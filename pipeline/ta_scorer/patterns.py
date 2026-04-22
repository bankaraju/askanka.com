"""Classic candlestick pattern detection. All functions accept mapping-like
rows with keys: open, high, low, close.

v1 rules are intentionally mainstream (Steve Nison / standard TA textbooks).
No ATR normalization — tuning knobs are exposed via kwargs.
"""
from __future__ import annotations
from typing import Mapping


def _body(row: Mapping) -> float:
    return abs(row["close"] - row["open"])


def _range(row: Mapping) -> float:
    return max(1e-9, row["high"] - row["low"])


def is_doji(row: Mapping, body_frac_max: float = 0.1) -> bool:
    """Body ≤ body_frac_max of the total range."""
    return _body(row) / _range(row) <= body_frac_max


def is_hammer(row: Mapping, body_frac_max: float = 0.35,
               lower_shadow_min: float = 2.0) -> bool:
    """Small body near top; lower shadow ≥ lower_shadow_min × body.
    Upper shadow small (≤ body)."""
    body = max(1e-9, _body(row))
    upper = row["high"] - max(row["open"], row["close"])
    lower = min(row["open"], row["close"]) - row["low"]
    return (body / _range(row) <= body_frac_max
            and lower >= lower_shadow_min * body
            and upper <= body)


def is_shooting_star(row: Mapping, body_frac_max: float = 0.35,
                      upper_shadow_min: float = 2.0) -> bool:
    """Mirror of hammer: small body near bottom; long upper shadow."""
    body = max(1e-9, _body(row))
    upper = row["high"] - max(row["open"], row["close"])
    lower = min(row["open"], row["close"]) - row["low"]
    return (body / _range(row) <= body_frac_max
            and upper >= upper_shadow_min * body
            and lower <= body)


def is_bullish_engulfing(prev: Mapping, cur: Mapping) -> bool:
    """Prev is red (close<open); cur is green (close>open) and
    cur body fully engulfs prev body."""
    prev_red = prev["close"] < prev["open"]
    cur_green = cur["close"] > cur["open"]
    engulfs = cur["open"] <= prev["close"] and cur["close"] >= prev["open"]
    return prev_red and cur_green and engulfs


def is_bearish_engulfing(prev: Mapping, cur: Mapping) -> bool:
    """Prev is green (close>open); cur is red (close<open) and
    cur body fully engulfs prev body."""
    prev_green = prev["close"] > prev["open"]
    cur_red = cur["close"] < cur["open"]
    engulfs = cur["open"] >= prev["close"] and cur["close"] <= prev["open"]
    return prev_green and cur_red and engulfs
