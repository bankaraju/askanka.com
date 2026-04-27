"""CLI driver for pattern-scanner scheduled tasks. Subcommands:
- scan      → daily detect + rank + write pattern_signals_today.json
- fit       → weekly 5y fit, write pattern_stats.parquet

Deferred: paired-open / paired-close (Phase C helpers not yet built).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from pipeline.autoresearch.mechanical_replay.canonical_loader import CanonicalLoader
from pipeline.pattern_scanner.constants import WIN_THRESHOLD
from pipeline.pattern_scanner.runner import run_daily_scan
from pipeline.pattern_scanner.stats import fit_universe

IST = timezone(timedelta(hours=5, minutes=30))
SCANNER_DIR = Path("pipeline/data/scanner")
SIGNALS_TODAY = SCANNER_DIR / "pattern_signals_today.json"
STATS_PATH = SCANNER_DIR / "pattern_stats.parquet"
CANONICAL_V3 = Path("pipeline/data/canonical_fno_research_v3.json")


def _build_bars_loader(loader: CanonicalLoader) -> Callable[[str], "pd.DataFrame | None"]:
    """Adapt CanonicalLoader.daily_bars() to the DatetimeIndex shape that
    pattern_scanner.detect expects. Returns None on missing CSV."""
    def _load(ticker: str) -> "pd.DataFrame | None":
        try:
            df = loader.daily_bars(ticker)
        except FileNotFoundError:
            return None
        if df is None or df.empty:
            return None
        return df.set_index("date").sort_index()
    return _load


def cmd_scan(
    canonical_path: Path = CANONICAL_V3,
    stats_path: Path = STATS_PATH,
    out_path: Path = SIGNALS_TODAY,
) -> dict:
    if not stats_path.exists():
        print(f"ERROR: {stats_path} missing — run fit first", file=sys.stderr)
        sys.exit(1)
    loader = CanonicalLoader(canonical_path=canonical_path)
    universe = sorted(loader.universe)
    bars_loader = _build_bars_loader(loader)
    stats = pd.read_parquet(stats_path)
    today = datetime.now(IST).date()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return run_daily_scan(
        scan_date=today, universe=universe,
        bars_loader=bars_loader,
        stats_df=stats, out_path=out_path,
    )


def cmd_fit(
    canonical_path: Path = CANONICAL_V3,
    stats_path: Path = STATS_PATH,
    lookback_years: int = 5,
) -> pd.DataFrame:
    loader = CanonicalLoader(canonical_path=canonical_path)
    universe = sorted(loader.universe)
    bars_loader = _build_bars_loader(loader)
    today = datetime.now(IST).date()
    start = today - timedelta(days=365 * lookback_years)
    df = fit_universe(
        universe=universe, bars_loader=bars_loader,
        start=start, end=today, win_threshold=WIN_THRESHOLD,
    )
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(stats_path, index=False)
    print(f"wrote {stats_path} with {len(df)} cells")
    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli_pattern_scanner")
    parser.add_argument("subcmd", choices=["scan", "fit"])
    args = parser.parse_args(argv)
    if args.subcmd == "scan":
        cmd_scan()
    elif args.subcmd == "fit":
        cmd_fit()


if __name__ == "__main__":
    main()
