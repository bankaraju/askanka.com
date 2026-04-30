"""Tests for pipeline.research.phase_c_minute.corp_action_adjuster (pure logic)."""
from __future__ import annotations

import pytest

from pipeline.research.phase_c_minute import corp_action_adjuster as ca


# ---- _parse_split_ratio ------------------------------------------------------

def test_parse_2_for_1_split():
    assert ca._parse_split_ratio("2.000000/1.000000") == pytest.approx(2.0)


def test_parse_3_for_2_split():
    assert ca._parse_split_ratio("3/2") == pytest.approx(1.5)


def test_parse_5_for_1_split():
    assert ca._parse_split_ratio("5/1") == pytest.approx(5.0)


def test_parse_malformed_returns_one():
    assert ca._parse_split_ratio("garbage") == 1.0


def test_parse_zero_pre_returns_one():
    assert ca._parse_split_ratio("2/0") == 1.0


# ---- cumulative_factor -------------------------------------------------------

def test_cumulative_factor_no_splits_is_one():
    assert ca.cumulative_factor([], "2024-06-01") == 1.0


def test_cumulative_factor_before_split_uses_ratio():
    splits = [("2025-08-26", 2.0)]
    assert ca.cumulative_factor(splits, "2025-08-25") == 2.0


def test_cumulative_factor_on_split_day_no_adjust():
    splits = [("2025-08-26", 2.0)]
    assert ca.cumulative_factor(splits, "2025-08-26") == 1.0


def test_cumulative_factor_after_split_no_adjust():
    splits = [("2025-08-26", 2.0)]
    assert ca.cumulative_factor(splits, "2026-01-01") == 1.0


def test_cumulative_factor_multiple_splits_multiplies():
    # 2:1 in 2024, then 3:2 in 2025
    splits = [("2024-06-01", 2.0), ("2025-08-26", 1.5)]
    assert ca.cumulative_factor(splits, "2023-01-01") == pytest.approx(3.0)
    # Between the two splits: only the later one applies
    assert ca.cumulative_factor(splits, "2025-01-01") == pytest.approx(1.5)
    # After both
    assert ca.cumulative_factor(splits, "2025-12-31") == pytest.approx(1.0)


# ---- adjust_bars -------------------------------------------------------------

def _bars(*recs):
    return [
        {"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}
        for (t, o, h, lo, c, v) in recs
    ]


def test_adjust_bars_no_splits_passes_through():
    bars = {"2024-01-01": _bars(("09:15:00", 100.0, 105.0, 99.0, 104.0, 1000))}
    out = ca.adjust_bars(bars, [])
    assert out is bars  # pass-through, same object


def test_adjust_bars_pre_split_divided_by_factor():
    splits = [("2025-08-26", 2.0)]
    bars = {"2024-07-01": _bars(("09:30:00", 1688.0, 1700.0, 1680.0, 1695.0, 5000))}
    out = ca.adjust_bars(bars, splits)
    bar = out["2024-07-01"][0]
    assert bar["open"] == pytest.approx(844.0)
    assert bar["high"] == pytest.approx(850.0)
    assert bar["low"] == pytest.approx(840.0)
    assert bar["close"] == pytest.approx(847.5)
    # Volume scales the other way: pre-split had fewer shares, post-basis is 2x shares
    assert bar["volume"] == pytest.approx(10000)


def test_adjust_bars_post_split_unchanged():
    splits = [("2025-08-26", 2.0)]
    bars = {"2025-09-01": _bars(("09:30:00", 950.0, 960.0, 945.0, 955.0, 8000))}
    out = ca.adjust_bars(bars, splits)
    bar = out["2025-09-01"][0]
    assert bar["open"] == 950.0
    assert bar["close"] == 955.0
    assert bar["volume"] == 8000


def test_adjust_bars_does_not_mutate_input():
    splits = [("2025-08-26", 2.0)]
    bars = {"2024-07-01": _bars(("09:30:00", 1688.0, 1700.0, 1680.0, 1695.0, 5000))}
    original_close = bars["2024-07-01"][0]["close"]
    _ = ca.adjust_bars(bars, splits)
    assert bars["2024-07-01"][0]["close"] == original_close


def test_adjust_bars_handles_missing_volume():
    splits = [("2025-08-26", 2.0)]
    bars = {"2024-07-01": [{"time": "09:30:00", "open": 1688.0, "high": 1700.0,
                             "low": 1680.0, "close": 1695.0}]}
    out = ca.adjust_bars(bars, splits)
    assert out["2024-07-01"][0]["close"] == pytest.approx(847.5)


# ---- _parse_split_ratio + cumulative_factor end-to-end -----------------------

def test_real_hdfcbank_split_scenario():
    """Real-world: HDFCBANK 2:1 split on 2025-08-26.
    A 1m bar on 2024-07-01 with raw close ₹1688 should adjust to ₹844."""
    splits_raw = [{"date": "2025-08-26", "split": "2.000000/1.000000"}]
    splits = [(s["date"], ca._parse_split_ratio(s["split"])) for s in splits_raw]
    pre_split_close = 1688.0
    f = ca.cumulative_factor(splits, "2024-07-01")
    adjusted = pre_split_close / f
    assert adjusted == pytest.approx(844.0)
