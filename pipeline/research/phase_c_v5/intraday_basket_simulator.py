# pipeline/research/phase_c_v5/intraday_basket_simulator.py
"""V5.1 production intraday pair simulator.

For each pair from basket_builder, fetch 1-min bars for both legs on the
signal day, simulate long + short with 14:30 mechanical exit, combine
P&L. Uses fetcher.fetch_minute so each day's bars get cached under the
V4 minute_bars/ hierarchy.
"""
from __future__ import annotations

from datetime import time as dtime
import logging

import pandas as pd

from pipeline.research.phase_c_backtest import fetcher as v4fetcher
from pipeline.research.phase_c_v5.cost_model import round_trip_cost

log = logging.getLogger(__name__)
EXIT_TIME = dtime(14, 30, 0)
NOTIONAL_PER_LEG_INR = 50_000


def _fetch_minute(symbol: str, trade_date: str) -> pd.DataFrame:
    """Thin wrapper; tests patch this to avoid hitting Kite."""
    return v4fetcher.fetch_minute(symbol, trade_date=trade_date)


def _entry_exit_prices(bars: pd.DataFrame, entry_ts: pd.Timestamp) -> tuple[float, float] | None:
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    entries = df.loc[df["date"] >= entry_ts]
    if entries.empty:
        return None
    entry_px = float(entries.iloc[0]["open"])
    exits = df.loc[df["date"].dt.time >= EXIT_TIME]
    if exits.empty:
        return None
    exit_px = float(exits.iloc[0]["open"])
    return entry_px, exit_px


def run(pairs: list[dict], entry_time_str: str = "09:20:00") -> pd.DataFrame:
    rows: list[dict] = []
    for p in pairs:
        day = pd.Timestamp(p["date"])
        day_str = day.date().isoformat()
        entry_ts = pd.Timestamp(f"{day_str} {entry_time_str}")
        long_bars = _fetch_minute(p["long_symbol"], day_str)
        short_bars = _fetch_minute(p["short_symbol"], day_str)
        if long_bars.empty or short_bars.empty:
            continue
        long_px = _entry_exit_prices(long_bars, entry_ts)
        short_px = _entry_exit_prices(short_bars, entry_ts)
        if long_px is None or short_px is None:
            continue
        long_entry, long_exit = long_px
        short_entry, short_exit = short_px
        long_gross = (long_exit / long_entry - 1.0) * NOTIONAL_PER_LEG_INR
        short_gross = (short_entry / short_exit - 1.0) * NOTIONAL_PER_LEG_INR
        long_cost = round_trip_cost("stock_future", NOTIONAL_PER_LEG_INR, "LONG")
        short_cost = round_trip_cost("stock_future", NOTIONAL_PER_LEG_INR, "SHORT")
        rows.append({
            "entry_date": day, "exit_date": day, "sector": p["sector"],
            "long_symbol": p["long_symbol"], "short_symbol": p["short_symbol"],
            "long_entry": long_entry, "long_exit": long_exit,
            "short_entry": short_entry, "short_exit": short_exit,
            "notional_total_inr": NOTIONAL_PER_LEG_INR * 2,
            "pnl_gross_inr": long_gross + short_gross,
            "pnl_cost_inr": long_cost + short_cost,
            "pnl_net_inr": (long_gross + short_gross) - (long_cost + short_cost),
            "exit_reason": "time_stop", "variant": "v51",
        })
    return pd.DataFrame(rows)
