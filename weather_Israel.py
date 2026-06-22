from mcp.server.fastmcp import FastMCP
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright


mcp = FastMCP("weather-Israel")

FORECAST_URL = "https://www.weather2day.co.il/forecast"

playwright = None
browser = None
page = None

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
    suggestions are present.

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



def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
