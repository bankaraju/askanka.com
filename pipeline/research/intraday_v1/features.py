"""Six intraday features per spec §3 — pure-functional, deterministic, PIT.

Each feature returns a finite float or numpy.nan. Caller is responsible for
NaN-handling at scoring time (instrument excluded with EXCLUDED=feature_nan_*).
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd


def delta_pcr_2d(today_chain: Dict, two_days_ago_chain: Dict) -> float:
    """Spec §3 feature 1.

    PCR(t, next_month) - PCR(t-2d, next_month).
    Where PCR = put_OI_total / call_OI_total on next-expiry options chain.
    """
    def _pcr(c):
        p = c.get("put_oi_total_next_month")
        ca = c.get("call_oi_total_next_month")
        if not p or not ca:
            return float("nan")
        return p / ca
    return _pcr(today_chain) - _pcr(two_days_ago_chain)


def orb_15min(df: pd.DataFrame, eval_t: datetime) -> float:
    """Spec §3 feature 2.

    (last_close in [09:15, eval_t) - open at 09:15) / open at 09:15.
    Returns NaN if eval_t < 09:30 (window not yet closed).
    """
    if eval_t.time() < pd.Timestamp("09:30:00").time():
        return float("nan")
    window = df[(df["timestamp"] >= eval_t.replace(hour=9, minute=15, second=0, microsecond=0)) &
                (df["timestamp"] < eval_t)]
    if window.empty:
        return float("nan")
    open_915 = window.iloc[0]["open"]
    last_close = window.iloc[-1]["close"]
    if not open_915 or open_915 == 0:
        return float("nan")
    return (last_close - open_915) / open_915


def volume_z(df: pd.DataFrame, eval_t: datetime, volume_history: pd.DataFrame) -> float:
    """Spec §3 feature 3.

    (cum_volume at eval_t - mu_20d_at_same_minute_of_day) / sigma_20d_at_same_minute.
    `volume_history` columns: minute_of_day_idx, mean_cum_volume_20d, std_cum_volume_20d.
    """
    window = df[(df["timestamp"] >= eval_t.replace(hour=9, minute=15, second=0, microsecond=0)) &
                (df["timestamp"] < eval_t)]
    cum_vol = float(window["volume"].sum()) if not window.empty else float("nan")
    minute_idx = (eval_t.hour - 9) * 60 + (eval_t.minute - 15)
    if minute_idx < 0:
        return float("nan")
    h = volume_history[volume_history["minute_of_day_idx"] == minute_idx]
    if h.empty:
        return float("nan")
    mu = float(h["mean_cum_volume_20d"].iloc[0])
    sigma = float(h["std_cum_volume_20d"].iloc[0])
    if sigma <= 0:
        return float("nan")
    return (cum_vol - mu) / sigma


def vwap_dev(df: pd.DataFrame, eval_t: datetime) -> float:
    """Spec §3 feature 4.

    (close at eval_t-1min - VWAP today through eval_t-1min) / VWAP.
    """
    window = df[(df["timestamp"] >= eval_t.replace(hour=9, minute=15, second=0, microsecond=0)) &
                (df["timestamp"] < eval_t)]
    if window.empty:
        return float("nan")
    px = window["close"]
    vol = window["volume"]
    if vol.sum() <= 0:
        return float("nan")
    vwap = (px * vol).sum() / vol.sum()
    last_close = px.iloc[-1]
    if vwap == 0:
        return float("nan")
    return (last_close - vwap) / vwap


def rs_vs_sector(instrument_df: pd.DataFrame, sector_df: pd.DataFrame, eval_t: datetime) -> float:
    """Spec §3 feature 5.

    (instrument_ret 09:15 → eval_t-1min) - (sector_ret 09:15 → eval_t-1min).
    """
    def _ret(d):
        w = d[(d["timestamp"] >= eval_t.replace(hour=9, minute=15, second=0, microsecond=0)) &
              (d["timestamp"] < eval_t)]
        if len(w) < 2:
            return float("nan")
        return (w.iloc[-1]["close"] - w.iloc[0]["open"]) / w.iloc[0]["open"]
    return _ret(instrument_df) - _ret(sector_df)


def trend_slope_15min(df: pd.DataFrame, eval_t: datetime) -> float:
    """Spec §3 feature 6.

    OLS slope of close prices on minute-index over [eval_t-15min, eval_t),
    normalized by close at start of window.
    """
    start = eval_t - pd.Timedelta(minutes=15)
    window = df[(df["timestamp"] >= start) & (df["timestamp"] < eval_t)]
    if len(window) < 5:
        return float("nan")
    y = window["close"].to_numpy()
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    base = y[0]
    if base == 0:
        return float("nan")
    return slope / base


def compute_all(
    instrument_df: pd.DataFrame,
    sector_df: pd.DataFrame,
    eval_t: datetime,
    today_pcr: Dict,
    two_days_ago_pcr: Dict,
    volume_history: pd.DataFrame,
) -> Dict[str, float]:
    """Composite — return all 6 features for a single (instrument, eval_t)."""
    return {
        "delta_pcr_2d":     delta_pcr_2d(today_pcr, two_days_ago_pcr),
        "orb_15min":        orb_15min(instrument_df, eval_t),
        "volume_z":         volume_z(instrument_df, eval_t, volume_history),
        "vwap_dev":         vwap_dev(instrument_df, eval_t),
        "rs_vs_sector":     rs_vs_sector(instrument_df, sector_df, eval_t),
        "trend_slope_15min": trend_slope_15min(instrument_df, eval_t),
    }
