"""
Anka Research — Daily Runner
Runs both price dump and fundamentals dump in sequence.
This is what the scheduled task calls.
"""

import sys
from datetime import datetime
from daily_prices import run_daily_dump
from daily_fundamentals import run_daily_fundamentals
from fii_flows import run as run_fii_flows


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"ANKA RESEARCH — DAILY DATA PIPELINE")
    print(f"Date: {date}")
    print(f"{'='*60}\n")

    print("STEP 1: Price Dump (EODHD + yfinance fallback)")
    print("-" * 40)
    prices = run_daily_dump(date)

    print(f"\nSTEP 2: Fundamentals Dump (yfinance)")
    print("-" * 40)
    fundamentals = run_daily_fundamentals(date)

    print(f"\nSTEP 3: FII/DII flows (NSE)")
    print("-" * 40)
    flows = run_fii_flows(date)

    print(f"\n{'='*60}")
    print(f"DAILY PIPELINE COMPLETE")
    print(f"Prices: {prices['metadata']['eodhd_calls']} EODHD + "
          f"{prices['metadata']['yf_calls']} yfinance, "
          f"{prices['metadata']['failures']} failures")
    print(f"Fundamentals: {fundamentals['metadata']['success']}/"
          f"{fundamentals['metadata']['total']} success")
    print(f"Flows: {'ok' if flows else 'FAILED'} "
          f"(FII net {flows['fii_equity_net'] if flows else 'n/a'})")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
