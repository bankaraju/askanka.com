"""Anka Research — FII/DII daily flow fetcher.

Scrapes NSE's public fiidii endpoint and writes normalized JSON to
pipeline/data/flows/<date>.json for the daily pipeline + article grounding.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data" / "flows"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "fii_flows.log", delay=True, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("fii_flows")

NSE_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_HOME = "https://www.nseindia.com/"


def fetch_nse() -> list[dict] | None:
    """Return the NSE fiidii array, or None on failure."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_HOME,
    })
    try:
        s.get(NSE_HOME, timeout=10)
        r = s.get(NSE_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or not data:
            log.warning("NSE returned empty/non-list payload")
            return None
        return data
    except Exception as e:
        log.warning(f"NSE fetch failed: {e}")
        return None


def normalize(raw: list[dict]) -> dict:
    """Convert NSE array-of-rows into the flows dict our grounding expects."""
    out = {
        "date": None,
        "fii_equity_net": None,
        "fii_equity_buy": None,
        "fii_equity_sell": None,
        "dii_equity_net": None,
        "dii_equity_buy": None,
        "dii_equity_sell": None,
        "source": "nse_fiidiiTradeReact",
    }
    for row in raw:
        cat = (row.get("category") or "").upper()
        try:
            buy = float(row.get("buyValue", 0))
            sell = float(row.get("sellValue", 0))
            net = float(row.get("netValue", 0))
        except (TypeError, ValueError):
            continue
        out["date"] = row.get("date") or out["date"]
        if "FII" in cat or "FPI" in cat:
            out["fii_equity_buy"] = buy
            out["fii_equity_sell"] = sell
            out["fii_equity_net"] = net
        elif "DII" in cat:
            out["dii_equity_buy"] = buy
            out["dii_equity_sell"] = sell
            out["dii_equity_net"] = net
    return out


def run(date: str | None = None) -> dict | None:
    """Fetch + save today's flows. date is the run date (filename); NSE's
    own 'date' field lives inside the payload and is usually T-1."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    raw = fetch_nse()
    if raw is None:
        log.error(f"FII flow fetch failed for run-date {date}")
        return None
    flows = normalize(raw)
    path = DATA_DIR / f"{date}.json"
    path.write_text(json.dumps(flows, indent=2), encoding="utf-8")
    log.info(
        f"Saved flows to {path} — FII net={flows['fii_equity_net']} DII net={flows['dii_equity_net']} "
        f"(NSE date={flows['date']})"
    )
    return flows


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    r = run(d)
    sys.exit(0 if r else 1)
