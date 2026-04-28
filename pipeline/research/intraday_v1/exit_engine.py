"""Exit-side logic for V1 paper trades — ATR(14)*2 stop + 14:30 mechanical.

Per spec §12 / `feedback_1430_ist_signal_cutoff.md`:
- Mechanical TIME_STOP at 14:30 IST is non-negotiable.
- ATR(14)*2 protective stop fires before 14:30 if breached.
- Exit price = stop trigger (paper) when stopped; LTP at 14:30 otherwise.

This file matches the *_engine.py regex → strategy gate enforces that the
twin hypothesis-registry entries from Task 1 exist before this commit.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Dict

import pandas as pd

ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 2.0
MECHANICAL_EXIT_TIME = time(14, 30)


class ExitTimingError(RuntimeError):
    """Raised if mechanical exit is requested before 14:30 IST."""


def compute_atr14(daily_df: pd.DataFrame) -> float:
    """Wilder ATR(14) from prior 14+ daily bars (high, low, close).

    The classic formula uses true-range; for a synthetic (high-low) input
    where prior_close lies inside the bar range, TR == high - low. Both
    forms agree in the test fixture.
    """
    if len(daily_df) < ATR_PERIOD:
        raise ValueError(f"Need at least {ATR_PERIOD} daily bars for ATR-{ATR_PERIOD}, got {len(daily_df)}")
    df = daily_df.tail(ATR_PERIOD).copy()
    prev_close = df["close"].shift(1)
    df["tr"] = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["tr"] = df["tr"].fillna(df["high"] - df["low"])
    return float(df["tr"].mean())


def evaluate_stops(
    entry_price: float,
    atr: float,
    direction: str,
    minute_bars: pd.DataFrame,
) -> Dict:
    """Walk forward through minute bars; return STOPPED + exit_price if breached, else OPEN.

    direction must be 'LONG' or 'SHORT'.
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError(f"direction must be LONG or SHORT, got {direction}")
    stop_distance = ATR_STOP_MULTIPLIER * atr
    for _, bar in minute_bars.iterrows():
        if direction == "LONG":
            stop_price = entry_price - stop_distance
            if bar["low"] <= stop_price:
                return {
                    "status": "STOPPED",
                    "exit_price": stop_price,
                    "exit_timestamp": bar["timestamp"],
                    "exit_reason": "ATR_STOP",
                }
        else:  # SHORT
            stop_price = entry_price + stop_distance
            if bar["high"] >= stop_price:
                return {
                    "status": "STOPPED",
                    "exit_price": stop_price,
                    "exit_timestamp": bar["timestamp"],
                    "exit_reason": "ATR_STOP",
                }
    return {"status": "OPEN", "exit_price": None, "exit_reason": None}


def mechanical_exit(eval_t: datetime, last_close: float) -> Dict:
    """14:30 IST mechanical close. Refuses to fire before 14:30."""
    if eval_t.time() < MECHANICAL_EXIT_TIME:
        raise ExitTimingError(
            f"mechanical_exit invoked at {eval_t.time()} — before 14:30 IST cutoff"
        )
    return {
        "status": "CLOSED",
        "exit_price": last_close,
        "exit_timestamp": eval_t,
        "exit_reason": "TIME_STOP",
    }
