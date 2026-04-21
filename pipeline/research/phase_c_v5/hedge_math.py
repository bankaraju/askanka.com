"""Beta-neutral hedge ratios (OLS, clamped)."""
from __future__ import annotations

import numpy as np
import pandas as pd

BETA_MIN, BETA_MAX = 0.5, 1.5


def ols_beta(y: np.ndarray, x: np.ndarray) -> float:
    """Simple OLS slope of y on x. Assumes both arrays are the same length
    and free of NaNs. Returns 0 if x has zero variance."""
    y_arr = np.asarray(y, dtype=float)
    x_arr = np.asarray(x, dtype=float)
    x_mean = x_arr.mean()
    x_var = ((x_arr - x_mean) ** 2).sum()
    if x_var == 0:
        return 0.0
    y_mean = y_arr.mean()
    cov = ((x_arr - x_mean) * (y_arr - y_mean)).sum()
    return float(cov / x_var)


def rolling_ols_beta(stock: pd.Series, index: pd.Series, window: int = 60) -> pd.Series:
    """Rolling OLS beta using pct-change returns. Both series must share an index.
    Result has same length as input; first (window - 1) values are NaN."""
    stock_ret = stock.pct_change(fill_method=None)
    index_ret = index.pct_change(fill_method=None)
    betas: list[float] = []
    for i in range(len(stock_ret)):
        if i < window:
            betas.append(np.nan)
            continue
        y = stock_ret.iloc[i - window + 1:i + 1].dropna().values
        x = index_ret.iloc[i - window + 1:i + 1].dropna().values
        if len(y) != len(x) or len(y) == 0:
            betas.append(np.nan)
            continue
        betas.append(ols_beta(y, x))
    return pd.Series(betas, index=stock.index)


def clamp_beta(beta: float, lo: float = BETA_MIN, hi: float = BETA_MAX) -> float:
    if beta < lo:
        return lo
    if beta > hi:
        return hi
    return beta
