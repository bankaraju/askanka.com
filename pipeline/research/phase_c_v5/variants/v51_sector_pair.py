"""V5.1 — sector-neutral intraday pair.

For each basket_builder pair, simulate long + short legs on 1-min bars,
exit at 14:30 IST (time_stop). Combine leg P&L; reduce pair to one ledger row.
"""
from __future__ import annotations

from datetime import time as dtime
import pandas as pd

from pipeline.research.phase_c_v5.cost_model import round_trip_cost

EXIT_TIME = dtime(14, 30, 0)
NOTIONAL_PER_LEG_INR = 50_000


def _entry_and_exit_prices(bars: pd.DataFrame, entry_ts: pd.Timestamp) -> tuple[float, float] | None:
    """Entry = first bar open at/after entry_ts. Exit = first bar open at 14:30."""
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    entry_rows = df.loc[df["date"] >= entry_ts]
    if entry_rows.empty:
        return None
    entry_px = float(entry_rows.iloc[0]["open"])
    exit_rows = df.loc[df["date"].dt.time >= EXIT_TIME]
    if exit_rows.empty:
        return None
    exit_px = float(exit_rows.iloc[0]["open"])
    return entry_px, exit_px


def run(pairs: list[dict], symbol_minute_bars: dict[str, pd.DataFrame],
        entry_time_str: str = "09:20:00") -> pd.DataFrame:
    rows: list[dict] = []
    for p in pairs:
        long_bars = symbol_minute_bars.get(p["long_symbol"])
        short_bars = symbol_minute_bars.get(p["short_symbol"])
        if long_bars is None or short_bars is None or long_bars.empty or short_bars.empty:
            continue
        entry_ts = pd.Timestamp(f"{pd.Timestamp(p['date']).date()} {entry_time_str}")
        long_px = _entry_and_exit_prices(long_bars, entry_ts)
        short_px = _entry_and_exit_prices(short_bars, entry_ts)
        if long_px is None or short_px is None:
            continue
        long_entry, long_exit = long_px
        short_entry, short_exit = short_px
        long_gross = (long_exit / long_entry - 1.0) * NOTIONAL_PER_LEG_INR
        short_gross = (short_entry / short_exit - 1.0) * NOTIONAL_PER_LEG_INR
        long_cost = round_trip_cost("stock_future", NOTIONAL_PER_LEG_INR, "LONG")
        short_cost = round_trip_cost("stock_future", NOTIONAL_PER_LEG_INR, "SHORT")
        gross = long_gross + short_gross
        cost = long_cost + short_cost
        rows.append({
            "entry_date": p["date"], "exit_date": p["date"], "sector": p["sector"],
            "long_symbol": p["long_symbol"], "short_symbol": p["short_symbol"],
            "long_entry": long_entry, "long_exit": long_exit,
            "short_entry": short_entry, "short_exit": short_exit,
            "notional_total_inr": NOTIONAL_PER_LEG_INR * 2,
            "pnl_gross_inr": gross, "pnl_cost_inr": cost, "pnl_net_inr": gross - cost,
            "exit_reason": "time_stop", "variant": "v51",
        })
    return pd.DataFrame(rows)
