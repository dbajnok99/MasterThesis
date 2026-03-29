"""
Tools available to the FSAgent and MCPToolAgent via LangChain.

Two categories:
  - FS_TOOLS  (FSAgent)      : file_read, file_write  (sandbox-scoped)
  - MCP_TOOLS (MCPToolAgent) : calculate, get_weather, get_stock_price
"""
from __future__ import annotations

import os

import requests
import yfinance as yf
from langchain_core.tools import tool

import config as cfg


# ── Sandbox tools ─────────────────────────────────────────────────────────────

@tool
def file_read(path: str) -> str:
    """Read a file from the sandbox workspace. 'path' is relative to the sandbox directory."""
    rel  = os.path.normpath(path)
    full = os.path.realpath(os.path.join(cfg.SANDBOX_DIR, rel))
    if not full.startswith(os.path.realpath(cfg.SANDBOX_DIR)):
        return "ERROR: path traversal denied"
    try:
        return open(full).read()
    except FileNotFoundError:
        return f"ERROR: file not found – {rel}"
    except Exception as e:
        return f"ERROR: {e}"


@tool
def file_write(path: str, content: str) -> str:
    """Write 'content' to 'path' (relative to the sandbox workspace)."""
    rel  = os.path.normpath(path)
    full = os.path.realpath(os.path.join(cfg.SANDBOX_DIR, rel))
    if not full.startswith(os.path.realpath(cfg.SANDBOX_DIR)):
        return "ERROR: path traversal denied"
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(content)
        return f"Written {len(content)} bytes to {rel}."
    except Exception as e:
        return f"ERROR: {e}"


@tool
def calculate(expression: str) -> str:
    """Evaluate a simple arithmetic expression such as '6 * 7' or '(100 + 50) / 3'."""
    if not all(c in "0123456789+-*/()., " for c in expression):
        return "ERROR: expression contains unsafe characters"
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307
    except Exception as e:
        return f"ERROR: {e}"


# ── External API tools ────────────────────────────────────────────────────────

# Weather code → human-readable description (WMO standard)
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail",
}


@tool
def get_weather(location: str) -> str:
    """
    Get current weather for any city worldwide.
    Returns temperature (°C), feels-like, humidity, wind speed, and conditions.
    Uses Open-Meteo (free, no API key required).
    """
    try:
        # 1. Geocode the location name → lat/lon
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        ).json()
        if not geo.get("results"):
            return f"Location not found: {location!r}"
        r    = geo["results"][0]
        lat, lon = r["latitude"], r["longitude"]
        name = f"{r['name']}, {r.get('country', '')}"

        # 2. Fetch current conditions
        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": (
                    "temperature_2m,apparent_temperature,weather_code,"
                    "wind_speed_10m,relative_humidity_2m"
                ),
                "timezone": "auto",
            },
            timeout=8,
        ).json()
        c = weather["current"]
        condition = _WMO.get(c["weather_code"], f"Code {c['weather_code']}")

        return (
            f"Weather in {name}:\n"
            f"  Condition   : {condition}\n"
            f"  Temperature : {c['temperature_2m']}°C  "
            f"(feels like {c['apparent_temperature']}°C)\n"
            f"  Humidity    : {c['relative_humidity_2m']}%\n"
            f"  Wind speed  : {c['wind_speed_10m']} km/h"
        )
    except Exception as e:
        return f"ERROR fetching weather: {e}"


@tool
def get_stock_price(ticker: str) -> str:
    """
    Get the latest stock price and key metrics for a ticker symbol.
    Examples: AAPL, TSLA, MSFT, GOOGL, AMZN, NVDA.
    Uses Yahoo Finance (free, no API key required).
    """
    try:
        t    = yf.Ticker(ticker.upper())
        hist = t.history(period="5d")
        if hist.empty:
            return f"No data found for ticker: {ticker!r}"

        price  = float(hist["Close"].iloc[-1])
        prev   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        change = price - prev
        pct    = (change / prev * 100) if prev else 0.0
        arrow  = "▲" if change >= 0 else "▼"

        fi = t.fast_info
        mcap = (
            f"  Market cap  : ${fi.market_cap / 1e9:.1f}B\n"
            if hasattr(fi, "market_cap") and fi.market_cap else ""
        )
        return (
            f"{ticker.upper()} — Latest price: ${price:.2f}  "
            f"{arrow} {change:+.2f} ({pct:+.2f}%)\n"
            f"  52-week high: ${fi.year_high:.2f}\n"
            f"  52-week low : ${fi.year_low:.2f}\n"
            f"{mcap}"
        )
    except Exception as e:
        return f"ERROR fetching stock data for {ticker!r}: {e}"


# ── Registries ────────────────────────────────────────────────────────────────

FS_TOOLS  = [file_read, file_write]
MCP_TOOLS = [calculate, get_weather, get_stock_price]
ALL_TOOLS = FS_TOOLS + MCP_TOOLS
