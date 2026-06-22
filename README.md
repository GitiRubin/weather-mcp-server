# Shamai HaChazai 🌤️ — An MCP-Based Weather Assistant

> **Shamai HaChazai** (שַׁמַּאי הַחַזַּאי) is the assistant's name — a playful Hebrew
> rhyme meaning roughly *"Shamai the Forecaster"*. *Shamai* is a real first name,
> and it rhymes with *chazai* ("forecaster"), so the original name is kept as-is.

A smart weather assistant that answers natural-language questions (in Hebrew and
English) about the weather in **Israel** and the **USA**. The project is built as
an **MCP Host**: a language model (OpenAI `gpt-4o-mini`) is connected to two **MCP**
servers that provide it with tools for gathering real weather data, and it
summarizes that data into a clear answer in the user's language.

It can be used in two ways:

- 🖥️ **Browser UI** ("Shamai HaChazai") — a chat with an animated weather
  background, bilingual (RTL/LTR).
- ⌨️ **Command line** — a simple chat in the terminal.

---

## How It Works (Architecture)

```
┌──────────────┐    question   ┌─────────────────┐   tool calls   ┌──────────────────────┐
│     User     │ ───────────▶ │  ChatHost        │ ─────────────▶ │ weather_Israel (MCP) │ → Playwright
│ (browser/CLI)│ ◀─────────── │  + OpenAI LLM    │ ◀───────────── │ weather_USA   (MCP)  │ → NWS API
└──────────────┘    answer     └─────────────────┘   weather data  └──────────────────────┘
```

| File | Role |
|------|------|
| [`host.py`](host.py) | The `ChatHost` — drives the conversation with OpenAI and invokes the MCP tools. Also includes the CLI chat. |
| [`web.py`](web.py) | A **FastAPI** server that wraps `ChatHost` and serves the browser UI. |
| [`client.py`](client.py) | Wraps the connection to a single MCP server (stdio). |
| [`weather_Israel.py`](weather_Israel.py) | MCP server for Israel — scrapes the forecast from [weather2day.co.il](https://www.weather2day.co.il/forecast) using Playwright. |
| [`weather_USA.py`](weather_USA.py) | MCP server for the USA — pulls data from the [National Weather Service API](https://api.weather.gov). |
| [`static/index.html`](static/index.html) | The browser UI (self-contained HTML/CSS/JS, including the illustrated mascot). |

---

## Prerequisites

- **Python 3.13** or newer
- **[uv](https://docs.astral.sh/uv/)** for dependency management
- An **OpenAI API key**

---

## Installation

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Install the Chromium browser for Playwright** (required by the Israel server):
   ```bash
   uv run playwright install chromium
   ```

3. **Set your API key** — create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=sk-...your-key-here...
   ```

---

## Running

### 🖥️ Browser UI (recommended)

```bash
uv run web.py
```

Open in your browser: **http://127.0.0.1:8000**

### ⌨️ Command line

```bash
uv run host.py
```

Type a question. To exit, type `exit` / `quit` (or in Hebrew: `יציאה` / `סיום` / `צא`).

> **Note:** A question about weather **in Israel** opens a real Chrome window
> (Playwright) that browses to the forecast site — this is intended behavior.
> **USA** forecasts run purely through an API, with no browser window.

---

## Example Questions the Assistant Can Answer

The agent detects the language and replies in the same language. You can ask in
Hebrew or English.

### 🇮🇱 Israel

- "What's the weather like in Haifa?"
- "What's the wind in Jerusalem tonight?"
- "Is it going to rain tomorrow in Tel Aviv?"
- "How hot will it be in Be'er Sheva today?"
- "מה מזג האוויר בחיפה?"

### 🇺🇸 USA

- "What's the weather forecast in New York?"
- "Are there any active weather alerts in California?"
- "What's the forecast for Miami this week?"
- "מה התחזית בלוס אנג'לס?"
- "Are there any weather alerts in Texas?"

---

## The Tools (MCP Tools) the Agent Uses Behind the Scenes

**`weather_USA`**
- `get_forecast_in_USA(latitude, longitude)` — a detailed forecast by coordinates.
- `get_alerts_in_USA(state)` — active weather alerts by state code (e.g. `CA`, `NY`).

**`weather_Israel`** — a four-step flow over the forecast site:
- `open_weather_forecast_israel()` — open the forecast site.
- `enter_weather_forecast_city_israel(city)` — type the city name into the search box.
- `select_weather_forecast_city_israel()` — pick the city from the autocomplete list.
- `extract_weather_forecast_israel()` — read the forecast content from the page.

The agent chooses and chains these tools by itself — in the browser UI, "chips"
are shown indicating which tools were used for each answer.
