"""
Driver: 60-day intraday correlation-break replay.

Usage:
    python -m pipeline.autoresearch.scripts.run_intraday_replay \
        [--n-days 60] [--end-date YYYY-MM-DD] \
        [--single-day YYYY-MM-DD] [--regime CAUTION] \
        [--max-tickers N] [-v]

Outputs:
    pipeline/autoresearch/data/intraday_break_replay_60d.parquet
    Summary printed to stdout, including verdict line:
        AVG_PNL_BPS=X.XX — {EDGE_PRESENT if X > 40 else NO_EDGE}
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make pipeline/ importable regardless of how this script is launched
_HERE = Path(__file__).resolve()
PIPELINE_DIR = _HERE.parent.parent.parent
AUTORESEARCH_DIR = _HERE.parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(AUTORESEARCH_DIR))

from intraday_break_replay import (  # noqa: E402
    run_replay,
    summarize,
    print_summary,
    save_parquet,
    OUTPUT_PARQUET,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-days", type=int, default=60)
    parser.add_argument("--end-date", type=str, default=None,
                        help="Inclusive end date YYYY-MM-DD (defaults to latest regime_history entry)")
    parser.add_argument("--single-day", type=str, default=None,
                        help="Smoke-test mode: run only this one trading day")
    parser.add_argument("--regime", type=str, default=None,
                        help="Force regime (only meaningful with --single-day)")
    parser.add_argument("--max-tickers", type=int, default=None,
                        help="Cap the per-day universe (debugging)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--out", type=str, default=str(OUTPUT_PARQUET),
                        help="Output parquet path")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    trades = run_replay(
        n_days=args.n_days,
        end_date=args.end_date,
        max_tickers=args.max_tickers,
        single_day=args.single_day,
        force_regime=args.regime,
    )

    summary = summarize(trades)
    print_summary(summary)

    if trades:
        save_parquet(trades, Path(args.out))
    else:
        print("No trades to save.")


if __name__ == "__main__":
    main()
