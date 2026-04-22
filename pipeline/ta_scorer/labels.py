"""1D simulated-PnL label for RELIANCE TA scorer. Minimal vs FCS labels:
no trail arming — daily horizon too short. Pure close-to-close with a daily
stop (≤ -1.0%). If the next-day close is past the stop, exit at stop price.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd


def make_label(prices: pd.DataFrame, *, entry_date: str, horizon_days: int = 1,
               win_threshold: float = 0.008, daily_stop_pct: float = -0.01
               ) -> Optional[dict]:
    df = prices.sort_values("date").reset_index(drop=True)
    idx = df.index[df["date"] == entry_date]
    if len(idx) == 0:
        return None
    i = int(idx[0])
    exit_i = i + horizon_days
    if exit_i >= len(df):
        return None
    entry = float(df["close"].iloc[i])
    exit_close = float(df["close"].iloc[exit_i])
    realized = (exit_close - entry) / entry
    # Daily stop — if low on exit day pierced stop, realize at stop
    stop_px = entry * (1.0 + daily_stop_pct)
    exit_low = float(df["low"].iloc[exit_i])
    if exit_low <= stop_px:
        realized = daily_stop_pct
    return {
        "y": 1 if realized >= win_threshold else 0,
        "realized_pct": realized,
        "entry_date": entry_date,
        "exit_date": df["date"].iloc[exit_i],
    }
