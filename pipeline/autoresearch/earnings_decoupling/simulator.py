"""MODE A simulator: entry T-3 close → exit T-1 close, signed by direction."""
from __future__ import annotations

import pandas as pd

ENTRY_OFFSET = -3
EXIT_OFFSET = -1


def simulate_trades(
    *,
    ledger: pd.DataFrame,
    prices: pd.DataFrame,
    entry_offset: int = ENTRY_OFFSET,
    exit_offset: int = EXIT_OFFSET,
) -> pd.DataFrame:
    candidates = ledger[ledger["status"] == "CANDIDATE"].copy()
    out_rows = []
    for _, row in candidates.iterrows():
        sym = row["ticker"]
        ev_date = pd.Timestamp(row["event_date"])
        if sym not in prices.columns:
            continue
        if ev_date not in prices.index:
            continue
        idx = prices.index.get_loc(ev_date)
        if idx + entry_offset < 0:
            continue
        entry_idx = idx + entry_offset
        exit_idx = idx + exit_offset
        if exit_idx >= len(prices):
            continue
        entry_p = prices[sym].iloc[entry_idx]
        exit_p = prices[sym].iloc[exit_idx]
        if pd.isna(entry_p) or pd.isna(exit_p) or entry_p <= 0:
            continue
        raw_ret = (exit_p - entry_p) / entry_p * 100.0
        sign = 1.0 if row["direction"] == "LONG" else -1.0
        out_rows.append({
            "ticker": sym,
            "date": str(ev_date.date()),
            "event_date": row["event_date"],
            "direction": row["direction"],
            "z": float(row.get("trigger_z", 0.0)),
            "entry_date": str(prices.index[entry_idx].date()),
            "entry_price": float(entry_p),
            "exit_date": str(prices.index[exit_idx].date()),
            "exit_price": float(exit_p),
            "next_ret": float(raw_ret),
            "trade_ret_pct": float(sign * raw_ret),
        })
    return pd.DataFrame(out_rows)
