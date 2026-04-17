"""
EODHD Fundamentals API — quarterly income statement + balance sheet.

Endpoint: GET /fundamentals/{symbol}.NSE?api_token=KEY&fmt=json
Used for cross-verification of Screener/BSE quarterly data.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / "pipeline" / ".env")

log = logging.getLogger("opus.eodhd_fundamentals")

EODHD_BASE = "https://eodhd.com/api"
IST = timezone(timedelta(hours=5, minutes=30))


def _api_key() -> str | None:
    key = os.getenv("EODHD_API_KEY", "").strip()
    return key if key and key != "YOUR_KEY_HERE" else None


def fetch_fundamentals(nse_symbol: str) -> list[dict]:
    """Fetch quarterly financials from EODHD Fundamentals API.

    Returns: [{"quarter_end", "revenue", "pat", "total_assets", "source", "fetched_at"}]
    """
    key = _api_key()
    if not key:
        log.debug("EODHD_API_KEY not set — skipping fundamentals for %s", nse_symbol)
        return []

    try:
        url = f"{EODHD_BASE}/fundamentals/{nse_symbol}.NSE"
        resp = requests.get(url, params={"api_token": key, "fmt": "json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        income = (data.get("Financials", {})
                  .get("Income_Statement", {})
                  .get("quarterly", {}))
        balance = (data.get("Financials", {})
                   .get("Balance_Sheet", {})
                   .get("quarterly", {}))

        now = datetime.now(IST).isoformat()
        results = []
        for date_key, inc in income.items():
            bal = balance.get(date_key, {})
            rev_raw = inc.get("totalRevenue") or inc.get("revenue") or "0"
            pat_raw = inc.get("netIncome") or inc.get("netIncomeContinuousOperations") or "0"
            assets_raw = bal.get("totalAssets") or "0"

            results.append({
                "quarter_end": date_key,
                "revenue": float(rev_raw) / 1e7 if float(rev_raw) > 1e6 else float(rev_raw),
                "pat": float(pat_raw) / 1e7 if float(pat_raw) > 1e6 else float(pat_raw),
                "total_assets": float(assets_raw) / 1e7 if float(assets_raw) > 1e6 else float(assets_raw),
                "source": "eodhd",
                "fetched_at": now,
            })

        return sorted(results, key=lambda x: x["quarter_end"], reverse=True)
    except Exception as exc:
        log.warning("EODHD fundamentals failed for %s: %s", nse_symbol, exc)
        return []
