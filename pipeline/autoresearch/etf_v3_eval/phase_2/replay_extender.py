"""Convert v0.2 minute-bar parquet to event-level rows for marker decomposition.

Each (ticker, trade_date) becomes one event with:
- open_to_1430_pct (TIME_STOP convention)
- open_to_close_pct
- intraday_high_pct, intraday_low_pct (for ATR/stop testing)

Notes
-----
- The TIME_STOP convention takes the close of the bar whose ``time(hour, min)``
  equals 14:30 IST. If no 14:30 bar exists for a (ticker, date), TIME_STOP
  falls back to the day's last close (open_to_1430_pct == open_to_close_pct).
- Input timestamps are localised to Asia/Kolkata if naive.
- Returns are signed percentages (positive when price > open_px).
"""
from __future__ import annotations

from datetime import time

import pandas as pd


def aggregate_minute_to_event_returns(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate one row per (ticker, trade_date) with directional return columns.

    Parameters
    ----------
    minute_df:
        DataFrame with columns: ticker, trade_date, timestamp, open, high, low,
        close, volume.  Timestamps may be tz-aware (Asia/Kolkata) or naive.

    Returns
    -------
    DataFrame with one row per (ticker, trade_date) and columns:
        ticker, trade_date,
        open_px, close_px, time_stop_px, intraday_high, intraday_low,
        open_to_1430_pct, open_to_close_pct,
        intraday_high_pct, intraday_low_pct.
    """
    df = minute_df.copy()
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")

    df["clock"] = df["timestamp"].dt.time
    df = df.sort_values(["ticker", "trade_date", "timestamp"])

    rows = []
    for (t, d), g in df.groupby(["ticker", "trade_date"], sort=False):
        g = g.reset_index(drop=True)
        first = g.iloc[0]
        last = g.iloc[-1]
        open_px = float(first["open"])
        close_px = float(last["close"])
        bar_1430 = g[g["clock"] == time(14, 30)]
        time_stop_px = float(bar_1430.iloc[0]["close"]) if len(bar_1430) else close_px
        intraday_high = float(g["high"].max())
        intraday_low = float(g["low"].min())
        rows.append({
            "ticker": t,
            "trade_date": d,
            "open_px": open_px,
            "close_px": close_px,
            "time_stop_px": time_stop_px,
            "intraday_high": intraday_high,
            "intraday_low": intraday_low,
            "open_to_1430_pct": (time_stop_px - open_px) / open_px,
            "open_to_close_pct": (close_px - open_px) / open_px,
            "intraday_high_pct": (intraday_high - open_px) / open_px,
            "intraday_low_pct": (intraday_low - open_px) / open_px,
        })
    return pd.DataFrame(rows)
