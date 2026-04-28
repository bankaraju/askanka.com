"""Tests exit_engine.py — ATR(14)*2 protective stop + 14:30 mechanical exit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pipeline.research.intraday_v1 import exit_engine

IST = timezone(timedelta(hours=5, minutes=30))


def _atr_history(close_base=100.0, atr=2.0, n=15):
    rows = []
    for i in range(n):
        rows.append({
            "date": f"2026-04-{1+i:02d}",
            "high":  close_base + atr,
            "low":   close_base - atr,
            "close": close_base,
        })
    return pd.DataFrame(rows)


def test_atr14_computation():
    df = _atr_history()
    atr = exit_engine.compute_atr14(df)
    # H-L = 2.0+2.0 = 4.0 every day → ATR-14 = 4.0
    assert abs(atr - 4.0) < 1e-6


def test_long_position_stops_when_low_breaches():
    entry_price = 100.0
    atr = 4.0
    direction = "LONG"
    minute_bars = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-04-25 09:35", "2026-04-25 09:40", "2026-04-25 09:45"
        ]).tz_localize("Asia/Kolkata"),
        "low":  [98.0, 95.0, 91.0],     # third bar breaches stop
        "high": [101.0, 100.0, 99.0],
        "close":[99.5, 97.0, 92.0],
    })
    result = exit_engine.evaluate_stops(
        entry_price=entry_price, atr=atr, direction=direction,
        minute_bars=minute_bars,
    )
    # Stop = entry - 2*ATR = 100 - 8 = 92.0; bar low 91.0 < 92.0 → STOP
    assert result["status"] == "STOPPED"
    assert result["exit_price"] == pytest.approx(92.0)


def test_long_position_holds_when_no_breach():
    entry_price = 100.0
    atr = 4.0
    direction = "LONG"
    minute_bars = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-04-25 09:35", "2026-04-25 10:00"
        ]).tz_localize("Asia/Kolkata"),
        "low":  [98.0, 96.0],
        "high": [101.0, 99.0],
        "close":[99.5, 98.0],
    })
    result = exit_engine.evaluate_stops(
        entry_price=entry_price, atr=atr, direction=direction,
        minute_bars=minute_bars,
    )
    assert result["status"] == "OPEN"


def test_short_position_stops_when_high_breaches():
    entry_price = 100.0
    atr = 4.0
    direction = "SHORT"
    minute_bars = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-04-25 10:00", "2026-04-25 10:30"
        ]).tz_localize("Asia/Kolkata"),
        "low":  [99.0, 100.0],
        "high": [101.0, 110.0],   # 110 > 108 stop
        "close":[100.0, 109.0],
    })
    result = exit_engine.evaluate_stops(
        entry_price=entry_price, atr=atr, direction=direction,
        minute_bars=minute_bars,
    )
    # Stop = entry + 2*ATR = 100 + 8 = 108
    assert result["status"] == "STOPPED"
    assert result["exit_price"] == pytest.approx(108.0)


def test_mechanical_1430_exit():
    eval_t = datetime.fromisoformat("2026-04-25T14:30:00+05:30")
    last_close = 105.0
    out = exit_engine.mechanical_exit(eval_t, last_close)
    assert out["status"] == "CLOSED"
    assert out["exit_price"] == 105.0
    assert out["exit_reason"] == "TIME_STOP"


def test_mechanical_exit_rejects_before_1430():
    eval_t = datetime.fromisoformat("2026-04-25T13:00:00+05:30")
    with pytest.raises(exit_engine.ExitTimingError):
        exit_engine.mechanical_exit(eval_t, 100.0)
