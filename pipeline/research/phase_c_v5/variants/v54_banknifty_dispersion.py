"""V5.4 — BANKNIFTY / NIFTY IT dispersion.

Fires when a top-3 constituent signal aligns with an under-performing index
(rolling 5-bar return of index < constituent's). Long constituent, short
index. Same logic for NIFTY IT.
"""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5.cost_model import round_trip_cost

STOCK_NOTIONAL_INR = 50_000
LAG_WINDOW = 5

_INDEX_TOP3 = {
    "BANKNIFTY": {"HDFCBANK", "ICICIBANK", "SBIN"},
    "NIFTYIT":   {"TCS", "INFY", "HCLTECH"},
}


def _index_for_symbol(symbol: str) -> str | None:
    for idx, constituents in _INDEX_TOP3.items():
        if symbol in constituents:
            return idx
    return None


def _rolling_return(df: pd.DataFrame, as_of: pd.Timestamp, window: int) -> float | None:
    df = df.sort_values("date").reset_index(drop=True)
    rows = df.loc[df["date"] == as_of]
    if rows.empty:
        return None
    idx = rows.index[0]
    if idx < window:
        return None
    past = float(df.iloc[idx - window]["close"])
    now = float(df.iloc[idx]["close"])
    return now / past - 1.0


def run(signals: pd.DataFrame, symbol_bars: dict[str, pd.DataFrame],
        hold_days: int = 1) -> pd.DataFrame:
    sigs = signals[signals["classification"] == "OPPORTUNITY"].copy()
    sigs["date"] = pd.to_datetime(sigs["date"])

    rows: list[dict] = []
    for _, s in sigs.iterrows():
        sym = s["symbol"]
        idx = _index_for_symbol(sym)
        if idx is None:
            continue
        stock = symbol_bars.get(sym)
        index = symbol_bars.get(idx)
        if stock is None or index is None:
            continue
        sig_date = s["date"]
        stock_ret = _rolling_return(stock, sig_date, LAG_WINDOW)
        index_ret = _rolling_return(index, sig_date, LAG_WINDOW)
        if stock_ret is None or index_ret is None:
            continue
        # Must be long-constituent + index lagging (stock_ret > index_ret)
        if s["direction"] != "LONG" or stock_ret <= index_ret:
            continue

        stock_day = stock.loc[stock["date"] == sig_date]
        if stock_day.empty:
            continue
        stock_idx = stock_day.index[0]
        exit_idx = stock_idx + hold_days
        if exit_idx >= len(stock):
            continue
        stock_entry = float(stock.iloc[stock_idx]["open"])
        stock_exit = float(stock.iloc[exit_idx]["close"])

        index_day = index.loc[index["date"] == sig_date]
        if index_day.empty:
            continue
        iidx = index_day.index[0]
        ixit = iidx + hold_days
        if ixit >= len(index):
            continue
        index_entry = float(index.iloc[iidx]["open"])
        index_exit = float(index.iloc[ixit]["close"])

        notional = STOCK_NOTIONAL_INR
        stock_gross = (stock_exit / stock_entry - 1.0) * notional
        index_gross = (index_entry / index_exit - 1.0) * notional  # short index
        stock_cost = round_trip_cost("stock_future", notional, "LONG")
        index_cost = round_trip_cost("nifty_future", notional, "SHORT")
        gross = stock_gross + index_gross
        cost = stock_cost + index_cost
        rows.append({
            "entry_date": sig_date, "exit_date": stock.iloc[exit_idx]["date"],
            "stock_symbol": sym, "stock_side": "LONG",
            "index_symbol": idx, "index_side": "SHORT",
            "stock_5bar_ret": stock_ret, "index_5bar_ret": index_ret,
            "notional_total_inr": notional * 2,
            "pnl_gross_inr": gross, "pnl_cost_inr": cost, "pnl_net_inr": gross - cost,
            "variant": "v54",
        })
    return pd.DataFrame(rows)
