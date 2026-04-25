"""Counterfactual entry-time grid + intraday stops/trails simulator.

Spec §5.5. For each (bars, side, entry_grid) call, walks minute bars from
T_ENTRY+1 to 14:30 IST and applies the user-stated execution rules:
  STOP_LOSS_PCT = 3, TARGET_PCT = 4.5,
  TRAIL_ARM_PCT = 2, TRAIL_DROP_PCT = 1.5,
  HARD_CLOSE = 14:30.

Tie-break on a single bar: stop fires before target (conservative).
"""
from __future__ import annotations

from datetime import time, datetime
from typing import Iterable

import pandas as pd

from pipeline.autoresearch.phase_c_shape_audit import constants as C


def _signed_return(entry: float, exit_price: float, side: str) -> float:
    if entry <= 0:
        return 0.0
    raw_pct = 100.0 * (exit_price - entry) / entry
    return raw_pct if side == "LONG" else -raw_pct


def _bar_signed_extreme(open_price: float, high: float, low: float, side: str) -> tuple[float, float]:
    """Return (intra_bar_min_pnl, intra_bar_max_pnl) for the side."""
    pnl_high = _signed_return(open_price, high, side)
    pnl_low = _signed_return(open_price, low, side)
    return min(pnl_high, pnl_low), max(pnl_high, pnl_low)


def _simulate_one_entry(
    bars_after_entry: pd.DataFrame,
    entry_price: float,
    side: str,
) -> dict:
    """Walk bars_after_entry, return {pnl_pct, exit_reason, exit_minute, mfe_pct}."""
    if bars_after_entry.empty:
        return {"pnl_pct": 0.0, "exit_reason": "TIME", "exit_minute": 0, "mfe_pct": 0.0}

    mfe = 0.0
    minute = 0
    for minute, (_, bar) in enumerate(bars_after_entry.iterrows(), start=1):
        bar_min_pnl, bar_max_pnl = _bar_signed_extreme(
            entry_price, float(bar["high"]), float(bar["low"]), side
        )
        if bar_min_pnl <= -C.STOP_LOSS_PCT:
            return {
                "pnl_pct": -C.STOP_LOSS_PCT,
                "exit_reason": "STOPPED",
                "exit_minute": minute,
                "mfe_pct": mfe,
            }
        if bar_max_pnl >= C.TARGET_PCT:
            return {
                "pnl_pct": C.TARGET_PCT,
                "exit_reason": "TARGETED",
                "exit_minute": minute,
                "mfe_pct": max(mfe, bar_max_pnl),
            }
        bar_close_pnl = _signed_return(entry_price, float(bar["close"]), side)
        if bar_max_pnl > mfe:
            mfe = bar_max_pnl
        if mfe >= C.TRAIL_ARM_PCT and (mfe - bar_close_pnl) >= C.TRAIL_DROP_PCT:
            return {
                "pnl_pct": mfe - C.TRAIL_DROP_PCT,
                "exit_reason": "TRAILED",
                "exit_minute": minute,
                "mfe_pct": mfe,
            }

    last_bar = bars_after_entry.iloc[-1]
    final_pnl = _signed_return(entry_price, float(last_bar["close"]), side)
    return {
        "pnl_pct": final_pnl,
        "exit_reason": "TIME",
        "exit_minute": minute,
        "mfe_pct": max(mfe, final_pnl),
    }


def simulate_grid(
    *,
    bars: pd.DataFrame,
    side: str,
    entry_grid: Iterable[time] = C.ENTRY_GRID,
) -> dict[str, dict]:
    """Run the simulator across each grid point. Returns dict keyed by 'HH:MM'."""
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")

    times = bars["timestamp_ist"].dt.time
    out: dict[str, dict] = {}
    for t_entry in entry_grid:
        key = f"{t_entry.hour:02d}:{t_entry.minute:02d}"

        entry_idx = bars.index[times >= t_entry]
        if len(entry_idx) == 0:
            out[key] = {"pnl_pct": 0.0, "exit_reason": "NO_ENTRY", "exit_minute": 0, "mfe_pct": 0.0}
            continue

        entry_row = bars.loc[entry_idx[0]]
        entry_price = float(entry_row["close"])
        after = bars.loc[entry_idx[0] + 1:]
        after = after[after["timestamp_ist"].dt.time <= C.HARD_CLOSE]
        out[key] = _simulate_one_entry(after, entry_price, side)
    return out
