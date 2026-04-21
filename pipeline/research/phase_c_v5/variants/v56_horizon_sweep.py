"""V5.6 — hold-horizon sweep. Five ledger rows per signal."""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5.cost_model import round_trip_cost

NOTIONAL_INR = 50_000
_HORIZONS = {
    "intraday_1430": 0,  # same-day open → next-bar close proxy on daily data
    "T+1": 1, "T+2": 2, "T+3": 3, "T+5": 5,
}


def run(signals: pd.DataFrame, symbol_bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sigs = signals[signals["classification"] == "OPPORTUNITY"].copy()
    sigs["date"] = pd.to_datetime(sigs["date"])

    rows: list[dict] = []
    for _, s in sigs.iterrows():
        sym = s["symbol"]
        bars = symbol_bars.get(sym)
        if bars is None or bars.empty:
            continue
        bars = bars.sort_values("date").reset_index(drop=True)
        day = s["date"]
        day_rows = bars.loc[bars["date"] == day]
        if day_rows.empty:
            continue
        entry_idx = day_rows.index[0]
        entry_px = float(bars.iloc[entry_idx]["open"])
        for horizon_name, shift in _HORIZONS.items():
            exit_idx = entry_idx + shift if shift > 0 else entry_idx
            if exit_idx >= len(bars):
                continue
            exit_px = float(bars.iloc[exit_idx]["close"])
            direction = s["direction"]
            if direction == "LONG":
                gross = (exit_px / entry_px - 1.0) * NOTIONAL_INR
            else:
                gross = (entry_px / exit_px - 1.0) * NOTIONAL_INR
            cost = round_trip_cost("stock_future", NOTIONAL_INR, direction)
            rows.append({
                "entry_date": day, "exit_date": bars.iloc[exit_idx]["date"],
                "symbol": sym, "direction": direction,
                "exit_horizon": horizon_name,
                "notional_total_inr": NOTIONAL_INR,
                "pnl_gross_inr": gross, "pnl_cost_inr": cost, "pnl_net_inr": gross - cost,
                "variant": "v56",
            })
    return pd.DataFrame(rows)
