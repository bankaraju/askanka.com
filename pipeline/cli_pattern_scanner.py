"""CLI driver for pattern-scanner scheduled tasks. Subcommands:
- scan          → daily detect + rank + write pattern_signals_today.json
- fit           → weekly 5y fit, write pattern_stats.parquet
- paired-open   → open futures + options shadow rows for yesterday's Top-10
- paired-close  → mechanical 15:30 IST close for today's OPEN paired rows

Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §6.5, §8.3, §8.4
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date
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

log = logging.getLogger(__name__)


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


def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    """Lazy import of pipeline.kite_client.fetch_ltp — keeps tests from triggering Kite auth."""
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


def _load_signals_today(signals_path: Path = SIGNALS_TODAY) -> list[dict]:
    """Return top_10 rows from pattern_signals_today.json, or [] if absent."""
    if not signals_path.is_file():
        log.info("paired-open: %s not found, nothing to open", signals_path)
        return []
    try:
        doc = json.loads(signals_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("paired-open: cannot parse %s: %s", signals_path, exc)
        return []
    return doc.get("top_10", []) or []


def _open_options_sidecar(top_10_rows: list[dict], ltp: dict[str, float]) -> None:
    """Best-effort per-row options OPEN. Never propagates (spec §5)."""
    from pipeline import scanner_paired_shadow  # lazy import
    n_ok = 0
    n_err = 0
    for row in top_10_rows:
        ticker = row.get("ticker") or row.get("symbol", "")
        entry_px = ltp.get(ticker)
        if entry_px is None:
            log.debug("options sidecar OPEN: no LTP for %s, skipping", ticker)
            continue
        try:
            scanner_paired_shadow.open_options_pair(row, entry_px)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001 — spec §5 mandates blanket catch
            n_err += 1
            log.warning(
                "options sidecar OPEN failed for %s: %s: %s",
                row.get("signal_id"), type(exc).__name__, exc,
            )
    log.info(
        "options sidecar OPEN: %d ok, %d errors out of %d rows",
        n_ok, n_err, len(top_10_rows),
    )


def _close_options_sidecar(date_str: str) -> None:
    """Best-effort per-row options CLOSE for CLOSED futures rows. Never propagates (spec §5)."""
    from pipeline.research.scanner import live_paper
    from pipeline import scanner_paired_shadow  # lazy import
    closed_rows = [
        e for e in live_paper._load()  # noqa: SLF001
        if e.get("date") == date_str and e.get("status") == "CLOSED"
    ]
    n_ok = 0
    n_err = 0
    n_noop = 0
    for row in closed_rows:
        signal_id = row.get("signal_id", "")
        try:
            result = scanner_paired_shadow.close_options_pair(signal_id)
            if result is None:
                n_noop += 1
            else:
                n_ok += 1
        except Exception as exc:  # noqa: BLE001 — spec §5 mandates blanket catch
            n_err += 1
            log.warning(
                "options sidecar CLOSE failed for %s: %s: %s",
                signal_id, type(exc).__name__, exc,
            )
    log.info(
        "options sidecar CLOSE: %d ok, %d no-match, %d errors",
        n_ok, n_noop, n_err,
    )


def cmd_paired_open(
    date_override: str | None = None,
    signals_path: Path = SIGNALS_TODAY,
) -> int:
    """Open paired (futures + options) shadow rows for yesterday's Top-10.

    Reads pattern_signals_today.json (which is from yesterday's scan).
    For each top_10 row:
      1. Fetch live LTP for ticker via Kite.
      2. Append OPEN row to futures ledger (idempotent on signal_id).
      3. Sidecar: per-row try/except -> options ledger.
    Returns 0 on success, 1 on hard fetch failure.

    Spec: §6.5, §8.3
    """
    from pipeline.research.scanner import live_paper

    top_10 = _load_signals_today(signals_path)
    if not top_10:
        log.info("paired-open: no top_10 rows; nothing to open")
        return 0

    tickers = [r.get("ticker") or r.get("symbol", "") for r in top_10]
    tickers = [t for t in tickers if t]
    log.info("paired-open: fetching LTP for %d tickers", len(tickers))
    ltp = _fetch_ltp(tickers)
    if not ltp and tickers:
        log.error("paired-open: LTP fetch returned nothing; aborting")
        return 1

    # Futures leg first
    n = live_paper.record_opens(top_10, ltp)
    log.info("paired-open: %d new futures OPEN rows", n)

    # Options sidecar (per-row exceptions caught inside)
    _open_options_sidecar(top_10, ltp)

    return 0


def cmd_paired_close(
    date_override: str | None = None,
) -> int:
    """Mechanical 15:30 IST close for today's OPEN paired rows.

    For each OPEN row in futures ledger (date == today):
      1. Fetch live LTP at 15:30 IST.
      2. Update futures row -> CLOSED with pnl_net via cost_model.
      3. Sidecar: per-row try/except -> close_options_pair.
    Returns 0 on success.

    Spec: §6.5, §8.4
    """
    from pipeline.research.scanner import live_paper

    date_str = date_override or _date.today().isoformat()
    ledger = live_paper._load()  # noqa: SLF001
    open_tickers = sorted(
        {e["ticker"] for e in ledger if e.get("date") == date_str and e.get("status") == "OPEN"}
    )
    if not open_tickers:
        log.info("paired-close: no OPEN entries for %s; nothing to close", date_str)
        return 0

    log.info("paired-close: fetching LTP for %d tickers at 15:30", len(open_tickers))
    ltp = _fetch_ltp(open_tickers)
    if not ltp:
        log.error("paired-close: LTP fetch returned nothing; leaving ledger untouched")
        return 1

    n = live_paper.close_at_1530(date_str, ltp)
    log.info("paired-close: %d entries transitioned OPEN -> CLOSED", n)

    # Options sidecar close
    _close_options_sidecar(date_str)

    return 0


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="cli_pattern_scanner")
    parser.add_argument("subcmd", choices=["scan", "fit", "paired-open", "paired-close"])
    parser.add_argument(
        "--date",
        default=None,
        help="Override trade date (YYYY-MM-DD). Used by paired-close.",
    )
    args = parser.parse_args(argv)
    if args.subcmd == "scan":
        cmd_scan()
    elif args.subcmd == "fit":
        cmd_fit()
    elif args.subcmd == "paired-open":
        sys.exit(cmd_paired_open(date_override=args.date))
    elif args.subcmd == "paired-close":
        sys.exit(cmd_paired_close(date_override=args.date))


if __name__ == "__main__":
    main()
