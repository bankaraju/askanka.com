"""
IndianAPI client — financial data + concall announcements.

Endpoints:
  GET https://stock.indianapi.in/financial_data?stock_name={symbol}
  GET https://stock.indianapi.in/recent_announcements?stock_name={symbol}

Requires INDIANAPI_KEY env var.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / "pipeline" / ".env")

log = logging.getLogger("opus.indianapi")

BASE = "https://stock.indianapi.in"
IST = timezone(timedelta(hours=5, minutes=30))

CONCALL_KEYWORDS = ("transcript", "concall", "analyst meet", "earnings call", "investor meet")


def _api_key() -> str | None:
    key = os.getenv("INDIANAPI_KEY", "").strip()
    return key if key else None


def _headers() -> dict:
    return {"X-Api-Key": _api_key() or ""}


def fetch_financials(nse_symbol: str) -> list[dict]:
    key = _api_key()
    if not key:
        log.debug("INDIANAPI_KEY not set — skipping financials for %s", nse_symbol)
        return []

    try:
        resp = requests.get(
            f"{BASE}/financial_data",
            params={"stock_name": nse_symbol},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("financial_data", data.get("data", []))
        if not isinstance(items, list):
            return []

        now = datetime.now(IST).isoformat()
        return [
            {
                "quarter": item.get("quarter", ""),
                "revenue": float(item.get("revenue", 0)),
                "pat": float(item.get("pat") or item.get("net_profit", 0)),
                "opm": float(item.get("opm") or item.get("operating_margin", 0)),
                "source": "indianapi",
                "fetched_at": now,
            }
            for item in items
            if item.get("quarter")
        ]
    except Exception as exc:
        log.warning("IndianAPI financials failed for %s: %s", nse_symbol, exc)
        return []


def fetch_concall_announcements(nse_symbol: str) -> list[dict]:
    key = _api_key()
    if not key:
        return []

    try:
        resp = requests.get(
            f"{BASE}/recent_announcements",
            params={"stock_name": nse_symbol},
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("announcements", data.get("data", []))
        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            headline = (item.get("headline") or item.get("title") or item.get("subject") or "").strip()
            if any(kw in headline.lower() for kw in CONCALL_KEYWORDS):
                results.append({
                    "headline": headline,
                    "date": item.get("date") or item.get("published") or "",
                    "link": item.get("link") or item.get("url") or "",
                })
        return results
    except Exception as exc:
        log.warning("IndianAPI announcements failed for %s: %s", nse_symbol, exc)
        return []
