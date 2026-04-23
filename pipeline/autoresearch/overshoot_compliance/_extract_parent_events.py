"""One-off extract: reproduce Steps 1-4b of the H-2026-04-23-001 compliance
runner and write events.json into the existing artifact directory, without
perturbing any other file.

The parent compliance run at
  pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/
did not materialize events.json (the runner built events in-memory before the
events.json writer was added in Task 10 Part A).  Rerunning the full pipeline
would rewrite every artifact in that directory.  Instead, this script
deterministically re-executes only the event-building steps with the same
seed (42) and default params, then writes events.json alongside the existing
artifacts.

Schema derivation for slice-runner compatibility:
  classify_events() emits {ticker, date, z, today_resid, today_ret,
  next_resid, next_ret}.  filter_events_by_geometry() expects
  {expected_return_pct, actual_return_pct}.

  residual = actual - expected (see reverse_regime_breaks.py line 129 and
  overshoot_reversion_backtest.py line 153).  Therefore:
      actual_return_pct   = today_ret     (already in percent)
      expected_return_pct = today_ret - today_resid

Usage:
  PYTHONPATH=. python -m pipeline.autoresearch.overshoot_compliance._extract_parent_events
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_reversion_backtest import (
    classify_events,
    compute_residuals,
    load_price_panel,
    load_sector_map,
)
from pipeline.autoresearch.overshoot_compliance import data_audit, execution_window

_REPO = Path(__file__).resolve().parents[3]
_FNO_DIR = _REPO / "pipeline" / "data" / "fno_historical"
_PARENT_DIR = (
    _REPO
    / "pipeline"
    / "autoresearch"
    / "results"
    / "compliance_H-2026-04-23-001_20260423-150125"
)
_EXECUTION_MODE = "MODE_A"
_EXPECTED_ROWS = 14_950  # approximate, per FDR analysis doc
_TOLERANCE_PCT = 10.0    # abort if off by more than 10%


def _build_parent_events() -> pd.DataFrame:
    """Reproduce Steps 1-4b of runner.main() deterministically.

    Returns the window=20 events DataFrame with derived
    expected_return_pct / actual_return_pct columns attached.
    """
    np.random.seed(42)

    sector_of = load_sector_map()
    tickers = sorted(sector_of.keys())
    closes = load_price_panel(tickers)
    if closes.empty:
        raise RuntimeError("Price panel is empty — cannot rebuild parent events")

    # Rebuild the flagged-dates map exactly as runner.main does so the
    # raw-bar canonicity gate matches the original run.
    ticker_frames: dict[str, pd.DataFrame] = {}
    for t in tickers:
        p = _FNO_DIR / f"{t}.csv"
        if not p.exists():
            continue
        df = (
            pd.read_csv(p, parse_dates=["Date"])
            .sort_values("Date")
            .drop_duplicates("Date", keep="last")
            .set_index("Date")
        )
        ticker_frames[t] = df

    long_hist_dates: set[pd.Timestamp] = set()
    for t, df in ticker_frames.items():
        if len(df) >= 1000:
            long_hist_dates.update(pd.DatetimeIndex(df.index).normalize())
    if long_hist_dates:
        bdays = pd.DatetimeIndex(sorted(long_hist_dates))
    else:
        bdays = pd.bdate_range(closes.index.min(), closes.index.max())

    flagged_by_ticker: dict[str, dict] = {}
    for t, df in ticker_frames.items():
        flagged_by_ticker[t] = execution_window.build_flagged_dates(t, df, bdays)

    # Step 4 - window=20 only (we don't need 15/25 for events.json).
    _, resids, zs = compute_residuals(closes, sector_of)
    returns = closes.pct_change() * 100
    ev_list = classify_events(returns, resids, zs)
    ev_df = pd.DataFrame(ev_list)
    if ev_df.empty:
        return ev_df
    ev_df["direction"] = np.where(ev_df["z"] > 0, "UP", "DOWN")

    # Step 4b - raw-bar canonicity gate.
    valid_rows: list[int] = []
    for idx, row in ev_df.iterrows():
        audit = {"flagged_dates": flagged_by_ticker.get(row["ticker"], {})}
        valid, _reasons = execution_window.is_tradeable(
            row["ticker"], row["date"], _EXECUTION_MODE, audit,
        )
        if valid:
            valid_rows.append(idx)
    ev_df = ev_df.loc[valid_rows].reset_index(drop=True)

    # Derive the columns the slice filter expects.
    # actual_return_pct = today_ret (percent daily return at event date)
    # expected_return_pct = today_ret - today_resid (residual = actual - expected)
    ev_df["actual_return_pct"] = ev_df["today_ret"].astype(float)
    ev_df["expected_return_pct"] = (
        ev_df["today_ret"].astype(float) - ev_df["today_resid"].astype(float)
    )

    return ev_df


def main() -> int:
    if not _PARENT_DIR.exists():
        print(f"ERROR: parent compliance dir not found: {_PARENT_DIR}", file=sys.stderr)
        return 2

    events = _build_parent_events()
    n = len(events)

    # Sanity check: row count must be within tolerance of documented ~14,950.
    if n == 0:
        print("ERROR: zero events produced — aborting", file=sys.stderr)
        return 3
    delta_pct = abs(n - _EXPECTED_ROWS) / _EXPECTED_ROWS * 100.0
    if delta_pct > _TOLERANCE_PCT:
        print(
            f"ERROR: row count {n} deviates {delta_pct:.1f}% from expected "
            f"{_EXPECTED_ROWS} (tolerance {_TOLERANCE_PCT}%); aborting",
            file=sys.stderr,
        )
        return 4

    out_path = _PARENT_DIR / "events.json"
    events.to_json(out_path, orient="records", date_format="iso", indent=2)

    print(f"Wrote {out_path}")
    print(f"  rows:    {n} (expected ~{_EXPECTED_ROWS}, delta {delta_pct:.2f}%)")
    print(f"  columns: {list(events.columns)}")
    print(f"  first:   {events.iloc[0].to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
