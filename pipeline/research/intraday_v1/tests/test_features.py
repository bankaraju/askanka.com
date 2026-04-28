"""Tests features.py — six features + determinism + NaN guards."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import features

IST = timezone(timedelta(hours=5, minutes=30))


def _trading_day_minute_bars(date_str: str = "2026-04-25", n_minutes: int = 60):
    """Synthetic 1-min OHLCV from 09:15 onward."""
    start = datetime.fromisoformat(f"{date_str}T09:15:00+05:30")
    rows = []
    for i in range(n_minutes):
        ts = start + timedelta(minutes=i)
        px = 100.0 + 0.05 * i
        rows.append({
            "timestamp": ts,
            "open": px,
            "high": px + 0.2,
            "low": px - 0.2,
            "close": px + 0.1,
            "volume": 1000 + 10 * i,
        })
    return pd.DataFrame(rows)


def test_orb_15min():
    df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:30:00+05:30")
    val = features.orb_15min(df, eval_t)
    # ORB = (close at 09:29 - open at 09:15) / open at 09:15
    # open at 09:15 = 100.0; close at 09:29 = 100.0 + 0.05*14 + 0.1 = 100.8
    expected = (100.8 - 100.0) / 100.0
    assert abs(val - expected) < 1e-9


def test_orb_15min_returns_nan_when_eval_before_0930():
    df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:25:00+05:30")
    val = features.orb_15min(df, eval_t)
    assert np.isnan(val)


def test_volume_z_uses_pit_history():
    df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T10:00:00+05:30")
    history = pd.DataFrame({
        "minute_of_day_idx": list(range(46)),  # 09:15..10:00 = 46 minutes
        "mean_cum_volume_20d": [1000.0 * (i + 1) for i in range(46)],
        "std_cum_volume_20d":  [200.0] * 46,
    })
    val = features.volume_z(df, eval_t, history)
    assert np.isfinite(val)


def test_vwap_dev_finite_after_window():
    df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:45:00+05:30")
    val = features.vwap_dev(df, eval_t)
    assert np.isfinite(val)


def test_trend_slope_15min_positive_for_rising_series():
    df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:45:00+05:30")
    val = features.trend_slope_15min(df, eval_t)
    assert val > 0  # synthetic series is strictly rising


def test_rs_vs_sector():
    inst_df = _trading_day_minute_bars()
    sector_df = _trading_day_minute_bars()
    sector_df["close"] = sector_df["close"] * 1.005  # sector outperforms 0.5%
    eval_t = datetime.fromisoformat("2026-04-25T09:30:00+05:30")
    val = features.rs_vs_sector(inst_df, sector_df, eval_t)
    # Stock ret < sector ret → negative RS
    assert val < 0


def test_delta_pcr_2d():
    today_chain = {"put_oi_total_next_month": 12000, "call_oi_total_next_month": 10000}
    yesterday_chain = {"put_oi_total_next_month": 11000, "call_oi_total_next_month": 10500}
    two_days_ago_chain = {"put_oi_total_next_month": 10000, "call_oi_total_next_month": 11000}
    val = features.delta_pcr_2d(today_chain, two_days_ago_chain)
    assert val == pytest.approx(12000/10000 - 10000/11000)


def test_compute_all_returns_six_features_or_nan():
    inst_df = _trading_day_minute_bars()
    sector_df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:30:00+05:30")
    today_chain = {"put_oi_total_next_month": 12000, "call_oi_total_next_month": 10000}
    two_d_chain = {"put_oi_total_next_month": 10000, "call_oi_total_next_month": 11000}
    history = pd.DataFrame({
        "minute_of_day_idx": list(range(16)),
        "mean_cum_volume_20d": [1000.0 * (i + 1) for i in range(16)],
        "std_cum_volume_20d":  [200.0] * 16,
    })
    out = features.compute_all(
        instrument_df=inst_df,
        sector_df=sector_df,
        eval_t=eval_t,
        today_pcr=today_chain,
        two_days_ago_pcr=two_d_chain,
        volume_history=history,
    )
    assert set(out.keys()) == {
        "delta_pcr_2d", "orb_15min", "volume_z",
        "vwap_dev", "rs_vs_sector", "trend_slope_15min",
    }
    for k, v in out.items():
        assert np.isfinite(v) or np.isnan(v), f"{k} not finite or NaN: {v}"


def test_compute_all_deterministic():
    inst_df = _trading_day_minute_bars()
    sector_df = _trading_day_minute_bars()
    eval_t = datetime.fromisoformat("2026-04-25T09:30:00+05:30")
    today_chain = {"put_oi_total_next_month": 12000, "call_oi_total_next_month": 10000}
    two_d_chain = {"put_oi_total_next_month": 10000, "call_oi_total_next_month": 11000}
    history = pd.DataFrame({
        "minute_of_day_idx": list(range(16)),
        "mean_cum_volume_20d": [1000.0 * (i + 1) for i in range(16)],
        "std_cum_volume_20d":  [200.0] * 16,
    })
    a = features.compute_all(inst_df, sector_df, eval_t, today_chain, two_d_chain, history)
    b = features.compute_all(inst_df, sector_df, eval_t, today_chain, two_d_chain, history)
    for k in a:
        if np.isnan(a[k]) and np.isnan(b[k]):
            continue
        assert a[k] == b[k]
