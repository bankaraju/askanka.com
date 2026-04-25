"""IndianAPI corporate_actions HTTP client.

Auth pattern mirrors pipeline/news_scanner.py:125-149 — X-Api-Key header
with stock_name query param. Key is read from the INDIANAPI_KEY env var;
data validation policy §6.1 prohibits hardcoding secrets in code or
specification documents.
"""
from __future__ import annotations

import os

import requests

ENDPOINT = "https://stock.indianapi.in/corporate_actions"
DEFAULT_TIMEOUT = 15


def fetch_corporate_actions(symbol: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Return the full corporate_actions payload for the given F&O symbol.

    Raises RuntimeError if INDIANAPI_KEY is not set or the HTTP call fails."""
    api_key = os.getenv("INDIANAPI_KEY")
    if not api_key:
        raise RuntimeError("INDIANAPI_KEY environment variable is not set")
    resp = requests.get(
        ENDPOINT,
        headers={"X-Api-Key": api_key},
        params={"stock_name": symbol},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()
