"""
Anka Research — Daily Fundamentals & News Dump (Skill 2)
Pulls analyst ratings, earnings, news, and key metrics via yfinance.
Saves to pipeline/data/daily/YYYY-MM-DD_fundamentals.json

Run daily alongside daily_prices.py
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from config import STOCKS, SECTOR_ETFS

DATA_DIR = Path(__file__).parent / "data" / "daily"
LOG_DIR = Path(__file__).parent / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "daily_fundamentals.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("daily_fundamentals")


def safe_get(info: dict, key: str, default=None):
    """Safely get a value from yfinance info dict."""
    try:
        val = info.get(key, default)
        if val is None:
            return default
        return val
    except Exception:
        return default


def fetch_stock_fundamentals(yf_symbol: str, label: str) -> dict:
    """Pull key fundamentals and news for a single stock via yfinance."""
    result = {
        "symbol": yf_symbol,
        "label": label,
        "fetched_at": datetime.now().isoformat(),
    }

    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}

        # === PRICE & VALUATION ===
        result["price"] = {
            "current": safe_get(info, "currentPrice") or safe_get(info, "regularMarketPrice"),
            "previous_close": safe_get(info, "previousClose") or safe_get(info, "regularMarketPreviousClose"),
            "52wk_high": safe_get(info, "fiftyTwoWeekHigh"),
            "52wk_low": safe_get(info, "fiftyTwoWeekLow"),
            "market_cap": safe_get(info, "marketCap"),
            "currency": safe_get(info, "currency", "USD"),
        }

        # === VALUATION METRICS ===
        result["valuation"] = {
            "forward_pe": safe_get(info, "forwardPE"),
            "trailing_pe": safe_get(info, "trailingPE"),
            "peg_ratio": safe_get(info, "pegRatio"),
            "price_to_book": safe_get(info, "priceToBook"),
            "ev_to_ebitda": safe_get(info, "enterpriseToEbitda"),
            "dividend_yield": safe_get(info, "dividendYield"),
        }

        # === FINANCIALS ===
        result["financials"] = {
            "revenue": safe_get(info, "totalRevenue"),
            "ebitda": safe_get(info, "ebitda"),
            "net_income": safe_get(info, "netIncomeToCommon"),
            "free_cash_flow": safe_get(info, "freeCashflow"),
            "total_debt": safe_get(info, "totalDebt"),
            "total_cash": safe_get(info, "totalCash"),
            "profit_margin": safe_get(info, "profitMargins"),
            "operating_margin": safe_get(info, "operatingMargins"),
            "revenue_growth": safe_get(info, "revenueGrowth"),
            "earnings_growth": safe_get(info, "earningsGrowth"),
        }

        # === ANALYST RATINGS ===
        result["analyst"] = {
            "target_mean": safe_get(info, "targetMeanPrice"),
            "target_high": safe_get(info, "targetHighPrice"),
            "target_low": safe_get(info, "targetLowPrice"),
            "recommendation": safe_get(info, "recommendationKey"),
            "num_analysts": safe_get(info, "numberOfAnalystOpinions"),
        }

        # === EARNINGS DATES ===
        try:
            cal = ticker.calendar
            if cal is not None and not (hasattr(cal, 'empty') and cal.empty):
                if isinstance(cal, dict):
                    result["earnings"] = {
                        "next_date": str(cal.get("Earnings Date", ["N/A"])[0]) if "Earnings Date" in cal else "N/A",
                    }
                else:
                    result["earnings"] = {"next_date": "see calendar"}
            else:
                result["earnings"] = {"next_date": "N/A"}
        except Exception:
            result["earnings"] = {"next_date": "N/A"}

        # === INSIDER & INSTITUTIONAL ===
        result["ownership"] = {
            "insider_pct": safe_get(info, "heldPercentInsiders"),
            "institutional_pct": safe_get(info, "heldPercentInstitutions"),
            "short_ratio": safe_get(info, "shortRatio"),
            "short_pct_float": safe_get(info, "shortPercentOfFloat"),
        }

        # === NEWS (last 5 headlines) ===
        try:
            news = ticker.news or []
            result["news"] = [
                {
                    "title": n.get("title", ""),
                    "publisher": n.get("publisher", ""),
                    "link": n.get("link", ""),
                    "published": n.get("providerPublishTime", ""),
                }
                for n in news[:5]
            ]
        except Exception:
            result["news"] = []

        # === ANALYST RECOMMENDATIONS HISTORY ===
        try:
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                recent = recs.tail(5).to_dict(orient="records")
                result["recent_ratings"] = recent
            else:
                result["recent_ratings"] = []
        except Exception:
            result["recent_ratings"] = []

        log.info(f"  {label}: price={result['price']['current']}, "
                 f"PE={result['valuation']['forward_pe']}, "
                 f"target={result['analyst']['target_mean']}, "
                 f"rec={result['analyst']['recommendation']}")

    except Exception as e:
        log.error(f"  {label}: FAILED — {e}")
        result["error"] = str(e)

    return result


def run_daily_fundamentals(date: str = None):
    """Main entry point — dump fundamentals for all watched stocks."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    log.info(f"=" * 60)
    log.info(f"DAILY FUNDAMENTALS DUMP — {date}")
    log.info(f"=" * 60)

    dump = {
        "date": date,
        "generated_at": datetime.now().isoformat(),
        "stocks": {},
        "etfs": {},
        "metadata": {"total": 0, "success": 0, "failed": 0}
    }

    # Stocks
    log.info("--- Stock Fundamentals ---")
    for ticker, cfg in STOCKS.items():
        data = fetch_stock_fundamentals(cfg["yf"], f"{ticker} ({cfg['index']})")
        data["sector"] = cfg["sector"]
        data["index"] = cfg["index"]
        dump["stocks"][ticker] = data
        dump["metadata"]["total"] += 1
        if "error" not in data:
            dump["metadata"]["success"] += 1
        else:
            dump["metadata"]["failed"] += 1

    # Sector ETFs
    log.info("--- ETF Fundamentals ---")
    for ticker, cfg in SECTOR_ETFS.items():
        data = fetch_stock_fundamentals(cfg["yf"], f"{ticker} ({cfg['name']})")
        dump["etfs"][ticker] = data
        dump["metadata"]["total"] += 1
        if "error" not in data:
            dump["metadata"]["success"] += 1
        else:
            dump["metadata"]["failed"] += 1

    # Save
    outfile = DATA_DIR / f"{date}_fundamentals.json"
    with open(outfile, "w") as f:
        json.dump(dump, f, indent=2, default=str)

    log.info(f"")
    log.info(f"DONE — saved to {outfile}")
    log.info(f"Total: {dump['metadata']['total']}, "
             f"Success: {dump['metadata']['success']}, "
             f"Failed: {dump['metadata']['failed']}")

    return dump


if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    run_daily_fundamentals(target_date)
