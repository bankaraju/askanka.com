"""Compute shape features per minute-bar session and classify shape.

Spec §5.3 (features) and §5.4 (shape classes). Anchor: open of 09:15 bar.
"""
from __future__ import annotations

from datetime import time
from typing import Any

import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_shape_audit import constants as C

SHAPE_LABELS = (
    "REVERSE_V_HIGH",
    "V_LOW_RECOVERY",
    "ONE_WAY_UP",
    "ONE_WAY_DOWN",
    "CHOPPY",
)


def _validate_bars(bars: pd.DataFrame) -> str:
    if len(bars) < C.MIN_BARS_PER_SESSION:
        return "BARS_INSUFFICIENT"
    first_t = bars["timestamp_ist"].iloc[0].time()
    last_t = bars["timestamp_ist"].iloc[-1].time()
    if first_t > C.FIRST_BAR_LATEST:
        return "BARS_INSUFFICIENT"
    if last_t < C.LAST_BAR_EARLIEST:
        return "BARS_INSUFFICIENT"
    return "OK"


def _bar_at_or_after(bars: pd.DataFrame, target_time: time) -> pd.Series | None:
    """Return the first bar whose timestamp_ist.time() >= target_time, or None."""
    times = bars["timestamp_ist"].dt.time
    mask = times >= target_time
    if not mask.any():
        return None
    return bars[mask].iloc[0]


def compute_shape_features(
    bars: pd.DataFrame,
    persisted_open: float | None = None,
) -> dict[str, Any]:
    """Compute all spec §5.3 features. Returns dict with `validation` field.

    persisted_open: if supplied, the day-open from correlation_break_history.json
    used to detect OPEN_PRICE_MISMATCH per spec §3.1.
    """
    out: dict[str, Any] = {"validation": _validate_bars(bars)}
    if out["validation"] != "OK":
        return out

    open_price = float(bars["open"].iloc[0])
    if persisted_open is not None and persisted_open > 0:
        diff_pct = abs(open_price - persisted_open) / persisted_open * 100.0
        if diff_pct > C.OPEN_PRICE_MISMATCH_TOL_PCT:
            out["validation"] = "OPEN_PRICE_MISMATCH"
            out["open_price"] = open_price
            out["persisted_open"] = persisted_open
            return out

    closes = bars["close"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    minutes = (bars["timestamp_ist"] - bars["timestamp_ist"].iloc[0]).dt.total_seconds().to_numpy() / 60.0

    peak_idx = int(np.argmax(closes))
    trough_idx = int(np.argmin(closes))
    peak_price = float(closes[peak_idx])
    trough_price = float(closes[trough_idx])
    peak_minute = float(minutes[peak_idx])
    trough_minute = float(minutes[trough_idx])

    close_price = float(closes[-1])
    bar_at_1430 = _bar_at_or_after(bars, C.HARD_CLOSE)
    price_at_1430 = float(bar_at_1430["close"]) if bar_at_1430 is not None else close_price

    def pct(p: float) -> float:
        return 100.0 * (p - open_price) / open_price

    first_15 = bars[bars["timestamp_ist"].dt.time < time(9, 30)]
    first_30 = bars[bars["timestamp_ist"].dt.time < time(9, 45)]
    range_15 = (
        100.0 * (float(first_15["high"].max()) - float(first_15["low"].min())) / open_price
        if not first_15.empty else 0.0
    )
    range_30 = (
        100.0 * (float(first_30["high"].max()) - float(first_30["low"].min())) / open_price
        if not first_30.empty else 0.0
    )

    out.update({
        "open_price": open_price,
        "peak_price": peak_price,
        "peak_minute": peak_minute,
        "trough_price": trough_price,
        "trough_minute": trough_minute,
        "close_price_15_30": close_price,
        "price_at_14_30": price_at_1430,
        "peak_pct": pct(peak_price),
        "trough_pct": pct(trough_price),
        "close_pct": pct(close_price),
        "pct_at_14_30": pct(price_at_1430),
        "range_first_15min": range_15,
        "range_first_30min": range_30,
        "peak_in_first_15min": peak_minute < 15,
        "trough_in_first_15min": trough_minute < 15,
    })
    return out


def classify_shape(features_dict: dict[str, Any]) -> str:
    """Return one of SHAPE_LABELS, mutually exclusive, first-match wins.

    Spec §5.4. Returns 'INVALID' if features_dict.validation != 'OK'.
    """
    if features_dict.get("validation") != "OK":
        return "INVALID"

    peak_pct = features_dict["peak_pct"]
    trough_pct = features_dict["trough_pct"]
    close_pct = features_dict["close_pct"]
    peak_first_15 = features_dict["peak_in_first_15min"]
    trough_first_15 = features_dict["trough_in_first_15min"]

    if peak_first_15 and peak_pct >= C.PEAK_PCT_THRESHOLD and close_pct <= peak_pct / C.PEAK_HALF_GIVEBACK:
        return "REVERSE_V_HIGH"

    if trough_first_15 and trough_pct <= C.TROUGH_PCT_THRESHOLD and close_pct >= trough_pct / C.PEAK_HALF_GIVEBACK:
        return "V_LOW_RECOVERY"

    if close_pct > peak_pct - C.ONE_WAY_TOLERANCE and close_pct >= C.PEAK_PCT_THRESHOLD:
        return "ONE_WAY_UP"

    if close_pct < trough_pct + C.ONE_WAY_TOLERANCE and close_pct <= C.TROUGH_PCT_THRESHOLD:
        return "ONE_WAY_DOWN"

    return "CHOPPY"
