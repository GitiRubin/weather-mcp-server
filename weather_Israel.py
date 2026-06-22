import re

from mcp.server.fastmcp import FastMCP
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright


mcp = FastMCP("weather-Israel")

FORECAST_URL = "https://www.weather2day.co.il/forecast"

# Candidate selectors for the main forecast container, tried in order. The page
# is JS-rendered and its markup may change, so we probe a few likely containers
# and fall back to the whole <body> if none match.
FORECAST_CONTAINER_SELECTORS = [
    "main",
    "#forecast",
    ".forecast",
    "#content",
]

# Cap the returned text so a noisy page cannot blow up the LLM context window.
MAX_FORECAST_CHARS = 6000

playwright = None
browser = None
page = None


def _clean_text(raw: str) -> str:
    """Strip noise from scraped page text so the LLM gets clean forecast data.

    Trims each line, drops blank lines, collapses repeated whitespace, and caps
    the total length at MAX_FORECAST_CHARS.
    """
    lines = [line.strip() for line in raw.splitlines()]
    lines = [line for line in lines if line]
    text = "\n".join(lines)
    # Collapse runs of spaces/tabs left inside lines.
    text = re.sub(r"[ \t]{2,}", " ", text)
    if len(text) > MAX_FORECAST_CHARS:
        text = text[:MAX_FORECAST_CHARS].rstrip() + "\n...[truncated]"
    return text

@mcp.tool()
async def open_weather_forecast_israel() -> str:
    """Open the Israel weather forecast website in a new browser page.

    This is step 1 of the Israel weather flow. It launches a Chromium browser,
    opens a new page, and navigates to the forecast site. The browser page is
    stored globally and reused by the other tools, so this must be called before
    enter_weather_forecast_city_israel() or select_weather_forecast_city_israel().

    Returns:
        A status message containing the opened page's title.
    """
    global playwright, browser, page

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    page = await browser.new_page()

    await page.goto(FORECAST_URL)

    # Dismiss the cookie consent banner if it appears, by clicking "מקובל"
    try:
        await page.click("#cookie-accept", timeout=5000)
    except PlaywrightTimeout:
        # Banner did not appear (e.g. already accepted) - nothing to dismiss
        pass

    title = await page.title()
    return f"Opened weather forecast page. Page title: {title}"

@mcp.tool()
async def enter_weather_forecast_city_israel(city: str) -> str:
    """Type a city name into the forecast search field.

    This fills the city name into the forecast search input, which triggers
    the site's autocomplete dropdown. It does not select a city yet; call
    select_weather_forecast_city_israel() afterwards to pick a suggestion.

    Args:
        city: The city name to search for.

    Returns:
        A status message indicating whether autocomplete suggestions appeared.
    """
    global page

    if page is None:
        return "Error: Weather forecast page is not open. Please call open_weather_forecast_israel() first."

    search_input = "#city_search_forecast"

    # Focus and type the city name into the search field
    await page.click(search_input)
    await page.fill(search_input, city)

    # Wait for the autocomplete suggestion list to appear
    try:
        await page.wait_for_selector(
            "#city_search_forecastautocomplete-list > div", timeout=5000
        )
        return (
            f"Typed '{city}'. Suggestions are ready - call "
            "select_weather_forecast_city_israel() to choose the first one."
        )
    except PlaywrightTimeout:
        return f"No suggestions found for '{city}'."


@mcp.tool()
async def select_weather_forecast_city_israel() -> str:
    """Select the first city in the autocomplete suggestion list.

    Clicks the first item in the forecast autocomplete dropdown, which
    navigates the page to that location's forecast. Requires that
    enter_weather_forecast_city_israel() was called first so that
    suggestions are present. Afterwards, call
    extract_weather_forecast_israel() to read the forecast content.

    Returns:
        A status message with the selected item and the resulting URL.
    """
    global page

    if page is None:
        return "Error: Weather forecast page is not open. Please call open_weather_forecast_israel() first."

    # The first direct child <div> of the autocomplete list is the first suggestion
    first_item = page.locator("#city_search_forecastautocomplete-list > div").first

    try:
        chosen = (await first_item.inner_text()).strip()
        # Clicking a suggestion navigates to that location's forecast page
        await first_item.click()
        await page.wait_for_load_state("networkidle")
        return f"Selected '{chosen}'. Now on: {page.url}"
    except PlaywrightTimeout:
        return "No city suggestion available to select."


@mcp.tool()
async def extract_weather_forecast_israel() -> str:
    """Read and clean the text of the currently open Israel forecast page.

    This is step 4 of the Israel weather flow. It must be called after
    select_weather_forecast_city_israel() so that the page is on a specific
    city's forecast. It scrapes the forecast container, cleans noise out of the
    text, and returns it so the model can answer the user's question from real
    page content.

    Returns:
        The cleaned forecast text, or an error message if the page is not open.
    """
    global page

    if page is None:
        return "Error: Weather forecast page is not open. Please call open_weather_forecast_israel() first."

    # Make sure the forecast finished loading before scraping.
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeout:
        pass

    raw = None
    for selector in FORECAST_CONTAINER_SELECTORS:
        try:
            locator = page.locator(selector).first
            raw = await locator.inner_text(timeout=3000)
            if raw and raw.strip():
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    # Fall back to the whole body if no targeted container matched.
    if not raw or not raw.strip():
        raw = await page.inner_text("body")

    cleaned = _clean_text(raw)
    return f"Weather forecast page content ({page.url}):\n\n{cleaned}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
