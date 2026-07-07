"""
Tools available to the FSAgent and MCPToolAgent via LangChain.

Two categories:
  - FS_TOOLS  (FSAgent)      : file_read, file_write  (sandbox-scoped)
  - MCP_TOOLS (MCPToolAgent) : calculate, get_weather, get_stock_price
"""
from __future__ import annotations

import hashlib
import os

from langchain_core.tools import tool

import config as cfg


def _seed(text: str) -> int:
    """Turn a string into a stable number.

    We use SHA-256 instead of Python's built-in hash(). hash() gives a
    different result each time the program starts, but we want the fake
    tools to give the same answer on every run.
    """
    return int(hashlib.sha256(text.strip().lower().encode()).hexdigest(), 16)


# Sandbox tools

@tool
def list_files() -> str:
    """List all files available in the sandbox workspace."""
    try:
        files = [
            f for f in os.listdir(cfg.SANDBOX_DIR)
            if os.path.isfile(os.path.join(cfg.SANDBOX_DIR, f))
        ]
        return "\n".join(files) if files else "(sandbox is empty)"
    except Exception as e:
        return f"ERROR: {e}"


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
def file_write(path: str, content: str, append: bool = False) -> str:
    """Write 'content' to 'path' (relative to the sandbox workspace). Set append=True to add to an existing file instead of overwriting."""
    rel  = os.path.normpath(path)
    full = os.path.realpath(os.path.join(cfg.SANDBOX_DIR, rel))
    if not full.startswith(os.path.realpath(cfg.SANDBOX_DIR)):
        return "ERROR: path traversal denied"
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "a" if append else "w"
        open(full, mode).write(content)
        action = "Appended" if append else "Written"
        return f"{action} {len(content)} bytes to {rel}."
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


# Fake weather and stock tools (no network)

# Weather codes and what they mean (WMO standard)
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
    """
    if not location.strip():
        return "Location not found: ''"
    # Fake weather: the numbers come from the city name, so the same city
    # always gives the same result and no internet is needed. The text is
    # made to look like a real weather API.
    s = _seed(location)
    codes = [0, 1, 2, 3, 45, 51, 61, 63, 71, 80, 95]
    condition = _WMO[codes[s % len(codes)]]
    temp     = -5 + (s % 40)          # -5 .. 34 °C
    feels    = temp - (s // 40 % 4)   # a few degrees cooler
    humidity = 40 + (s % 55)          # 40 .. 94 %
    wind     = 3 + (s % 30)           # 3 .. 32 km/h
    name = location.strip().title()

    return (
        f"Weather in {name}:\n"
        f"  Condition   : {condition}\n"
        f"  Temperature : {temp}°C  (feels like {feels}°C)\n"
        f"  Humidity    : {humidity}%\n"
        f"  Wind speed  : {wind} km/h"
    )


@tool
def get_stock_price(ticker: str) -> str:
    """
    Get the latest stock price and key metrics for a ticker symbol.
    Examples: AAPL, TSLA, MSFT, GOOGL, AMZN, NVDA.
    """
    tk = ticker.upper().strip()
    if not tk:
        return "No data found for ticker: ''"
    # Fake stock data: the numbers come from the ticker, so the same ticker
    # always gives the same result and no internet is needed. The text is
    # made to look like a real stock API.
    s = _seed(tk)
    price  = 20 + (s % 40000) / 100.0     # 20.00 .. 419.99
    change = ((s // 100 % 800) - 400) / 100.0   # -4.00 .. +3.99
    pct    = (change / price * 100) if price else 0.0
    arrow  = "▲" if change >= 0 else "▼"
    high   = price * 1.25
    low    = price * 0.72
    mcap   = price * (s % 900 + 100) / 100.0     # billions

    return (
        f"{tk} — Latest price: ${price:.2f}  "
        f"{arrow} {change:+.2f} ({pct:+.2f}%)\n"
        f"  52-week high: ${high:.2f}\n"
        f"  52-week low : ${low:.2f}\n"
        f"  Market cap  : ${mcap:.1f}B"
    )


# Registries

FS_TOOLS  = [list_files, file_read, file_write]
MCP_TOOLS = [calculate, get_weather, get_stock_price]
