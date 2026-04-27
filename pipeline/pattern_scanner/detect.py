"""Hand-rolled pattern detector — 12 patterns, no external TA libraries.

Per spec §9: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Literal

import pandas as pd

from pipeline.pattern_scanner.constants import (
    BB_LENGTH,
    BB_STD,
    BB_SQUEEZE_RATIO,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
)

MIN_BARS_FOR_DETECTION: int = 60


@dataclass(frozen=True)
class PatternFlag:
    date: _date
    ticker: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    raw_features: dict


def detect_patterns_for_ticker(
    ticker: str, bars: pd.DataFrame, scan_date: _date
) -> list[PatternFlag]:
    """Detect all 12 patterns for a single ticker on scan_date.

    bars: DatetimeIndex, columns open/high/low/close, sorted ascending.
    Returns [] when: scan_date not in index, or len(bars) < MIN_BARS_FOR_DETECTION.
    """
    # Truncate to scan_date inclusive
    scan_ts = pd.Timestamp(scan_date)
    bars = bars[bars.index <= scan_ts]

    if scan_ts not in bars.index:
        return []
    if len(bars) < MIN_BARS_FOR_DETECTION:
        return []

    flags: list[PatternFlag] = []
    flags.extend(_detect_candles(ticker, bars, scan_date))
    flags.extend(_detect_bb(ticker, bars, scan_date))
    flags.extend(_detect_macd(ticker, bars, scan_date))
    return flags


# ---------------------------------------------------------------------------
# Candle pattern detectors
# ---------------------------------------------------------------------------

def _detect_candles(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    flags: list[PatternFlag] = []

    o = float(bars["open"].iloc[-1])
    h = float(bars["high"].iloc[-1])
    l = float(bars["low"].iloc[-1])
    c = float(bars["close"].iloc[-1])
    body = abs(c - o)
    rng = h - l
    if rng == 0:
        return []

    # Previous bar
    if len(bars) < 2:
        return []
    o_prev = float(bars["open"].iloc[-2])
    h_prev = float(bars["high"].iloc[-2])
    l_prev = float(bars["low"].iloc[-2])
    c_prev = float(bars["close"].iloc[-2])
    body_prev = abs(c_prev - o_prev)
    rng_prev = h_prev - l_prev

    # 5-bar look-back for trend direction (idx -6 relative to -1 = 5 bars back from last)
    lookback_close = float(bars["close"].iloc[-6]) if len(bars) >= 6 else None

    # --- BULLISH_HAMMER ---
    # Small body (top quarter of range), long lower shadow (≥2× body),
    # upper shadow ≤ body (not ≤ 0.3×body — body can be near-zero making that too strict)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    if (
        body <= 0.3 * rng
        and lower_shadow >= 2 * body
        and upper_shadow <= body + 1e-9  # upper shadow no larger than body
        and lookback_close is not None
        and c_prev < lookback_close  # downtrend: prev close below 5-bar ago close
    ):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BULLISH_HAMMER", direction="LONG",
            raw_features={
                "body_pct": float(body / rng),
                "lower_shadow_pct": float(lower_shadow / rng),
                "upper_shadow_pct": float(upper_shadow / rng),
            },
        ))

    # --- SHOOTING_STAR ---
    # Mirror of hammer: small body at bottom of range, long upper shadow (≥2× body),
    # lower shadow ≤ body
    upper_shadow_ss = h - max(o, c)
    lower_shadow_ss = min(o, c) - l
    if (
        body <= 0.3 * rng
        and upper_shadow_ss >= 2 * body
        and lower_shadow_ss <= body + 1e-9
        and lookback_close is not None
        and c_prev > lookback_close  # uptrend
    ):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="SHOOTING_STAR", direction="SHORT",
            raw_features={
                "body_pct": float(body / rng),
                "upper_shadow_pct": float(upper_shadow_ss / rng),
                "lower_shadow_pct": float(lower_shadow_ss / rng),
            },
        ))

    # --- BULLISH_ENGULFING ---
    # prev red, current green, current body engulfs prev body
    if (
        c_prev < o_prev          # prev red
        and c > o                # current green
        and c >= o_prev          # current close >= prev open
        and o <= c_prev          # current open <= prev close
    ):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BULLISH_ENGULFING", direction="LONG",
            raw_features={
                "prev_body": float(body_prev),
                "curr_body": float(body),
            },
        ))

    # --- BEARISH_ENGULFING ---
    # prev green, current red, current body engulfs prev body
    if (
        c_prev > o_prev          # prev green
        and c < o                # current red
        and o >= c_prev          # current open >= prev close
        and c <= o_prev          # current close <= prev open
    ):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BEARISH_ENGULFING", direction="SHORT",
            raw_features={
                "prev_body": float(body_prev),
                "curr_body": float(body),
            },
        ))

    # --- MORNING_STAR (3-bar) ---
    if len(bars) >= 3:
        o3 = float(bars["open"].iloc[-3])
        h3 = float(bars["high"].iloc[-3])
        l3 = float(bars["low"].iloc[-3])
        c3 = float(bars["close"].iloc[-3])
        rng3 = h3 - l3
        body3 = abs(c3 - o3)

        o2 = float(bars["open"].iloc[-2])
        h2 = float(bars["high"].iloc[-2])
        l2 = float(bars["low"].iloc[-2])
        c2 = float(bars["close"].iloc[-2])
        rng2 = h2 - l2
        body2 = abs(c2 - o2)

        # bar-1 is current bar (o, h, l, c)
        midpoint3 = (o3 + c3) / 2.0
        if (
            rng3 > 0
            and c3 < o3                         # bar-3 long red
            and body3 > 0.6 * rng3
            and rng2 > 0
            and body2 <= 0.3 * rng2             # bar-2 small body (doji)
            and c > o                           # bar-1 green
            and c >= midpoint3                  # closes above bar-3 midpoint
        ):
            flags.append(PatternFlag(
                date=scan_date, ticker=ticker,
                pattern_id="MORNING_STAR", direction="LONG",
                raw_features={
                    "bar3_body_pct": float(body3 / rng3),
                    "bar2_body_pct": float(body2 / rng2),
                    "midpoint3": float(midpoint3),
                    "close": float(c),
                },
            ))

    # --- EVENING_STAR (3-bar) ---
    if len(bars) >= 3:
        o3 = float(bars["open"].iloc[-3])
        h3 = float(bars["high"].iloc[-3])
        l3 = float(bars["low"].iloc[-3])
        c3 = float(bars["close"].iloc[-3])
        rng3 = h3 - l3
        body3 = abs(c3 - o3)

        o2 = float(bars["open"].iloc[-2])
        h2 = float(bars["high"].iloc[-2])
        l2 = float(bars["low"].iloc[-2])
        c2 = float(bars["close"].iloc[-2])
        rng2 = h2 - l2
        body2 = abs(c2 - o2)

        midpoint3 = (o3 + c3) / 2.0
        if (
            rng3 > 0
            and c3 > o3                         # bar-3 long green
            and body3 > 0.6 * rng3
            and rng2 > 0
            and body2 <= 0.3 * rng2             # bar-2 small body
            and c < o                           # bar-1 red
            and c <= midpoint3                  # closes below bar-3 midpoint
        ):
            flags.append(PatternFlag(
                date=scan_date, ticker=ticker,
                pattern_id="EVENING_STAR", direction="SHORT",
                raw_features={
                    "bar3_body_pct": float(body3 / rng3),
                    "bar2_body_pct": float(body2 / rng2),
                    "midpoint3": float(midpoint3),
                    "close": float(c),
                },
            ))

    # --- PIERCING_LINE ---
    if rng_prev > 0:
        if (
            c_prev < o_prev                     # prev long red
            and body_prev > 0.6 * rng_prev
            and o < l_prev                      # current opens below prev low
            and c > o                           # current green
            and c > (o_prev + c_prev) / 2.0    # closes above midpoint of prev body
        ):
            flags.append(PatternFlag(
                date=scan_date, ticker=ticker,
                pattern_id="PIERCING_LINE", direction="LONG",
                raw_features={
                    "prev_body_pct": float(body_prev / rng_prev),
                    "midpoint_prev": float((o_prev + c_prev) / 2.0),
                    "close": float(c),
                },
            ))

    # --- DARK_CLOUD_COVER ---
    if rng_prev > 0:
        if (
            c_prev > o_prev                     # prev long green
            and body_prev > 0.6 * rng_prev
            and o > h_prev                      # current opens above prev high
            and c < o                           # current red
            and c < (o_prev + c_prev) / 2.0    # closes below midpoint of prev body
        ):
            flags.append(PatternFlag(
                date=scan_date, ticker=ticker,
                pattern_id="DARK_CLOUD_COVER", direction="SHORT",
                raw_features={
                    "prev_body_pct": float(body_prev / rng_prev),
                    "midpoint_prev": float((o_prev + c_prev) / 2.0),
                    "close": float(c),
                },
            ))

    return flags


# ---------------------------------------------------------------------------
# Bollinger Band detector
# ---------------------------------------------------------------------------

def _detect_bb(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    close = bars["close"]
    mid = close.rolling(BB_LENGTH).mean()
    std = close.rolling(BB_LENGTH).std()
    upper = mid + BB_STD * std
    lower = mid - BB_STD * std
    width = upper - lower
    width_avg = width.rolling(BB_LENGTH).mean()

    # Need at least BB_LENGTH*2 bars for width_avg to be meaningful; but
    # we already guaranteed ≥60 bars. Still guard NaN.
    if width_avg.iloc[-2] != width_avg.iloc[-2]:  # NaN check
        return []

    flags: list[PatternFlag] = []
    squeeze_yesterday = width.iloc[-2] < width_avg.iloc[-2] * BB_SQUEEZE_RATIO
    c_today = float(close.iloc[-1])

    if squeeze_yesterday and c_today > float(upper.iloc[-1]):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BB_BREAKOUT", direction="LONG",
            raw_features={
                "close": float(c_today),
                "upper": float(upper.iloc[-1]),
                "width": float(width.iloc[-2]),
                "width_avg": float(width_avg.iloc[-2]),
            },
        ))

    if squeeze_yesterday and c_today < float(lower.iloc[-1]):
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="BB_BREAKDOWN", direction="SHORT",
            raw_features={
                "close": float(c_today),
                "lower": float(lower.iloc[-1]),
                "width": float(width.iloc[-2]),
                "width_avg": float(width_avg.iloc[-2]),
            },
        ))

    return flags


# ---------------------------------------------------------------------------
# MACD detector
# ---------------------------------------------------------------------------

def _detect_macd(ticker: str, bars: pd.DataFrame, scan_date: _date) -> list[PatternFlag]:
    close = bars["close"]
    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    line = ema_fast - ema_slow
    signal = line.ewm(span=MACD_SIGNAL, adjust=False).mean()

    diff_prev = float(line.iloc[-2]) - float(signal.iloc[-2])
    diff_curr = float(line.iloc[-1]) - float(signal.iloc[-1])

    flags: list[PatternFlag] = []

    if diff_prev <= 0 and diff_curr > 0:
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="MACD_BULL_CROSS", direction="LONG",
            raw_features={
                "macd": float(line.iloc[-1]),
                "signal": float(signal.iloc[-1]),
            },
        ))

    if diff_prev >= 0 and diff_curr < 0:
        flags.append(PatternFlag(
            date=scan_date, ticker=ticker,
            pattern_id="MACD_BEAR_CROSS", direction="SHORT",
            raw_features={
                "macd": float(line.iloc[-1]),
                "signal": float(signal.iloc[-1]),
            },
        ))

    return flags
