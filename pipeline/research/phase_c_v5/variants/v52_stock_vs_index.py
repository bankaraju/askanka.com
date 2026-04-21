"""V5.2 — stock leg + opposite-side sector-index leg, beta-neutralised."""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5 import hedge_math
from pipeline.research.phase_c_v5.cost_model import round_trip_cost

STOCK_NOTIONAL_INR = 50_000


def run(signals: pd.DataFrame, symbol_bars: dict[str, pd.DataFrame],
        hold_days: int = 1) -> pd.DataFrame:
    sigs = signals[signals["classification"] == "OPPORTUNITY"].copy()
    sigs["date"] = pd.to_datetime(sigs["date"])

    rows: list[dict] = []
    for _, s in sigs.iterrows():
        stock_sym = s["symbol"]
        index_sym = s["sector_index"]
        stock_df = symbol_bars.get(stock_sym)
        index_df = symbol_bars.get(index_sym)
        if stock_df is None or index_df is None:
            continue
        # Align on date
        merged = pd.merge(stock_df[["date", "close"]].rename(columns={"close": "stock"}),
                          index_df[["date", "close"]].rename(columns={"close": "idx"}),
                          on="date", how="inner").sort_values("date")
        if len(merged) < 70:
            continue
        betas = hedge_math.rolling_ols_beta(
            merged.set_index("date")["stock"],
            merged.set_index("date")["idx"], window=60)
        sig_date = s["date"]
        if sig_date not in betas.index:
            continue
        beta = betas.loc[sig_date]
        if pd.isna(beta):
            continue
        hedge_ratio = hedge_math.clamp_beta(beta)

        # Simple hold: close-to-close over `hold_days`. Entry open = entry_date open,
        # exit close = entry_date + hold_days bar close.
        stock_day = stock_df.loc[stock_df["date"] == sig_date]
        if stock_day.empty:
            continue
        entry_idx = stock_day.index[0]
        exit_idx = entry_idx + hold_days
        if exit_idx >= len(stock_df):
            continue
        stock_entry = float(stock_df.iloc[entry_idx]["open"])
        stock_exit = float(stock_df.iloc[exit_idx]["close"])
        index_day = index_df.loc[index_df["date"] == sig_date]
        if index_day.empty:
            continue
        idx_entry_idx = index_day.index[0]
        idx_exit_idx = idx_entry_idx + hold_days
        if idx_exit_idx >= len(index_df):
            continue
        index_entry = float(index_df.iloc[idx_entry_idx]["open"])
        index_exit = float(index_df.iloc[idx_exit_idx]["close"])

        stock_side = s["direction"]
        index_side = "SHORT" if stock_side == "LONG" else "LONG"
        stock_notional = STOCK_NOTIONAL_INR
        index_notional = STOCK_NOTIONAL_INR * hedge_ratio

        if stock_side == "LONG":
            stock_gross = (stock_exit / stock_entry - 1.0) * stock_notional
        else:
            stock_gross = (stock_entry / stock_exit - 1.0) * stock_notional
        if index_side == "LONG":
            index_gross = (index_exit / index_entry - 1.0) * index_notional
        else:
            index_gross = (index_entry / index_exit - 1.0) * index_notional

        # Determine the index cost bucket: NIFTY/BANKNIFTY are "nifty_future" tier
        # (cheapest); anything else is sectoral.
        index_instrument = "nifty_future" if index_sym in {"NIFTY", "BANKNIFTY"} \
                           else "sectoral_index_future"
        stock_cost = round_trip_cost("stock_future", stock_notional, stock_side)
        index_cost = round_trip_cost(index_instrument, index_notional, index_side)

        gross = stock_gross + index_gross
        cost = stock_cost + index_cost
        rows.append({
            "entry_date": sig_date, "exit_date": stock_df.iloc[exit_idx]["date"],
            "stock_symbol": stock_sym, "stock_side": stock_side,
            "index_symbol": index_sym, "index_side": index_side,
            "hedge_ratio": hedge_ratio,
            "stock_notional_inr": stock_notional,
            "index_notional_inr": index_notional,
            "notional_total_inr": stock_notional + index_notional,
            "pnl_gross_inr": gross, "pnl_cost_inr": cost, "pnl_net_inr": gross - cost,
            "variant": "v52",
        })
    return pd.DataFrame(rows)
