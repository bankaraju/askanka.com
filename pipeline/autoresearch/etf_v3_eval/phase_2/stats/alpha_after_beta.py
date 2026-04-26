"""§11B alpha-after-beta — daily-return regression of strategy on NIFTY.

Reports: beta (slope), alpha_annualized (intercept × 252), r_squared,
residual_sharpe (Sharpe of residuals after stripping β·NIFTY).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import statsmodels.api as sm


def regress_against_benchmark(
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    annualization: int = 252,
) -> dict:
    """Regress strategy on benchmark; report alpha (annualised), beta, R², residual Sharpe.

    Returns dict ``{alpha_annualized, beta, r_squared, residual_sharpe, n_obs}``.
    Inputs are coerced via ``np.asarray(..., dtype=float)`` so list inputs work.
    """
    y = np.asarray(strategy_returns, dtype=float)
    x = np.asarray(benchmark_returns, dtype=float)
    if len(y) != len(x):
        raise ValueError(f"length mismatch: strategy={len(y)} vs benchmark={len(x)}")
    if len(y) < 2:
        raise ValueError(f"regress_against_benchmark needs >= 2 observations, got {len(y)}")
    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()
    intercept, beta = float(model.params[0]), float(model.params[1])
    residuals = y - (intercept + beta * x)
    res_mean = float(residuals.mean())
    res_sd = float(residuals.std(ddof=1) or 1e-12)  # guard zero-variance edge
    return {
        "alpha_annualized": intercept * annualization,
        "beta": beta,
        "r_squared": float(model.rsquared),
        "residual_sharpe": (res_mean / res_sd) * np.sqrt(annualization),
        "n_obs": int(len(y)),
    }
