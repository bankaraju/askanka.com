"""Tests for pipeline.research.phase_c_minute.replay (pure logic, no I/O)."""
from __future__ import annotations

import pytest

from pipeline.research.phase_c_minute import replay as r


# ---- snapshot_times ---------------------------------------------------------

def test_snapshot_times_starts_at_0930_ends_at_1400():
    times = r.snapshot_times()
    assert times[0] == "09:30:00"
    assert times[-1] == "14:00:00"


def test_snapshot_times_15min_intervals():
    times = r.snapshot_times()
    # 09:30 -> 14:00 = 4.5h = 270 min, divided by 15 = 18 intervals = 19 snaps
    assert len(times) == 19


def test_snapshot_times_all_aligned_to_quarter_hour():
    for t in r.snapshot_times():
        h, m, s = t.split(":")
        assert int(s) == 0
        assert int(m) % 15 == 0


# ---- _classify --------------------------------------------------------------

def test_classify_below_threshold_returns_not_a_break():
    assert r._classify(z=2.0, expected=0.01, actual=0.005) == "NOT_A_BREAK"


def test_classify_lag_when_under_shooting_same_direction():
    # Expected +1%, actual +0.3%, z >= 4 -> LAG
    assert r._classify(z=4.5, expected=0.01, actual=0.003) == "OPPORTUNITY_LAG"


def test_classify_overshoot_when_over_shooting_same_direction():
    # Expected +1%, actual +5%, z >= 4 -> OVERSHOOT
    assert r._classify(z=5.0, expected=0.01, actual=0.05) == "OPPORTUNITY_OVERSHOOT"


def test_classify_opposite_sign_is_possible_opportunity():
    # Expected +1%, actual -0.5%, z >= 4 -> POSSIBLE_OPPORTUNITY
    assert r._classify(z=4.0, expected=0.01, actual=-0.005) == "POSSIBLE_OPPORTUNITY"


def test_classify_zero_actual_uncertain():
    assert r._classify(z=4.0, expected=0.01, actual=0.0) == "UNCERTAIN"


# ---- _direction_from_expected -----------------------------------------------

def test_direction_long_when_expected_positive():
    assert r._direction_from_expected(0.5) == "LONG"


def test_direction_short_when_expected_negative():
    assert r._direction_from_expected(-0.5) == "SHORT"


def test_direction_none_when_expected_zero():
    assert r._direction_from_expected(0.0) is None


# ---- compute_signal_at_snapshot ----------------------------------------------

def test_compute_signal_lag_records_trade_rec_long():
    seen: set[str] = set()
    # std=0.005 (≈50 bps daily) — realistic; std<=0.001 collapses _z_score to 0
    sig = r.compute_signal_at_snapshot(
        date="2025-06-01", snap_time_ist="11:00:00", ticker="HDFCBANK",
        regime="NEUTRAL", sector="Banks",
        snap_px=1003.0, prev_close=1000.0,
        profile_expected=0.025, profile_std=0.005,
        seen_today=seen,
    )
    # intraday_ret = 0.003, z = (0.003 - 0.025)/0.005 = -4.4 -> |z|>=4
    # both positive (expected, actual), actual < expected -> LAG -> LONG
    assert sig is not None
    assert sig.classification == "OPPORTUNITY_LAG"
    assert sig.trade_rec == "LONG"
    assert sig.status == "OPEN"
    assert "HDFCBANK" in seen


def test_compute_signal_dedup_marks_second_as_duplicate():
    seen: set[str] = {"HDFCBANK"}
    sig = r.compute_signal_at_snapshot(
        date="2025-06-01", snap_time_ist="11:30:00", ticker="HDFCBANK",
        regime="NEUTRAL", sector="Banks",
        snap_px=1003.0, prev_close=1000.0,
        profile_expected=0.025, profile_std=0.005,
        seen_today=seen,
    )
    assert sig is not None
    assert sig.status == "DUPLICATE_DAY_TICKER"


