"""
Anka Research — Weekly Aggregator
Reads 5 days of daily dumps, calculates WoW changes, computes rankings,
and outputs a structured JSON for report generation.

Saves to pipeline/data/weekly/week-NNN.json
"""

import json
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from config import WAR_START_DATE
from portfolio_tracker import run_portfolio_tracker

DATA_DIR = Path(__file__).parent / "data" / "daily"
WEEKLY_DIR = Path(__file__).parent / "data" / "weekly"
LOG_DIR = Path(__file__).parent / "logs"
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "weekly_aggregator.log", delay=True, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("weekly_aggregator")


def load_daily_file(date_str: str, suffix: str = "") -> dict | None:
    """Load a daily JSON dump file."""
    filename = f"{date_str}{suffix}.json"
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return None


def get_week_dates(end_date: str) -> list[str]:
    """Get the last 7 calendar days ending on end_date.
    Includes Saturday dumps (which capture Friday US close).
    Returns Mon-Sat date strings to find all daily dump files."""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    d = end
    while len(dates) < 7:  # 7 calendar days back
        if d.weekday() < 6:  # Mon-Sat (Sat has Friday US close)
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return sorted(dates)


def safe_close(data: dict) -> float | None:
    """Extract closing price from a daily data entry."""
    if data and isinstance(data, dict):
        val = data.get("close") or data.get("adjusted_close")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def pct_change(old: float, new: float) -> float | None:
    """Calculate percentage change."""
    if old and new and old != 0:
        return round(((new - old) / old) * 100, 2)
    return None


