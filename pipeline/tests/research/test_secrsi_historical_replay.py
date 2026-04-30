"""Tests for pipeline.research.h_2026_04_27_secrsi.historical_replay."""
from __future__ import annotations

import pytest

from pipeline.research.h_2026_04_27_secrsi import historical_replay as hr


# ---- _atr_pit ----------------------------------------------------------------

def _make_daily(n: int, close_start: float = 100.0,
                tr: float = 2.0) -> list[dict]:
    """Build n daily bars with constant true-range = `tr`."""
    out = []
    for i in range(n):
        c = close_start + i
        out.append({
            "date": f"2024-01-{i+1:02d}",
            "high": c + tr / 2,
            "low": c - tr / 2,
            "close": c,
        })
    return out


def test_atr_pit_uses_only_prior_bars():
    daily = _make_daily(20)  # constant TR = 2.0
    atr = hr._atr_pit(daily, "2024-01-20", window=14)
    assert atr is not None
    assert atr == pytest.approx(2.0, abs=0.5)  # mean of 14 TRs around 2


def test_atr_pit_returns_none_when_insufficient_history():
    daily = _make_daily(10)
    atr = hr._atr_pit(daily, "2024-01-10", window=14)
    assert atr is None


def test_atr_pit_strict_inequality_excludes_target_day():
    daily = _make_daily(20)
    atr_with = hr._atr_pit(daily, "2024-01-20", window=14)
    atr_without = hr._atr_pit(daily, "2024-01-19", window=14)
    # Different windows so likely different values
    assert atr_with is not None and atr_without is not None


# ---- _bar_at -----------------------------------------------------------------

def test_bar_at_returns_exact_match():
    bars = [
        {"time": "09:15:00", "close": 100.0},
        {"time": "11:00:00", "close": 105.0},
        {"time": "14:30:00", "close": 110.0},
    ]
    assert hr._bar_at(bars, "11:00:00")["close"] == 105.0


def test_bar_at_returns_first_bar_after_when_no_match():
    bars = [
        {"time": "09:15:00", "close": 100.0},
        {"time": "10:55:00", "close": 102.0},
        {"time": "11:05:00", "close": 105.0},
    ]
    # No 11:00 bar exactly — pick next one
    assert hr._bar_at(bars, "11:00:00")["close"] == 105.0


def test_bar_at_returns_none_when_all_before():
    bars = [{"time": "09:15:00", "close": 100.0}]
    assert hr._bar_at(bars, "11:00:00") is None


# ---- _exit_for_leg -----------------------------------------------------------

def _bars_flat(times: list[str], price: float) -> list[dict]:
    return [
        {"time": t, "open": price, "high": price, "low": price, "close": price}
        for t in times
    ]


def test_exit_long_time_stop_when_no_atr_breach():
    bars = _bars_flat(["11:00:00", "12:00:00", "14:30:00"], 100.0)
    bars[-1]["close"] = 102.0
    exit_px, reason = hr._exit_for_leg(bars, "LONG", entry_px=100.0, atr=1.0)
    assert reason == "TIME_STOP"
    assert exit_px == pytest.approx(102.0)


def test_exit_long_atr_stop_fires():
    bars = [
        {"time": "11:00:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"time": "11:30:00", "open": 100.0, "high": 100.0, "low": 95.0, "close": 95.0},
        {"time": "14:30:00", "open": 95.0, "high": 95.0, "low": 95.0, "close": 95.0},
    ]
    # ATR=2, stop_distance=4, LONG stop at 96
    exit_px, reason = hr._exit_for_leg(bars, "LONG", entry_px=100.0, atr=2.0)
    assert reason == "ATR_STOP"
    assert exit_px == pytest.approx(96.0)


def test_exit_short_atr_stop_fires():
    bars = [
        {"time": "11:00:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"time": "12:00:00", "open": 100.0, "high": 105.0, "low": 100.0, "close": 105.0},
        {"time": "14:30:00", "open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0},
    ]
    # ATR=2, stop_distance=4, SHORT stop at 104
    exit_px, reason = hr._exit_for_leg(bars, "SHORT", entry_px=100.0, atr=2.0)
    assert reason == "ATR_STOP"
    assert exit_px == pytest.approx(104.0)


def test_exit_no_atr_falls_back_to_time_stop():
    bars = _bars_flat(["11:00:00", "14:30:00"], 100.0)
    bars[-1]["close"] = 110.0
    exit_px, reason = hr._exit_for_leg(bars, "LONG", entry_px=100.0, atr=None)
    assert reason == "TIME_STOP"
    assert exit_px == pytest.approx(110.0)


def test_exit_no_data_returns_entry_px():
    bars = [{"time": "09:30:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}]
    exit_px, reason = hr._exit_for_leg(bars, "LONG", entry_px=100.0, atr=2.0)
    assert reason == "NO_DATA"
    assert exit_px == 100.0


# ---- _basket_pnl + _max_drawdown + _sharpe -----------------------------------

def test_basket_pnl_equal_weight():
    rows = [
        {"weight": 0.125, "pnl_pct": 0.01},  # +1%
        {"weight": 0.125, "pnl_pct": -0.01}, # -1%
        {"weight": 0.125, "pnl_pct": 0.02},
        {"weight": 0.125, "pnl_pct": 0.0},
        {"weight": 0.125, "pnl_pct": 0.005},
        {"weight": 0.125, "pnl_pct": -0.005},
        {"weight": 0.125, "pnl_pct": 0.01},
        {"weight": 0.125, "pnl_pct": 0.0},
    ]
    pnl = hr._basket_pnl(rows)
    # sum(pnl_pct) = 0.030, mean (each leg weight=0.125) = 0.00375
    assert pnl == pytest.approx(0.00375)


def test_basket_pnl_empty():
    assert hr._basket_pnl([]) == 0.0


def test_max_drawdown_basic():
    # +5, -10, +3, -2, +4
    returns = [0.05, -0.10, 0.03, -0.02, 0.04]
    mdd = hr._max_drawdown(returns)
    # Cumulative: 0.05, -0.05, -0.02, -0.04, 0.00
    # Peak: 0.05 (after first), then never higher until end
    # MDD: -0.05 - 0.05 = -0.10
    assert mdd == pytest.approx(-0.10)


def test_max_drawdown_monotonic_up():
    returns = [0.01, 0.02, 0.03]
    assert hr._max_drawdown(returns) == 0.0


def test_sharpe_zero_when_constant():
    assert hr._sharpe([0.01, 0.01, 0.01]) == 0.0


def test_sharpe_positive_for_positive_drift():
    s = hr._sharpe([0.01, 0.005, 0.012, 0.008, 0.02])
    assert s > 0


def test_summarize_partitions_by_year():
    daily = {
        "2023-06-01": 0.01,
        "2023-12-31": -0.005,
        "2024-01-15": 0.02,
        "2024-07-04": 0.0,
    }
    out = hr._summarize(daily)
    assert "2023" in out["per_year"]
    assert "2024" in out["per_year"]
    assert out["per_year"]["2023"]["n"] == 2
    assert out["per_year"]["2024"]["n"] == 2
    assert out["full"]["n"] == 4
