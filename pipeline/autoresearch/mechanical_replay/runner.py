"""CLI orchestrator for the mechanical 60-day replay.

Pipeline:
  1. Build the daily Phase C signal roster (roster.py).
  2. For each (ticker, date) row:
       a. Compute the ATR-14 stop from canonical daily bars truncated to
          the day BEFORE trade date (no look-ahead).
       b. Fetch minute bars via SP1's cached fetcher (one shot per row).
       c. Simulate one trade per row at 09:30 → 14:30.
  3. Join regime tag (regime_history.csv) onto each row.
  4. Write trades_with_exit.csv + engine_summary.json + the markdown one-pager.

Phase B + spread engines are out of scope for this v1 runner — only Phase C
is wired. The simulator and report layer are engine-agnostic so adding
Phase B / spread rosters in v2 is a roster.py extension only.

Usage:
  python -m pipeline.autoresearch.mechanical_replay.runner \
    --window-start 2026-02-21 --window-end 2026-04-22 \
    [--limit 5] [--no-fetch] [--out-dir <path>]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay import (
    atr,
    canonical_loader,
    constants as C,
    report,
    roster,
    simulator,
)

# SP1 fetcher reused.
try:
    from pipeline.autoresearch.phase_c_shape_audit import fetcher as sp1_fetcher
    from pipeline.autoresearch.phase_c_shape_audit import constants as sp1_const
except ImportError:
    sp1_fetcher = None
    sp1_const = None

logger = logging.getLogger("mechanical_replay")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _load_regime_history(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    date_col = next((c for c in ("date", "Date") if c in df.columns), None)
    regime_col = next((c for c in ("regime_zone", "regime", "Regime") if c in df.columns), None)
    if date_col is None or regime_col is None:
        raise ValueError(f"regime_history.csv missing required columns; saw {list(df.columns)}")
    df["date"] = pd.to_datetime(df[date_col]).dt.normalize()
    df["regime"] = df[regime_col]
    return df[["date", "regime"]]


def _stop_pct_for_row(loader: canonical_loader.CanonicalLoader, ticker: str, trade_date: pd.Timestamp,
                     side: Optional[str]) -> dict:
    if side not in ("LONG", "SHORT"):
        return {"stop_pct": C.ATR_FALLBACK_PCT, "atr_14": None, "stop_source": "fallback_no_side"}
    daily = loader.daily_bars(ticker)
    cutoff = trade_date.normalize() - pd.Timedelta(days=1)
    df_pre = daily[daily["date"] <= cutoff]
    if df_pre.empty:
        return {"stop_pct": C.ATR_FALLBACK_PCT, "atr_14": None, "stop_source": "fallback_no_history"}
    return atr.compute_stop(df_pre, side=side, profile="intraday")


def _fetch_minute_bars(ticker: str, trade_date: pd.Timestamp,
                      *, no_fetch: bool, bars_dir: Path) -> Optional[pd.DataFrame]:
    if sp1_fetcher is None:
        logger.warning("SP1 fetcher unavailable — skipping minute fetch for %s on %s", ticker, trade_date.date())
        return None
    try:
        if no_fetch:
            cache_path = sp1_fetcher._cache_path(bars_dir, ticker, trade_date.date())
            if not cache_path.exists():
                return None
            return pd.read_parquet(cache_path)
        return sp1_fetcher.fetch_minute_bars(
            ticker=ticker,
            trade_date=trade_date.date(),
            bars_dir=bars_dir,
        )
    except Exception as e:
        logger.warning("Minute-bar fetch failed for %s on %s: %s", ticker, trade_date.date(), e)
        return None


def run(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    limit: Optional[int] = None,
    no_fetch: bool = False,
    out_dir: Path = C.DATA_DIR,
    bars_dir: Optional[Path] = None,
) -> dict:
    """Execute the replay end-to-end. Returns the same dict that's written to engine_summary.json."""
    if bars_dir is None:
        bars_dir = sp1_const.BARS_DIR if sp1_const is not None else C.SP1_BARS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading canonical universe…")
    loader = canonical_loader.CanonicalLoader()
    logger.info("Canonical universe size: %d tickers (dataset_id=%s)", len(loader.universe), loader.dataset_id)

    logger.info("Building Phase C roster for window %s → %s", window_start.date(), window_end.date())
    rost = roster.build_phase_c_roster(
        loader=loader,
        window_start=window_start,
        window_end=window_end,
    )
    if rost.empty:
        logger.warning("Empty roster — nothing to simulate.")
        return {}
    if limit is not None:
        rost = rost.head(limit).copy()
    logger.info("Roster rows: %d (actual=%d, missed=%d)",
                len(rost),
                int((rost["source"] == "actual").sum()),
                int((rost["source"] == "missed").sum()))

    regime = _load_regime_history(C.REGIME_HISTORY_CSV)
    rost = rost.merge(regime, on="date", how="left")

    trades: list[dict] = []
    for _, row in rost.iterrows():
        ticker = row["ticker"]
        trade_date = pd.Timestamp(row["date"])
        side = row.get("side")

        stop = _stop_pct_for_row(loader, ticker, trade_date, side)
        bars = _fetch_minute_bars(ticker, trade_date, no_fetch=no_fetch, bars_dir=bars_dir)
        if bars is None or bars.empty:
            trade = {
                "exit_reason": "FETCH_FAILED",
                "pnl_pct": np.nan,
                "mfe_pct": np.nan,
                "entry_time": None, "exit_time": None,
                "entry_price": None, "exit_price": None,
                "side": side,
            }
        elif side not in ("LONG", "SHORT"):
            trade = {
                "exit_reason": "NO_SIDE",
                "pnl_pct": np.nan,
                "mfe_pct": np.nan,
                "entry_time": None, "exit_time": None,
                "entry_price": None, "exit_price": None,
                "side": None,
            }
        else:
            trade = simulator.simulate_one_trade(
                bars=bars,
                side=side,
                stop_pct=stop["stop_pct"],
                zcross_time=None,  # v1: z-cross channel deferred
            )

        merged = {
            "signal_id": row.get("signal_id"),
            "ticker": ticker,
            "date": trade_date,
            "source": row.get("source"),
            "regime": row.get("regime"),
            "engine": "phase_c",
            "classification": row.get("classification"),
            "side": trade.get("side") or side,
            "exit_reason": trade["exit_reason"],
            "pnl_pct": trade["pnl_pct"],
            "mfe_pct": trade.get("mfe_pct"),
            "entry_time": trade.get("entry_time"),
            "exit_time": trade.get("exit_time"),
            "entry_price": trade.get("entry_price"),
            "exit_price": trade.get("exit_price"),
            "stop_pct": stop["stop_pct"],
            "atr_14": stop["atr_14"],
            "stop_source": stop["stop_source"],
            "actual_pnl_pct": row.get("actual_pnl_pct"),
        }
        trades.append(merged)

    trades_df = pd.DataFrame(trades)
    trades_csv = out_dir / "trades_with_exit.csv"
    trades_df.to_csv(trades_csv, index=False)
    logger.info("Wrote %d trades → %s", len(trades_df), trades_csv)

    # Drop rows with no pnl from the summary math (FETCH_FAILED / NO_SIDE).
    valid = trades_df.dropna(subset=["pnl_pct"]).copy()
    summary = report.build_engine_summary(valid)
    cube = report.build_regime_cube(valid)
    checks = report.run_sanity_checks(
        trades=valid,
        total_signals_in_window=len(trades_df),
        coverage_threshold_pct=C.COVERAGE_THRESHOLD_PCT,
    )
    report.write_engine_summary(summary, out_dir / "engine_summary.json")
    report.write_one_pager(
        summary=summary,
        cube=cube,
        checks=checks,
        trades=valid,
        window_start=window_start,
        window_end=window_end,
        out_path=C.REPORT_MD,
    )
    logger.info("Per-engine summary: %s", json.dumps(summary, default=str))
    logger.info("Sanity checks: %s", json.dumps(checks, default=str))

    return {
        "summary": summary,
        "n_total": int(len(trades_df)),
        "n_valid": int(len(valid)),
        "checks": checks,
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Mechanical 60-day Phase C replay.")
    p.add_argument("--window-start", default="2026-02-24",
                  help="ISO date, default 2026-02-24 (60 calendar days before window-end).")
    p.add_argument("--window-end", default="2026-04-24",
                  help="ISO date, default 2026-04-24 (latest closed_signals coverage).")
    p.add_argument("--limit", type=int, default=None, help="Cap roster rows for smoke runs.")
    p.add_argument("--no-fetch", action="store_true",
                  help="Don't call Kite; only use cached minute bars.")
    p.add_argument("--out-dir", default=str(C.DATA_DIR), help="Output dir for CSV + JSON.")
    args = p.parse_args(argv)

    run(
        window_start=pd.Timestamp(args.window_start),
        window_end=pd.Timestamp(args.window_end),
        limit=args.limit,
        no_fetch=args.no_fetch,
        out_dir=Path(args.out_dir),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