def test_compute_signal_returns_none_below_threshold():
    seen: set[str] = set()
    sig = r.compute_signal_at_snapshot(
        date="2025-06-01", snap_time_ist="10:00:00", ticker="X",
        regime="NEUTRAL", sector=None,
        snap_px=1001.0, prev_close=1000.0,
        profile_expected=0.005, profile_std=0.005,
        seen_today=seen,
    )
    # intraday_ret = 0.001, z = (0.001 - 0.005)/0.005 = -0.8 -> below threshold
    assert sig is None


def test_compute_signal_zero_prev_close_returns_none():
    seen: set[str] = set()
    sig = r.compute_signal_at_snapshot(
        date="2025-06-01", snap_time_ist="10:00:00", ticker="X",
        regime="NEUTRAL", sector=None, snap_px=100.0, prev_close=0.0,
        profile_expected=0.005, profile_std=0.001, seen_today=seen,
    )
    assert sig is None


# ---- simulate_exit ----------------------------------------------------------

def _bars(times_pxs: list[tuple[str, float]]) -> list[dict]:
    return [
        {"time": t, "open": px, "high": px, "low": px, "close": px}
        for t, px in times_pxs
    ]


def test_simulate_exit_long_time_stop():
    bars = _bars([("11:00:00", 100.0), ("13:00:00", 102.0), ("14:30:00", 105.0)])
    px, reason, t = r.simulate_exit(bars, "11:00:00", "LONG", 100.0, 1.0)
    assert reason == "TIME_STOP"
    assert px == pytest.approx(105.0)
    assert t == "14:30:00"


def test_simulate_exit_long_atr_stop_fires_when_low_breaches():
    bars = [
        {"time": "11:00:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"time": "11:30:00", "open": 100.0, "high": 100.0, "low": 95.0, "close": 95.0},
        {"time": "14:30:00", "open": 95.0, "high": 95.0, "low": 95.0, "close": 95.0},
    ]
    # ATR=2, stop_dist=4, LONG stop=96
    px, reason, t = r.simulate_exit(bars, "11:00:00", "LONG", 100.0, 2.0)
    assert reason == "ATR_STOP"
    assert px == pytest.approx(96.0)
    assert t == "11:30:00"


def test_simulate_exit_short_atr_stop_fires_when_high_breaches():
    bars = [
        {"time": "11:00:00", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"time": "12:00:00", "open": 100.0, "high": 105.0, "low": 100.0, "close": 105.0},
        {"time": "14:30:00", "open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0},
    ]
    px, reason, t = r.simulate_exit(bars, "11:00:00", "SHORT", 100.0, 2.0)
    assert reason == "ATR_STOP"
    assert px == pytest.approx(104.0)
    assert t == "12:00:00"


def test_simulate_exit_no_atr_falls_back_to_time_stop():
    bars = _bars([("11:00:00", 100.0), ("14:30:00", 110.0)])
    px, reason, t = r.simulate_exit(bars, "11:00:00", "LONG", 100.0, None)
    assert reason == "TIME_STOP"
    assert px == 110.0


def test_simulate_exit_no_data_returns_entry():
    bars = _bars([("09:15:00", 100.0)])
    px, reason, t = r.simulate_exit(bars, "11:00:00", "LONG", 100.0, 2.0)
    assert reason == "NO_DATA"
    assert px == 100.0


# ---- realize_pnl ------------------------------------------------------------

def test_realize_pnl_long_positive_when_exit_higher():
    assert r.realize_pnl("LONG", 100.0, 102.0) == pytest.approx(0.02)


def test_realize_pnl_short_positive_when_exit_lower():
    assert r.realize_pnl("SHORT", 100.0, 98.0) == pytest.approx(0.02)


def test_realize_pnl_long_negative_when_exit_lower():
    assert r.realize_pnl("LONG", 100.0, 98.0) == pytest.approx(-0.02)
