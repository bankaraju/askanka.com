"""Simulated-P&L label generator.

For each historical entry_date, simulate a LONG position held for up to
`horizon_days` trading days with the stop+trail hierarchy locked down in
Task B9/B10. Label y=1 if realized P&L >= win_threshold, else 0.

The stop/trail logic mirrors pipeline.signal_tracker but is inlined here
because signal_tracker expects a live-prices dict, not a historical frame.
Keeping the replay self-contained avoids coupling the label generator to
check_signal_status's I/O conventions.
"""
from __future__ import annotations
from typing import Any
import math
import pandas as pd


def _closes_after(prices_df: pd.DataFrame, entry_date: str, n_days: int) -> list[float]:
    """Return up to n_days of close prices strictly AFTER entry_date."""
    if prices_df is None or len(prices_df) == 0:
        return []
    entry_ts = pd.Timestamp(entry_date)
    sorted_df = prices_df.sort_values("date").reset_index(drop=True)
    mask = pd.to_datetime(sorted_df["date"]) > entry_ts
    return sorted_df.loc[mask, "close"].head(n_days).tolist()


def _entry_close(prices_df: pd.DataFrame, entry_date: str) -> float | None:
    if prices_df is None or len(prices_df) == 0:
        return None
    entry_ts = pd.Timestamp(entry_date)
    mask = pd.to_datetime(prices_df["date"]) <= entry_ts
    if not mask.any():
        return None
    return float(prices_df.loc[mask, "close"].iloc[-1])


def simulated_pnl_label(
    prices_df: pd.DataFrame,
    entry_date: str,
    horizon_days: int = 5,
    win_threshold: float = 0.015,
    daily_stop: float = -0.02,
    avg_favorable: float = 0.02,
    trail_arm_factor: float = 0.5,
) -> dict[str, Any] | None:
    """Return {'y': 0|1, 'realized_pct': float, 'exit_reason': str} or None."""
    entry = _entry_close(prices_df, entry_date)
    if entry is None:
        return None
    closes = _closes_after(prices_df, entry_date, horizon_days)
    if not closes:
        return None

    peak_pnl = 0.0
    peak_trail_stop = None  # monotonic ratchet per B10

    for i, c in enumerate(closes, start=1):
        pnl = (c - entry) / entry
        today_return = pnl if i == 1 else (c - closes[i - 2]) / closes[i - 2]

        if pnl > peak_pnl:
            peak_pnl = pnl

        trail_budget = avg_favorable * math.sqrt(i)
        trail_armed = peak_pnl >= trail_budget * trail_arm_factor

        if trail_armed:
            candidate_trail = peak_pnl - avg_favorable  # Constant-width trail, not growing
            peak_trail_stop = (
                candidate_trail if peak_trail_stop is None
                else max(peak_trail_stop, candidate_trail)
            )
            # Use small epsilon for floating-point comparison
            if pnl <= peak_trail_stop + 1e-10:
                # Trail fire is always a win—we're locking in planned profits
                return {"y": 1,
                        "realized_pct": pnl, "exit_reason": "trail"}
        else:
            if today_return <= daily_stop:
                return {"y": 0, "realized_pct": pnl, "exit_reason": "daily_stop"}

    # horizon timeout — close at last available bar
    final_pnl = (closes[-1] - entry) / entry
    return {"y": 1 if final_pnl >= win_threshold else 0,
            "realized_pct": final_pnl, "exit_reason": "timeout"}
