"""NIFTY-beta regression per §11B of backtesting-specs.txt v1.0.

regress_on_nifty: given a strategy's daily return series and NIFTY's daily
return series (both pd.Series indexed by Timestamp), return dict with
{beta, alpha_annualised, r_squared, residual_sharpe, gross_sharpe, n_aligned}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.research.phase_c_backtest import stats as PC


def regress_on_nifty(
    strategy_rets: pd.Series,
    nifty_rets: pd.Series,
    periods_per_year: int = 252,
) -> dict:
    aligned = pd.concat({"s": strategy_rets, "m": nifty_rets}, axis=1).dropna()
    if len(aligned) < 2 or aligned["m"].std(ddof=1) == 0:
        return {
            "beta": 0.0,
            "alpha_annualised": 0.0,
            "r_squared": 0.0,
            "residual_sharpe": 0.0,
            "gross_sharpe": PC.sharpe(strategy_rets.to_numpy(), periods_per_year),
            "n_aligned": int(len(aligned)),
        }
    s = aligned["s"].to_numpy()
    m = aligned["m"].to_numpy()
    m_mean, s_mean = m.mean(), s.mean()
    cov = np.mean((m - m_mean) * (s - s_mean))
    var_m = np.mean((m - m_mean) ** 2)
    beta = float(cov / var_m)
    alpha = float(s_mean - beta * m_mean)
    ss_tot = np.sum((s - s_mean) ** 2)
    ols_residuals = s - (alpha + beta * m)
    ss_res = np.sum(ols_residuals ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    de_market = s - beta * m
    return {
        "beta": round(beta, 6),
        "alpha_annualised": round(alpha * periods_per_year, 6),
        "r_squared": round(r2, 6),
        "residual_sharpe": round(PC.sharpe(de_market, periods_per_year), 6),
        "gross_sharpe": round(PC.sharpe(s, periods_per_year), 6),
        "n_aligned": int(len(aligned)),
    }
