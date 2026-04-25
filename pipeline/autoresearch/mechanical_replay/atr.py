"""14-day ATR + per-side stop percent, mirroring live engine intent.

Live intent (per pipeline/break_signal_generator.py:143-149):
    Phase C is intraday. Use 1.0× ATR with abs cap at 3.5% so a high-vol
    name doesn't show a -8% stop that can't possibly trigger inside the
    5-hour horizon.

This module computes ATR off canonical daily bars (so the replay has
clean point-in-time data) and applies the same cap.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C


def _true_range(df: pd.DataFrame) -> pd.Series:
    """TR = max(H - L, |H - prev_C|, |L - prev_C|). First row is NaN by definition."""
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    return pd.concat([
        (h - l).abs(),
        (h - prev_c).abs(),
        (l - prev_c).abs(),
    ], axis=1).max(axis=1)


def _atr(df: pd.DataFrame, window: int = C.ATR_LOOKBACK) -> Optional[float]:
    """Simple mean of last `window` true ranges. None if insufficient bars."""
    if len(df) < window + 1:
        return None
    tr = _true_range(df)
    return float(tr.tail(window).mean())


def compute_stop(
    df: pd.DataFrame,
    *,
    side: Literal["LONG", "SHORT"],
    profile: Literal["intraday", "overnight"] = "intraday",
) -> Dict[str, Any]:
    """Return {stop_pct, atr_14, stop_source} for a single-ticker trade.

    `df` must have columns date / open / high / low / close, sorted ascending.
    Compute uses bars up to and including the last row in df — the caller is
    responsible for slicing to the entry-day-prior history (no look-ahead).
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"invalid side: {side}")
    if profile == "intraday":
        mult = C.ATR_MULT_INTRADAY
    elif profile == "overnight":
        mult = C.ATR_MULT_OVERNIGHT
    else:
        raise ValueError(f"invalid profile: {profile}")

    a = _atr(df, window=C.ATR_LOOKBACK)
    if a is None or a <= 0:
        return {
            "stop_pct": C.ATR_FALLBACK_PCT,
            "atr_14": None,
            "stop_source": "fallback",
        }

    last_close = float(df["close"].iloc[-1])
    if last_close <= 0:
        return {
            "stop_pct": C.ATR_FALLBACK_PCT,
            "atr_14": a,
            "stop_source": "fallback",
        }

    raw_pct = (mult * a) / last_close * 100.0  # always positive
    capped = raw_pct > C.ATR_MAX_ABS_PCT
    final_pct = min(raw_pct, C.ATR_MAX_ABS_PCT)

    # Both LONG and SHORT report negative stop_pct (it's a loss).
    stop_pct = -final_pct

    suffix = "_capped" if capped else ""
    return {
        "stop_pct": round(stop_pct, 3),
        "atr_14": round(a, 4),
        "stop_source": f"atr_14_{profile}{suffix}",
    }
