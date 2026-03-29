"""
Anka Research — Daily Price Dump (Skill 1)
Pulls EOD prices from EODHD (primary) with yfinance fallback.
Saves to pipeline/data/daily/YYYY-MM-DD.json

Run daily after market close (~6pm EST / 3:30am IST next day)
"""

import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
import yfinance as yf

# Load config
sys.path.insert(0, str(Path(__file__).parent))
from config import INDICES, STOCKS, FX_PAIRS, COMMODITIES, SECTOR_ETFS, VOLATILITY

# Setup
load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("EODHD_API_KEY")
DATA_DIR = Path(__file__).parent / "data" / "daily"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "daily_prices.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("daily_prices")

EODHD_BASE = "https://eodhd.com/api"


def fetch_eodhd_eod(symbol: str, date: str) -> dict | None:
    """Fetch EOD data from EODHD for a single symbol on a given date.
    Uses a 5-day lookback buffer to handle weekends/holidays."""
    if not API_KEY or API_KEY == "YOUR_KEY_HERE":
        return None
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        from_date = (dt - timedelta(days=5)).strftime("%Y-%m-%d")
        url = f"{EODHD_BASE}/eod/{symbol}"
        params = {"api_token": API_KEY, "fmt": "json", "from": from_date, "to": date}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[-1]  # latest entry
    except Exception as e:
        log.warning(f"EODHD failed for {symbol}: {e}")
    return None


def fetch_yf_eod(symbol: str, date: str) -> dict | None:
    """Fallback: fetch EOD data from yfinance."""
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        start = dt - timedelta(days=5)  # buffer for weekends
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=(dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        if hist.empty:
            return None
        row = hist.iloc[-1]
        return {
            "date": hist.index[-1].strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]) if "Volume" in row else 0,
            "source": "yfinance"
        }
    except Exception as e:
        log.warning(f"yfinance failed for {symbol}: {e}")
    return None


def fetch_price(eodhd_sym: str, yf_sym: str, date: str, label: str) -> dict:
    """Try EODHD first, fall back to yfinance."""
    result = fetch_eodhd_eod(eodhd_sym, date)
    if result:
        result["source"] = "eodhd"
        log.info(f"  {label}: {result.get('close', 'N/A')} (EODHD)")
        return result

    result = fetch_yf_eod(yf_sym, date)
    if result:
        log.info(f"  {label}: {result.get('close', 'N/A')} (yfinance fallback)")
        return result

    log.error(f"  {label}: FAILED both sources")
    return {"error": f"No data for {label}", "source": "none"}


def run_daily_dump(date: str = None):
    """Main entry point — dump all prices for a given date."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    log.info(f"=" * 60)
    log.info(f"DAILY PRICE DUMP — {date}")
    log.info(f"=" * 60)

    dump = {
        "date": date,
        "generated_at": datetime.now().isoformat(),
        "indices": {},
        "stocks": {},
        "fx": {},
        "commodities": {},
        "sector_etfs": {},
        "volatility": {},
        "metadata": {"eodhd_calls": 0, "yf_calls": 0, "failures": 0}
    }

    # 1. INDICES
    log.info("--- Indices ---")
    for name, cfg in INDICES.items():
        data = fetch_price(cfg["eodhd"], cfg["yf"], date, name)
        data["currency"] = cfg["currency"]
        dump["indices"][name] = data
        dump["metadata"]["eodhd_calls" if data.get("source") == "eodhd" else "yf_calls"] += 1

    # 2. STOCKS
    log.info("--- Stocks ---")
    for ticker, cfg in STOCKS.items():
        data = fetch_price(cfg["eodhd"], cfg["yf"], date, f"{ticker} ({cfg['index']})")
        data["sector"] = cfg["sector"]
        data["index"] = cfg["index"]
        dump["stocks"][ticker] = data
        dump["metadata"]["eodhd_calls" if data.get("source") == "eodhd" else "yf_calls"] += 1

    # 3. FX PAIRS
    log.info("--- FX Pairs ---")
    for pair, cfg in FX_PAIRS.items():
        data = fetch_price(cfg["eodhd"], cfg["yf"], date, pair)
        dump["fx"][pair] = data
        dump["metadata"]["eodhd_calls" if data.get("source") == "eodhd" else "yf_calls"] += 1

    # 4. COMMODITIES
    log.info("--- Commodities ---")
    for name, cfg in COMMODITIES.items():
        data = fetch_price(cfg["eodhd"], cfg["yf"], date, name)
        dump["commodities"][name] = data
        dump["metadata"]["eodhd_calls" if data.get("source") == "eodhd" else "yf_calls"] += 1

    # 5. SECTOR ETFs (yfinance only — these are US ETFs)
    log.info("--- Sector ETFs ---")
    for ticker, cfg in SECTOR_ETFS.items():
        data = fetch_yf_eod(cfg["yf"], date)
        if data:
            data["name"] = cfg["name"]
            log.info(f"  {ticker}: {data.get('close', 'N/A')} (yfinance)")
        else:
            data = {"error": f"No data for {ticker}", "source": "none"}
            dump["metadata"]["failures"] += 1
        dump["sector_etfs"][ticker] = data

    # 6. VOLATILITY (VIX)
    log.info("--- Volatility ---")
    for name, cfg in VOLATILITY.items():
        data = fetch_price(cfg["eodhd"], cfg["yf"], date, name)
        dump["volatility"][name] = data

    # Count failures
    for section in ["indices", "stocks", "fx", "commodities", "volatility"]:
        for k, v in dump[section].items():
            if v.get("source") == "none":
                dump["metadata"]["failures"] += 1

    # Save
    outfile = DATA_DIR / f"{date}.json"
    with open(outfile, "w") as f:
        json.dump(dump, f, indent=2, default=str)

    log.info(f"")
    log.info(f"DONE — saved to {outfile}")
    log.info(f"EODHD calls: {dump['metadata']['eodhd_calls']}, "
             f"yfinance calls: {dump['metadata']['yf_calls']}, "
             f"failures: {dump['metadata']['failures']}")

    return dump


if __name__ == "__main__":
    # Accept optional date arg: python daily_prices.py 2026-03-28
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    run_daily_dump(target_date)
