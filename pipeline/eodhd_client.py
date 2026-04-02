"""
Anka Research Pipeline — EODHD Client
Centralised access to EODHD real-time and EOD endpoints.
Primary data source for all live signal operations.
yfinance is used only as fallback (see signal_tracker.py).

Endpoints used:
  Real-time:  GET /api/real-time/{symbol}?api_token=KEY&fmt=json
  EOD series: GET /api/eod/{symbol}?api_token=KEY&fmt=json&from=YYYY-MM-DD&to=YYYY-MM-DD
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Ensure bundled lib/ packages (requests, dotenv, etc.) are importable when
# this module is loaded directly (e.g. tests, -c snippets). Entry points such
# as schtask_runner.py also inject this path, so the insert is idempotent.
_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.eodhd")

EODHD_BASE = "https://eodhd.com/api"
_API_KEY: Optional[str] = os.getenv("EODHD_API_KEY")
_TIMEOUT = 10  # seconds


def _key() -> Optional[str]:
    return _API_KEY


def fetch_realtime(eodhd_symbol: str) -> Optional[dict]:
    """Fetch the latest real-time quote for a single EODHD symbol.

    Returns dict with keys: close, open, high, low, volume, previousClose,
    change, change_p, timestamp.
    Returns None on any failure (caller falls back to yfinance).

    Example symbol: "HAL.NSE", "BPCL.NSE", "BZ.COMM"
    """
    key = _key()
    if not key or key == "YOUR_KEY_HERE":
        log.debug("EODHD_API_KEY not set — skipping real-time fetch for %s", eodhd_symbol)
        return None
    try:
        url = f"{EODHD_BASE}/real-time/{eodhd_symbol}"
        resp = requests.get(url, params={"api_token": key, "fmt": "json"}, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data or "close" not in data:
            log.warning("EODHD real-time: empty response for %s", eodhd_symbol)
            return None
        return {
            "close":         float(data["close"]),
            "open":          float(data.get("open") or data["close"]),
            "previousClose": float(data.get("previousClose") or data["close"]),
            "change_p":      float(data.get("change_p", 0.0)),
            "timestamp":     data.get("timestamp"),
            "source":        "eodhd_rt",
        }
    except requests.Timeout:
        log.warning("EODHD real-time timeout for %s", eodhd_symbol)
        return None
    except Exception as exc:
        log.warning("EODHD real-time failed for %s: %s", eodhd_symbol, exc)
        return None


def fetch_eod_series(eodhd_symbol: str, days: int = 30) -> list[dict]:
    """Fetch the last N calendar days of EOD OHLCV for a single symbol.

    Returns list of dicts sorted oldest-first, each with keys:
    date, open, high, low, close, adjusted_close, volume.
    Returns empty list on failure.

    Used as fallback when saved daily dump files don't cover the full window.
    """
    key = _key()
    if not key or key == "YOUR_KEY_HERE":
        log.debug("EODHD_API_KEY not set — skipping EOD series for %s", eodhd_symbol)
        return []
    try:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")  # +10 buffer for holidays
        url = f"{EODHD_BASE}/eod/{eodhd_symbol}"
        resp = requests.get(url, params={
            "api_token": key, "fmt": "json",
            "from": from_date, "to": to_date,
        }, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            log.warning("EODHD EOD series: unexpected response for %s", eodhd_symbol)
            return []
        return [
            {
                "date":           row["date"],
                "open":           float(row.get("open", 0)),
                "high":           float(row.get("high", 0)),
                "low":            float(row.get("low", 0)),
                "close":          float(row["close"]),
                "adjusted_close": float(row.get("adjusted_close", row["close"])),
                "volume":         int(row.get("volume", 0)),
                "source":         "eodhd",
            }
            for row in data
            if "close" in row and row["close"]
        ]
    except requests.Timeout:
        log.warning("EODHD EOD series timeout for %s", eodhd_symbol)
        return []
    except Exception as exc:
        log.warning("EODHD EOD series failed for %s: %s", eodhd_symbol, exc)
        return []
