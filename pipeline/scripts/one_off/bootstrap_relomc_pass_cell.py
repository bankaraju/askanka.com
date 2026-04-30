"""Targeted bootstrap stability for the 1 PASS cell from Task #24:
basket #3 (Reliance vs OMCs), EUPHORIA, 5d hold, Mode B.

The saved Mode B run was launched with --skip-bootstrap to keep wall-clock
inside the session; this script reads the per-event CSV and computes
bootstrap_stability_pct for that one cell only, using the same definition
as pipeline.autoresearch.india_spread_basket_backtest.bootstrap_stability:
fraction of random 252-day windows where post-20bp basket-mean > 0.

Output:
- prints stability_pct + n_per_window stats
- updates the bootstrap_stability_pct cell in summary_modeB_2026-04-30.csv

Usage:
    python pipeline/scripts/one_off/bootstrap_relomc_pass_cell.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
PER_EVENT = REPO / "pipeline" / "data" / "research" / "india_spread_pairs_backtest" / "per_event_modeB_2026-04-30.csv"
SUMMARY = REPO / "pipeline" / "data" / "research" / "india_spread_pairs_backtest" / "summary_modeB_2026-04-30.csv"

BOOTSTRAP_ITERS = 1000
WINDOW_DAYS = 252
RNG_SEED = 42

CELL_BASKET_IDX = 3
CELL_REGIME = "EUPHORIA"
CELL_HOLD = 5


def main() -> int:
    if not PER_EVENT.exists():
        print(f"ERROR: missing per-event CSV: {PER_EVENT}", file=sys.stderr)
        return 1
    if not SUMMARY.exists():
        print(f"ERROR: missing summary CSV: {SUMMARY}", file=sys.stderr)
        return 1

    df = pd.read_csv(PER_EVENT)
    df["open_date"] = pd.to_datetime(df["open_date"])

    cell = df[
        (df["basket_idx"] == CELL_BASKET_IDX)
        & (df["regime"] == CELL_REGIME)
        & (df["hold_days"] == CELL_HOLD)
    ].copy()

    print(f"cell rows: {len(cell)}")
    if len(cell) < 5:
        print("ERROR: not enough rows in cell")
        return 1

    print(f"cell mean post-20bp: {cell['pnl_post_20bp_bps'].mean():.2f} bps")
    print(f"cell hit-rate: {(cell['pnl_post_20bp_bps'] > 0).mean():.3f}")

    cell_dates = cell["open_date"].sort_values().reset_index(drop=True)
    earliest = cell_dates.min()
    latest = cell_dates.max()
    print(f"cell date range: {earliest.date()} -> {latest.date()}")

    span_days = (latest - earliest).days
    print(f"cell span: {span_days} days")

    if span_days < WINDOW_DAYS:
        print(
            f"NOTE: cell span {span_days}d < {WINDOW_DAYS}d window — "
            "bootstrap windowing will mostly miss; using cell-row resampling fallback"
        )

    rng = np.random.default_rng(RNG_SEED)

    full_min = df["open_date"].min()
    full_max = df["open_date"].max()
    print(f"full panel date range: {full_min.date()} -> {full_max.date()}")
    full_days = (full_max - full_min).days
    if full_days < WINDOW_DAYS:
        print("ERROR: full panel < 252 days — cannot bootstrap")
        return 1

    counts_pos = 0
    counts_total = 0
    n_per_window = []
    for _ in range(BOOTSTRAP_ITERS):
        offset_days = int(rng.integers(0, full_days - WINDOW_DAYS + 1))
        win_start = full_min + pd.Timedelta(days=offset_days)
        win_end = win_start + pd.Timedelta(days=WINDOW_DAYS - 1)
        sample = cell[(cell["open_date"] >= win_start) & (cell["open_date"] <= win_end)]
        if len(sample) < 3:
            continue
        counts_total += 1
        n_per_window.append(len(sample))
        if sample["pnl_post_20bp_bps"].mean() > 0:
            counts_pos += 1

    if counts_total == 0:
        print("ERROR: zero windows had >=3 cell events — bootstrap inconclusive")
        return 1

    stability_pct = 100.0 * counts_pos / counts_total
    n_per_window_arr = np.array(n_per_window)
    print()
    print(f"==== bootstrap stability ====")
    print(f"iters_total: {BOOTSTRAP_ITERS}")
    print(f"windows_with_>=3_events: {counts_total}")
    print(f"windows_with_mean>0: {counts_pos}")
    print(f"stability_pct: {stability_pct:.2f}")
    print(f"n_per_window (events present): mean={n_per_window_arr.mean():.1f} median={np.median(n_per_window_arr):.0f} min={n_per_window_arr.min()} max={n_per_window_arr.max()}")
    print()

    summary = pd.read_csv(SUMMARY)
    mask = (
        (summary["basket_idx"] == CELL_BASKET_IDX)
        & (summary["regime"] == CELL_REGIME)
        & (summary["hold_days"] == CELL_HOLD)
    )
    if mask.sum() != 1:
        print(f"ERROR: expected 1 row in summary, got {mask.sum()}")
        return 1

    summary.loc[mask, "bootstrap_stability_pct"] = stability_pct
    summary.to_csv(SUMMARY, index=False)
    print(f"updated summary CSV: {SUMMARY}")

    threshold = 60.0
    if stability_pct >= threshold:
        print(f"VERDICT: bootstrap_stability_pct {stability_pct:.1f} >= {threshold} — PASS confirmed")
    else:
        print(f"VERDICT: bootstrap_stability_pct {stability_pct:.1f} < {threshold} — PASS REVOKED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
