import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import data_audit as DA


def _frame(rows):
    return pd.DataFrame(rows).set_index(pd.to_datetime([r["Date"] for r in rows])).drop(columns=["Date"])


def test_missing_bars_detected_when_gap_in_trading_dates():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        # missing 2025-01-02 (business day)
        {"Date": "2025-01-03", "Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000},
    ]
    report = DA.audit_ticker("TEST", _frame(rows), business_days=pd.bdate_range("2025-01-01", "2025-01-03"))
    assert report["missing_bar_count"] == 1


def test_duplicate_timestamps_detected():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
    ]
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.bdate_range("2025-01-01", "2025-01-01"))
    assert report["duplicate_timestamp_count"] == 1


def test_stale_quote_detected_when_ohlc_unchanged_for_many_bars():
    rows = []
    for i, d in enumerate(pd.bdate_range("2025-01-01", periods=10)):
        rows.append({"Date": d.strftime("%Y-%m-%d"), "Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 1000})
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.DatetimeIndex(df.index), stale_run_min=3)
    assert report["stale_quote_count"] == 10  # all 10 bars form one run >= 3


def test_zero_or_negative_price_flagged():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        {"Date": "2025-01-02", "Open": 0, "High": 0, "Low": 0, "Close": 0, "Volume": 1000},
    ]
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    df = df.drop(columns=["Date"])
    report = DA.audit_ticker("TEST", df, business_days=pd.DatetimeIndex(df.index))
    assert report["zero_or_negative_price_count"] == 1


def test_aggregate_classifies_clean():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 5},
                  "B": {"total_bars": 1000, "impaired_bars": 3}}
    agg = DA.aggregate(per_ticker)
    assert agg["impaired_pct"] == pytest.approx(0.4, abs=0.01)
    assert agg["classification"] == "CLEAN"


def test_aggregate_classifies_impaired():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 15},
                  "B": {"total_bars": 1000, "impaired_bars": 15}}
    agg = DA.aggregate(per_ticker)
    assert agg["classification"] == "DATA-IMPAIRED"


def test_aggregate_classifies_auto_fail():
    per_ticker = {"A": {"total_bars": 1000, "impaired_bars": 40}}
    agg = DA.aggregate(per_ticker)
    assert agg["classification"] == "AUTO-FAIL"
