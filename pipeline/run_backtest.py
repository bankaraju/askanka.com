"""
Anka Research Pipeline — Backtest Orchestrator
One-time script to run the full historical pattern backtest,
generate pattern_lookup.json, and print a summary report.

Usage:
    python run_backtest.py [--force]    # --force re-downloads even if cache exists
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure pipeline dir is on path
sys.path.insert(0, str(Path(__file__).parent))

from pattern_engine import (
    run_full_backtest,
    fetch_india_historical,
    load_historical_events,
    build_event_response_matrix,
    build_pattern_lookup,
    compute_spread_backtest,
    PATTERN_OUTPUT,
    HIST_DIR,
    CACHE_MAX_AGE_HOURS,
)


def print_report(pattern_output_path: Path) -> None:
    """Pretty-print the backtest results from pattern_lookup.json."""
    if not pattern_output_path.exists():
        print("ERROR: pattern_lookup.json not found — backtest may have failed.")
        return

    with open(pattern_output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("\n" + "=" * 70)
    print("  ANKA RESEARCH — HISTORICAL PATTERN BACKTEST REPORT")
    print("=" * 70)
    print(f"  Generated   : {data.get('generated_at', 'N/A')}")
    print(f"  Events      : {data.get('n_events', 0)}")
    print(f"  Tickers     : {data.get('n_tickers', 0)}")
    print()

    # --- Pattern Lookup Summary ---
    lookup = data.get("pattern_lookup", {})
    print("-" * 70)
    print("  PATTERN LOOKUP — 1-Day Median Returns by Category")
    print("-" * 70)

    for category, tickers in sorted(lookup.items()):
        print(f"\n  [{category.upper()}]  ({len(tickers)} tickers)")
        winners = []
        losers = []
        for tk, stats in sorted(tickers.items(), key=lambda x: x[1].get("1d_median", 0), reverse=True):
            med = stats.get("1d_median", "—")
            hr = stats.get("hit_rate_1d", "—")
            n = stats.get("n_events", 0)
            line = f"    {tk:<14s} 1d: {med:>+7.2f}%   hit: {hr if isinstance(hr, str) else f'{hr:.0%}':>5s}   (n={n})" if isinstance(med, (int, float)) else f"    {tk:<14s} 1d: {med}"
            if isinstance(med, (int, float)) and med > 0:
                winners.append(line)
            else:
                losers.append(line)

        if winners:
            print("    WINNERS:")
            for w in winners:
                print(w)
        if losers:
            print("    LOSERS:")
            for l in losers:
                print(l)

    # --- Spread Backtest Summary ---
    spreads = data.get("spread_backtests", {})
    print("\n" + "=" * 70)
    print("  SPREAD BACKTESTS — Key Pair Performance")
    print("=" * 70)

    for pair_name, categories in sorted(spreads.items()):
        print(f"\n  [{pair_name}]")
        for cat, stats in sorted(categories.items()):
            s1 = stats.get("1d_spread_median", "—")
            s3 = stats.get("3d_spread_median", "—")
            s5 = stats.get("5d_spread_median", "—")
            hr = stats.get("hit_rate", "—")
            n = stats.get("n", 0)
            s1_str = f"{s1:>+6.2f}%" if isinstance(s1, (int, float)) else s1
            s3_str = f"{s3:>+6.2f}%" if isinstance(s3, (int, float)) else s3
            s5_str = f"{s5:>+6.2f}%" if isinstance(s5, (int, float)) else s5
            hr_str = f"{hr:.0%}" if isinstance(hr, (int, float)) else hr
            print(f"    {cat:<18s}  1d:{s1_str}  3d:{s3_str}  5d:{s5_str}  hit:{hr_str:>5s}  n={n}")

    # --- Key Takeaways ---
    print("\n" + "-" * 70)
    print("  KEY TAKEAWAYS")
    print("-" * 70)

    # Find best spreads
    best_pairs = []
    for pair_name, categories in spreads.items():
        for cat, stats in categories.items():
            s1 = stats.get("1d_spread_median")
            hr = stats.get("hit_rate")
            n = stats.get("n", 0)
            if s1 is not None and hr is not None and n >= 3:
                best_pairs.append((pair_name, cat, s1, hr, n))

    best_pairs.sort(key=lambda x: x[2], reverse=True)
    if best_pairs:
        print("\n  Top 5 Spread Opportunities (by 1-day spread, min 3 events):")
        for i, (pn, cat, s1, hr, n) in enumerate(best_pairs[:5], 1):
            print(f"    {i}. {pn} on {cat}: +{s1:.2f}% spread, {hr:.0%} hit rate (n={n})")

    print("\n" + "=" * 70)
    print("  Backtest complete. pattern_lookup.json saved.")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Anka Research — Historical Pattern Backtest")
    parser.add_argument("--force", action="store_true", help="Force re-download of price data (ignore cache)")
    args = parser.parse_args()

    if args.force:
        # Clear cache by removing CSVs
        if HIST_DIR.exists():
            for csv in HIST_DIR.glob("*.csv"):
                csv.unlink()
            print(f"Cleared cache: {HIST_DIR}")

    print("\nStarting Anka Research Pattern Backtest...")
    print(f"  Historical events: data/historical_events.json")
    print(f"  Stock data cache : data/india_historical/")
    print(f"  Output           : data/pattern_lookup.json\n")

    # Run the full backtest
    run_full_backtest()

    # Print formatted report
    print_report(PATTERN_OUTPUT)


if __name__ == "__main__":
    main()
