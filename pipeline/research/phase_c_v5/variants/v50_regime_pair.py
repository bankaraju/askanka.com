"""V5.0 — Regime-ranker pair engine (THE MOAT).

Sub-variants:
  a: N=3, all 5 regimes pooled
  b: N=5, all 5 regimes pooled
  c: N=3, EUPHORIA + RISK-ON only
  d: N=3, regime_age_days >= 3
"""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5.basket_simulator import simulate_basket_trade


_SUB_VARIANT_PARAMS = {
    "a": {"top_n": 3, "zone_filter": None,              "min_regime_age": 1},
    "b": {"top_n": 5, "zone_filter": None,              "min_regime_age": 1},
    "c": {"top_n": 3, "zone_filter": {"EUPHORIA", "RISK-ON"}, "min_regime_age": 1},
    "d": {"top_n": 3, "zone_filter": None,              "min_regime_age": 3},
}


def run(
    ranker_df: pd.DataFrame,
    symbol_bars: dict[str, pd.DataFrame],
    sub_variant: str,
    hold_days: int = 5,
    notional_per_leg_inr: float = 50_000,
    slippage_bps: float = 5.0,
) -> pd.DataFrame:
    """Run V5.0 for one sub-variant. Returns a trade ledger.

    Each eligible (date, zone) cohort forms one basket: top-N longs vs top-N
    shorts, equal notional. Hold ``hold_days`` trading days.
    """
    if sub_variant not in _SUB_VARIANT_PARAMS:
        raise ValueError(f"sub_variant must be one of a/b/c/d, got {sub_variant!r}")
    params = _SUB_VARIANT_PARAMS[sub_variant]

    if ranker_df.empty:
        return pd.DataFrame()

    df = ranker_df.copy()
    if params["zone_filter"] is not None:
        df = df[df["zone"].isin(params["zone_filter"])]
    df = df[df["regime_age_days"] >= params["min_regime_age"]]
    df = df[df["rank"] <= params["top_n"]]

    trades: list[dict] = []
    for (entry_date, zone), cohort in df.groupby(["date", "zone"]):
        longs = cohort[cohort["side"] == "LONG"].sort_values("rank")
        shorts = cohort[cohort["side"] == "SHORT"].sort_values("rank")
        if longs.empty or shorts.empty:
            continue
        long_legs = [{"symbol": r["symbol"], "weight": 1.0 / len(longs)}
                     for _, r in longs.iterrows()]
        short_legs = [{"symbol": r["symbol"], "weight": 1.0 / len(shorts)}
                      for _, r in shorts.iterrows()]
        trade = simulate_basket_trade(
            entry_date=entry_date,
            long_legs=long_legs, short_legs=short_legs,
            symbol_bars=symbol_bars, hold_days=hold_days,
            notional_per_leg_inr=notional_per_leg_inr,
            slippage_bps=slippage_bps,
        )
        if trade is None:
            continue
        trades.append({
            "entry_date": trade["entry_date"],
            "exit_date": trade["exit_date"],
            "zone": zone,
            "hold_days": hold_days,
            "notional_total_inr": trade["notional_total_inr"],
            "pnl_gross_inr": trade["pnl_gross_inr"],
            "pnl_cost_inr": trade["pnl_cost_inr"],
            "pnl_net_inr": trade["pnl_net_inr"],
            "n_long_legs": trade["side_count_long"],
            "n_short_legs": trade["side_count_short"],
            "sub_variant": sub_variant,
            "top_n": params["top_n"],
        })
    return pd.DataFrame(trades)