def run_weekly_aggregation(end_date: str = None, week_number: int = None):
    """Main entry point — aggregate a week's data."""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if week_number is None:
        # Calculate week number from war start
        war_start = datetime.strptime(WAR_START_DATE, "%Y-%m-%d")
        current = datetime.strptime(end_date, "%Y-%m-%d")
        week_number = max(1, ((current - war_start).days // 7) + 1)

    week_dates = get_week_dates(end_date)
    log.info(f"=" * 60)
    log.info(f"WEEKLY AGGREGATION — Week {week_number:03d}")
    log.info(f"Period: {week_dates[0]} to {week_dates[-1]}")
    log.info(f"=" * 60)

    # Load all available daily dumps
    daily_prices = {}
    daily_fundamentals = {}
    for d in week_dates:
        dp = load_daily_file(d)
        if dp:
            daily_prices[d] = dp
            log.info(f"  Loaded prices: {d}")
        df = load_daily_file(d, "_fundamentals")
        if df:
            daily_fundamentals[d] = df
            log.info(f"  Loaded fundamentals: {d}")

    if not daily_prices:
        log.error("No daily price data found for this week!")
        return None

    # Get first and last available dates
    available_dates = sorted(daily_prices.keys())
    first_date = available_dates[0]
    last_date = available_dates[-1]
    first_data = daily_prices[first_date]
    last_data = daily_prices[last_date]

    # Build weekly summary
    weekly = {
        "week_number": week_number,
        "week_label": f"Week {week_number:03d}",
        "period": {"start": first_date, "end": last_date},
        "generated_at": datetime.now().isoformat(),
        "trading_days_available": len(available_dates),
        "indices": {},
        "stocks": {},
        "fx": {},
        "commodities": {},
        "sector_etfs": {},
        "volatility": {},
        "rankings": {},
    }

    # === INDEX WoW ===
    log.info("--- Index WoW ---")
    for name in first_data.get("indices", {}):
        start_close = safe_close(first_data["indices"].get(name, {}))
        end_close = safe_close(last_data.get("indices", {}).get(name, {}))
        change = pct_change(start_close, end_close)
        weekly["indices"][name] = {
            "start_price": start_close,
            "end_price": end_close,
            "wow_change_pct": change,
            "currency": first_data["indices"].get(name, {}).get("currency", ""),
        }
        log.info(f"  {name}: {start_close} → {end_close} ({change}%)")

    # === STOCK WoW ===
    log.info("--- Stock WoW ---")
    for ticker in first_data.get("stocks", {}):
        start_close = safe_close(first_data["stocks"].get(ticker, {}))
        end_close = safe_close(last_data.get("stocks", {}).get(ticker, {}))
        change = pct_change(start_close, end_close)

        stock_entry = {
            "start_price": start_close,
            "end_price": end_close,
            "wow_change_pct": change,
            "sector": first_data["stocks"].get(ticker, {}).get("sector", ""),
            "index": first_data["stocks"].get(ticker, {}).get("index", ""),
        }

        # Merge latest fundamentals if available
        if daily_fundamentals:
            latest_fund_date = sorted(daily_fundamentals.keys())[-1]
            fund_data = daily_fundamentals[latest_fund_date].get("stocks", {}).get(ticker, {})
            if fund_data:
                stock_entry["analyst"] = fund_data.get("analyst", {})
                stock_entry["valuation"] = fund_data.get("valuation", {})
                stock_entry["financials"] = fund_data.get("financials", {})
                stock_entry["ownership"] = fund_data.get("ownership", {})
                stock_entry["news"] = fund_data.get("news", [])
                stock_entry["recent_ratings"] = fund_data.get("recent_ratings", [])

        weekly["stocks"][ticker] = stock_entry
        log.info(f"  {ticker}: {start_close} → {end_close} ({change}%)")

    # === FX WoW ===
    log.info("--- FX WoW ---")
    for pair in first_data.get("fx", {}):
        start_close = safe_close(first_data["fx"].get(pair, {}))
        end_close = safe_close(last_data.get("fx", {}).get(pair, {}))
        change = pct_change(start_close, end_close)
        weekly["fx"][pair] = {
            "start_rate": start_close,
            "end_rate": end_close,
            "wow_change_pct": change,
        }

    # === COMMODITIES WoW ===
    log.info("--- Commodities WoW ---")
    for name in first_data.get("commodities", {}):
        start_close = safe_close(first_data["commodities"].get(name, {}))
        end_close = safe_close(last_data.get("commodities", {}).get(name, {}))
        change = pct_change(start_close, end_close)
        weekly["commodities"][name] = {
            "start_price": start_close,
            "end_price": end_close,
            "wow_change_pct": change,
        }

    # === SECTOR ETFs WoW ===
    for ticker in first_data.get("sector_etfs", {}):
        start_close = safe_close(first_data["sector_etfs"].get(ticker, {}))
        end_close = safe_close(last_data.get("sector_etfs", {}).get(ticker, {}))
        change = pct_change(start_close, end_close)
        weekly["sector_etfs"][ticker] = {
            "start_price": start_close,
            "end_price": end_close,
            "wow_change_pct": change,
        }

    # === VOLATILITY ===
    for name in first_data.get("volatility", {}):
        start_close = safe_close(first_data["volatility"].get(name, {}))
        end_close = safe_close(last_data.get("volatility", {}).get(name, {}))
        change = pct_change(start_close, end_close)
        weekly["volatility"][name] = {
            "start_level": start_close,
            "end_level": end_close,
            "wow_change_pct": change,
        }

    # === RANKINGS ===
    # Top 5 outperformers and underperformers
    stock_changes = [
        (t, d.get("wow_change_pct", 0) or 0)
        for t, d in weekly["stocks"].items()
    ]
    stock_changes.sort(key=lambda x: x[1], reverse=True)
    weekly["rankings"]["top_5_winners"] = [
        {"ticker": t, "wow_pct": c, "sector": weekly["stocks"][t].get("sector", ""),
         "index": weekly["stocks"][t].get("index", "")}
        for t, c in stock_changes[:5]
    ]
    weekly["rankings"]["top_5_losers"] = [
        {"ticker": t, "wow_pct": c, "sector": weekly["stocks"][t].get("sector", ""),
         "index": weekly["stocks"][t].get("index", "")}
        for t, c in stock_changes[-5:]
    ]

    # Best/worst index
    idx_changes = [
        (n, d.get("wow_change_pct", 0) or 0)
        for n, d in weekly["indices"].items()
    ]
    idx_changes.sort(key=lambda x: x[1], reverse=True)
    weekly["rankings"]["best_index"] = idx_changes[0] if idx_changes else None
    weekly["rankings"]["worst_index"] = idx_changes[-1] if idx_changes else None

    # Strongest/weakest currency
    fx_changes = [
        (p, d.get("wow_change_pct", 0) or 0)
        for p, d in weekly["fx"].items()
    ]
    fx_changes.sort(key=lambda x: x[1], reverse=True)
    weekly["rankings"]["fx_strongest"] = fx_changes[0] if fx_changes else None
    weekly["rankings"]["fx_weakest"] = fx_changes[-1] if fx_changes else None

    # === MODEL PORTFOLIO TRACKER ===
    log.info("\n--- Model Portfolio Tracker ---")
    try:
        portfolio_data = run_portfolio_tracker(last_date)
        weekly["model_portfolio"] = portfolio_data
        log.info(f"  Portfolio: {portfolio_data['summary']['active_positions']} active, "
                 f"avg USD return: {portfolio_data['summary']['avg_return_usd_pct']}%")
    except Exception as e:
        log.error(f"  Portfolio tracker failed: {e}")
        weekly["model_portfolio"] = {"error": str(e)}

    # Save
    outfile = WEEKLY_DIR / f"week-{week_number:03d}.json"
    with open(outfile, "w") as f:
        json.dump(weekly, f, indent=2, default=str)

    log.info(f"")
    log.info(f"DONE — saved to {outfile}")
    log.info(f"Top winner: {weekly['rankings']['top_5_winners'][0] if weekly['rankings']['top_5_winners'] else 'N/A'}")
    log.info(f"Top loser: {weekly['rankings']['top_5_losers'][0] if weekly['rankings']['top_5_losers'] else 'N/A'}")

    return weekly


if __name__ == "__main__":
    end = sys.argv[1] if len(sys.argv) > 1 else None
    wk = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run_weekly_aggregation(end, wk)
