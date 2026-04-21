"""V5.7 — long ATM call/put per Phase C OPPORTUNITY signal.

Uses Station 6.5 synthetic pricer (pipeline.options_pricer) for entry + exit
premiums. Strike = round(spot/50)*50. Exit at 14:30 of entry day (proxied by
next-bar close on daily data; true-intraday test requires 1-min bars and is
out of scope for the first pass).

Pricer signature adaptation: the plan assumed price_bs_call/put(spot, strike,
vol, valuation_date, expiry_date) but the shipped pricer (options_pricer.py)
exposes bs_call_price(S, K, T, sigma, r) using T_years directly. _price_option
converts the two Timestamps to T_years before forwarding.
"""
from __future__ import annotations

import math

import pandas as pd

from pipeline.research.phase_c_v5.cost_model import round_trip_cost

OPTION_NOTIONAL_INR = 50_000


def _atm_strike(spot: float, step: int = 50) -> int:
    return int(round(spot / step) * step)


def _price_option(
    symbol: str,
    strike: int,
    spot: float,
    vol: float,
    expiry_date: pd.Timestamp,
    valuation_date: pd.Timestamp,
    option_type: str,
) -> float:
    """Thin wrapper around Station 6.5 pricer so tests can patch it without
    importing the module.

    Adaptation: shipped pricer uses T_years (float), not valuation/expiry dates.
    We derive T = max(calendar days remaining, 0) / 365.
    """
    from pipeline import options_pricer as bs

    days_remaining = (expiry_date - valuation_date).days
    T = max(days_remaining, 0) / 365.0
    if option_type == "CALL":
        return bs.bs_call_price(S=spot, K=float(strike), T=T, sigma=vol)
    return bs.bs_put_price(S=spot, K=float(strike), T=T, sigma=vol)


def _ewma_vol(bars: pd.DataFrame, half_life: int = 30) -> float:
    """EWMA realised vol of daily log returns."""
    closes = bars["close"].astype(float).values
    if len(closes) < 2:
        return 0.30
    import numpy as np

    rets = np.diff(np.log(closes))
    decay = 0.5 ** (1.0 / half_life)
    weights = decay ** np.arange(len(rets))[::-1]
    weighted_var = np.sum(weights * rets ** 2) / weights.sum()
    return float(math.sqrt(weighted_var * 252))


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
        bars["date"] = pd.to_datetime(bars["date"])
        day = s["date"]
        day_rows = bars.loc[bars["date"] == day]
        if day_rows.empty:
            continue
        entry_idx = day_rows.index[0]
        exit_idx = entry_idx + 1  # daily proxy for same-day 14:30 exit
        if exit_idx >= len(bars):
            continue
        spot_entry = float(bars.iloc[entry_idx]["open"])
        spot_exit = float(bars.iloc[exit_idx]["close"])
        strike = _atm_strike(spot_entry)
        # Expiry: nearest month-end, approximated as entry + 30 calendar days
        expiry = day + pd.Timedelta(days=30)
        option_type = "CALL" if s["direction"] == "LONG" else "PUT"
        vol = _ewma_vol(bars.iloc[max(0, entry_idx - 30):entry_idx])

        prem_entry = _price_option(sym, strike, spot_entry, vol, expiry, day, option_type)
        prem_exit = _price_option(
            sym, strike, spot_exit, vol, expiry,
            pd.Timestamp(bars.iloc[exit_idx]["date"]), option_type,
        )
        # Convert premium change to INR P&L on OPTION_NOTIONAL_INR
        contracts = OPTION_NOTIONAL_INR / max(prem_entry, 0.01)
        gross = (prem_exit - prem_entry) * contracts
        cost = round_trip_cost("option", OPTION_NOTIONAL_INR, "LONG")
        rows.append({
            "entry_date": day,
            "exit_date": bars.iloc[exit_idx]["date"],
            "symbol": sym,
            "option_type": option_type,
            "strike": strike,
            "option_entry_premium": prem_entry,
            "option_exit_premium": prem_exit,
            "ewma_vol": vol,
            "contracts": contracts,
            "notional_total_inr": OPTION_NOTIONAL_INR,
            "pnl_gross_inr": gross,
            "pnl_cost_inr": cost,
            "pnl_net_inr": gross - cost,
            "variant": "v57",
        })
    return pd.DataFrame(rows)
