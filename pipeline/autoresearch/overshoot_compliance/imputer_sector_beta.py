"""Sensitivity-track sector-beta imputer per
docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md section 4.

Never invoked on the authoritative compliance path. Output is always
tagged source='proxy_sector_beta' so downstream readers cannot confuse
it with observed prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def impute(
    *,
    ticker_returns: pd.Series,
    sector_returns: pd.Series,
    raw_close: pd.Series,
    gap_date,
    sector_return_at_t: float,
    min_obs: int = 60,
) -> dict | None:
    """Return proxy dict for a missing bar, or None if insufficient pre-t history.

    Parameters
    ----------
    ticker_returns : daily returns of the ticker, pd.Series indexed by date
    sector_returns : daily returns of the sector (or NIFTY) index, same index
    raw_close : ticker's daily close series
    gap_date : the missing bar's date (no value at or after must be used for beta)
    sector_return_at_t : the observed sector return on gap_date
    min_obs : minimum pre-t observation count required before imputing
    """
    gap = pd.Timestamp(gap_date).normalize()
    # empty / non-datetime inputs cannot be imputed against
    if ticker_returns.empty or sector_returns.empty:
        return None
    if not isinstance(ticker_returns.index, pd.DatetimeIndex) or not isinstance(sector_returns.index, pd.DatetimeIndex):
        return None
    # strict pre-t: only bars dated strictly BEFORE gap
    tr = ticker_returns.loc[ticker_returns.index.normalize() < gap]
    sr = sector_returns.loc[sector_returns.index.normalize() < gap]
    aligned = pd.concat({"t": tr, "s": sr}, axis=1).dropna()

    if len(aligned) < min_obs:
        return None

    s = aligned["s"].to_numpy()
    t = aligned["t"].to_numpy()
    var_s = np.var(s, ddof=1)
    if var_s <= 0:
        return None
    beta = float(np.cov(t, s, ddof=1)[0, 1] / var_s)

    r_hat = beta * sector_return_at_t

    # Last observed raw close strictly BEFORE gap_date
    pre_close = raw_close.loc[raw_close.index.normalize() < gap]
    if pre_close.empty:
        return None
    last_close = float(pre_close.iloc[-1])

    p_imputed = last_close * (1.0 + r_hat)

    return {
        "source": "proxy_sector_beta",
        "P_imputed": p_imputed,
        "P_raw": None,
        "beta_value": beta,
        "beta_window_start": aligned.index.min(),
        "beta_window_end": aligned.index.max(),
        "r_sector_used": float(sector_return_at_t),
    }
