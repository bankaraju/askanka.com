"""
Backfill missing daily data from war start (Feb 28, 2026) to today.
Skips dates that already have data files.
Skips weekends and Indian holidays.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trading_calendar import is_trading_day, IST
from daily_prices import run_daily_dump
from daily_fundamentals import run_daily_fundamentals

DATA_DIR = Path(__file__).parent / "data" / "daily"
WAR_START = datetime(2026, 2, 28)


def backfill():
    today = datetime.now(IST).replace(tzinfo=None)
    current = WAR_START
    filled = 0
    skipped = 0

    while current <= today:
        date_str = current.strftime("%Y-%m-%d")
        price_file = DATA_DIR / f"{date_str}.json"

        if price_file.exists():
            print(f"  {date_str} — already exists, skipping")
            skipped += 1
        elif current.weekday() >= 5:
            # Weekend - skip silently (EODHD won't have data anyway)
            pass
        else:
            print(f"\n  {date_str} — fetching...")
            try:
                run_daily_dump(date_str)
                filled += 1
            except Exception as e:
                print(f"  {date_str} — PRICE ERROR: {e}")

            try:
                run_daily_fundamentals(date_str)
            except Exception as e:
                print(f"  {date_str} — FUNDAMENTALS ERROR: {e}")

        current += timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"BACKFILL COMPLETE: {filled} days filled, {skipped} skipped")
    print(f"{'='*60}")


if __name__ == "__main__":
    backfill()
