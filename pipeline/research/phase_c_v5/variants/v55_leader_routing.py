"""V5.5 — leader → index routing.

Trade the index future when >=2 of its top-3 constituents fire same-direction
OPPORTUNITY. Liquidity win: index futures absorb 100x book scale.
"""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5.cost_model import round_trip_cost

INDEX_NOTIONAL_INR = 100_000  # larger per trade since index is more liquid
MIN_ALIGNED = 2
_INDEX_TOP3 = {
    "BANKNIFTY": {"HDFCBANK", "ICICIBANK", "SBIN"},
    "NIFTYIT":   {"TCS", "INFY", "HCLTECH"},
}


def run(signals: pd.DataFrame, symbol_bars: dict[str, pd.DataFrame],
        hold_days: int = 1) -> pd.DataFrame:
    sigs = signals[signals["classification"] == "OPPORTUNITY"].copy()
    if sigs.empty:
        return pd.DataFrame()
    sigs["date"] = pd.to_datetime(sigs["date"])

    rows: list[dict] = []
    for (day, index), group in _iter_eligible(sigs):
        aligned_direction = group["direction"].iloc[0]
        if not (group["direction"] == aligned_direction).all():
            continue
        if len(group) < MIN_ALIGNED:
            continue
        index_bars = symbol_bars.get(index)
        if index_bars is None or index_bars.empty:
            continue
        index_bars = index_bars.sort_values("date").reset_index(drop=True)
        day_rows = index_bars.loc[index_bars["date"] == day]
        if day_rows.empty:
            continue
        entry_idx = day_rows.index[0]
        exit_idx = entry_idx + hold_days
        if exit_idx >= len(index_bars):
            continue
        entry = float(index_bars.iloc[entry_idx]["open"])
        exit_ = float(index_bars.iloc[exit_idx]["close"])
        if aligned_direction == "LONG":
            gross = (exit_ / entry - 1.0) * INDEX_NOTIONAL_INR
        else:
            gross = (entry / exit_ - 1.0) * INDEX_NOTIONAL_INR
        # Cost tier fix: use tiered lookup instead of always "nifty_future"
        index_instrument = "nifty_future" if index in {"NIFTY", "BANKNIFTY"} else "sectoral_index_future"
        cost = round_trip_cost(index_instrument, INDEX_NOTIONAL_INR, aligned_direction)
        rows.append({
            "entry_date": day, "exit_date": index_bars.iloc[exit_idx]["date"],
            "index_symbol": index, "direction": aligned_direction,
            "n_constituents_aligned": len(group),
            "notional_total_inr": INDEX_NOTIONAL_INR,
            "pnl_gross_inr": gross, "pnl_cost_inr": cost, "pnl_net_inr": gross - cost,
            "variant": "v55",
        })
    return pd.DataFrame(rows)


def _iter_eligible(sigs: pd.DataFrame):
    for (day,), group in sigs.groupby([sigs["date"]]):
        for index, constituents in _INDEX_TOP3.items():
            sub = group[group["symbol"].isin(constituents)]
            if len(sub) >= MIN_ALIGNED:
                yield (day, index), sub
