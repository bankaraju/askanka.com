from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.data_audit import audit_run_data


def test_audit_counts_zero_volume_and_stale():
    df = pd.DataFrame({
        "ticker": ["A","A","A","A"],
        "trade_date": [date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15","2026-03-03 09:16",
            "2026-03-03 09:17","2026-03-03 09:18",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100,100,100,101], "high":[100,100,100,101],
        "low":[100,100,100,101], "close":[100,100,100,101],
        "volume":[10, 0, 0, 5],
    })
    rep = audit_run_data(df)
    assert rep["zero_volume_bar_count"] == 2
    assert rep["stale_quote_count_min3"] == 1   # 3 consecutive identical OHLC bars
    # 3 impaired bars (2 zero-volume + 1 stale-tail) out of 4 → 75%
    assert rep["bad_data_pct"] == pytest.approx(75.0)


def test_audit_handles_empty_frame():
    df = pd.DataFrame(columns=["ticker","trade_date","timestamp","open","high","low","close","volume"])
    rep = audit_run_data(df)
    assert rep["n_rows"] == 0
    assert rep["zero_volume_bar_count"] == 0
    assert rep["stale_quote_count_min3"] == 0
    assert rep["bad_data_pct"] == 0.0
    assert rep["tag"] == "CLEAN"


def test_audit_isolates_stale_runs_per_ticker():
    """Stale runs in ticker A must not bleed into ticker B's count."""
    df = pd.DataFrame({
        "ticker": ["A","A","A","B","B","B"],
        "trade_date": [date(2026,3,3)]*6,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15","2026-03-03 09:16","2026-03-03 09:17",
            "2026-03-03 09:18","2026-03-03 09:19","2026-03-03 09:20",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100,100,100,200,201,202],
        "high":[100,100,100,200,201,202],
        "low":[100,100,100,200,201,202],
        "close":[100,100,100,200,201,202],
        "volume":[1,1,1,1,1,1],
    })
    rep = audit_run_data(df)
    # A: 3 identical bars → 1 stale-tail. B: all-different → 0 stale-tails.
    assert rep["stale_quote_count_min3"] == 1


def test_audit_tag_thresholds():
    """1% boundary stays CLEAN; >1% flips to DATA-IMPAIRED."""
    # Build a 100-row frame with exactly 1 zero-volume bar → 1.0% impaired.
    df = pd.DataFrame({
        "ticker": ["A"]*100,
        "trade_date": [date(2026,3,3)]*100,
        "timestamp": pd.date_range("2026-03-03 09:15", periods=100, freq="min", tz="Asia/Kolkata"),
        "open":  [100.0+i*0.1 for i in range(100)],
        "high":  [100.0+i*0.1 for i in range(100)],
        "low":   [100.0+i*0.1 for i in range(100)],
        "close": [100.0+i*0.1 for i in range(100)],
        "volume":[1]*99 + [0],  # 1 zero-volume bar
    })
    rep = audit_run_data(df)
    assert rep["bad_data_pct"] == pytest.approx(1.0)
    assert rep["tag"] == "CLEAN"  # boundary: <=1% is CLEAN
