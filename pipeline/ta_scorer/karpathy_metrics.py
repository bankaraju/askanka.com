"""H-2026-04-29-ta-karpathy-v1 v1.1 robustness metrics.

Implements Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR)
per Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio: Correcting for
Selection Bias, Backtest Overfitting, and Non-Normality", Journal of Portfolio
Management 40 (5).

Adopted in v1.1 amendment dated 2026-04-28 in response to user feedback that
raw Sharpe is inflated when many configurations are searched per stock and
across stocks. The 9-alpha grid x 20 (stock x direction) cells = 180 trial
configurations is the primary inflator we are deflating against.

Spec amendment: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
§15.1 verdict gate now adds a PSR>=0.95 threshold against the deflated null.

Mathematical references:
  PSR(SR*) = N(((SR_hat - SR*) * sqrt(T-1)) / sqrt(1 - g3*SR_hat + (g4-1)/4*SR_hat^2))
  E[max(SR_estimates)] approx (1-gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N*e))
  DSR_threshold = E[max(SR_estimates)] (the SR* to feed into PSR)

where N = number of trials, T = number of return observations,
g3 = skewness of returns, g4 = kurtosis of returns,
gamma = Euler-Mascheroni constant ~ 0.5772.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats as sps

EULER_GAMMA = 0.5772156649015329


def sharpe_ratio(returns: np.ndarray | pd.Series, *, periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio. Zero-risk-free benchmark (Indian intraday context).

    Daily return series with mean mu and std sigma -> SR_annual = mu/sigma * sqrt(periods_per_year).
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    if len(r) < 2 or np.std(r, ddof=1) == 0:
        return float("nan")
    return float(np.mean(r) / np.std(r, ddof=1) * math.sqrt(periods_per_year))


def probabilistic_sharpe_ratio(
    returns: np.ndarray | pd.Series,
    *,
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """PSR: probability that the true Sharpe exceeds `sr_benchmark`.

    Bailey & Lopez de Prado (2014) eq. 9. Adjusts for non-normality via the
    return series' skewness g3 and excess kurtosis g4.

    Returns a probability in [0, 1].
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    T = len(r)
    if T < 4:
        return float("nan")
    mu = np.mean(r)
    sigma = np.std(r, ddof=1)
    if sigma == 0:
        return float("nan")
    sr_daily = mu / sigma
    sr_hat = sr_daily * math.sqrt(periods_per_year)

    # Sample skewness g1 (Fisher-Pearson) and excess kurtosis g2
    g1 = float(sps.skew(r, bias=False))
    g2 = float(sps.kurtosis(r, fisher=True, bias=False))

    # PSR uses the daily SR (sr_daily) for the variance term, then translates
    # via T as the number of observations
    sr_daily_bench = sr_benchmark / math.sqrt(periods_per_year)
    var_sr = (1.0 - g1 * sr_daily + (g2 / 4.0) * sr_daily ** 2) / (T - 1)
    if var_sr <= 0 or not np.isfinite(var_sr):
        return float("nan")
    z = (sr_daily - sr_daily_bench) / math.sqrt(var_sr)
    return float(sps.norm.cdf(z))


def expected_max_sharpe(n_trials: int) -> float:
    """E[max(SR)] of N independent draws from Normal(0,1) -- the deflation
    threshold. Bailey & Lopez de Prado (2014) eq. 6.
    """
    if n_trials < 2:
        return 0.0
    e = math.e
    return float(
        (1 - EULER_GAMMA) * sps.norm.ppf(1.0 - 1.0 / n_trials)
        + EULER_GAMMA * sps.norm.ppf(1.0 - 1.0 / (n_trials * e))
    )


def deflated_sharpe_ratio(
    returns: np.ndarray | pd.Series,
    *,
    n_trials: int,
    periods_per_year: int = 252,
    sr_estimates_std: float | None = None,
) -> dict:
    """Deflated Sharpe Ratio.

    Computes PSR with the benchmark set to E[max(SR)] across `n_trials`. This
    asks: given that we searched N configurations, is the OBSERVED SR still
    plausibly real?

    Args:
      returns: realised return series of the SELECTED config (e.g. forward
               holdout daily P&L)
      n_trials: number of independent backtest configurations searched (e.g.
               9 alphas x 20 cells = 180 for this hypothesis)
      periods_per_year: 252 for daily intraday returns
      sr_estimates_std: if provided, scales the deflation. Default 1.0
                        treats trials as iid Normal(0,1) Sharpes.

    Returns dict with: sr_observed, sr_max_expected, psr_vs_max, dsr_pass
    where dsr_pass = (psr_vs_max >= 0.95).
    """
    sr_obs = sharpe_ratio(returns, periods_per_year=periods_per_year)
    sr_max = expected_max_sharpe(n_trials)
    if sr_estimates_std is not None and sr_estimates_std > 0:
        sr_max = sr_max * float(sr_estimates_std)
    psr = probabilistic_sharpe_ratio(
        returns, sr_benchmark=sr_max, periods_per_year=periods_per_year,
    )
    return {
        "sr_observed": sr_obs,
        "sr_max_expected": sr_max,
        "n_trials": int(n_trials),
        "psr_vs_max": psr,
        "dsr_pass": bool(psr >= 0.95) if not np.isnan(psr) else False,
    }


def stability_penalty(fold_aucs: list[float]) -> float:
    """Robustness penalty for cells whose AUC swings wildly across folds.

    Returns a scalar in [0, 1] where 1.0 = perfectly stable, 0.0 = max
    instability. Use as a multiplier on cell P&L when basketing.

    Definition: 1 - clip(std(fold_aucs) / 0.10, 0, 1). Std of 0 -> 1.0; std of
    >=0.10 -> 0.0. The 0.10 cap is the spec qualifier-gate's 2x ceiling
    (qualifier requires fold_auc_std <= 0.05).
    """
    a = [x for x in fold_aucs if not np.isnan(x)]
    if len(a) < 2:
        return float("nan")
    return float(max(0.0, 1.0 - np.std(a) / 0.10))


def basket_returns_from_cells(
    cell_returns: dict[str, np.ndarray | pd.Series],
    *,
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """Combine per-cell daily returns into a basket return series.

    Cells with different date coverage are aligned on union and missing
    days are 0 (cell didn't trade that day).

    Args:
      cell_returns: {cell_id: per-day returns indexed by date OR raw array}
      weights: {cell_id: weight}. Default = equal-weight across cells that
               have any returns.
    """
    if not cell_returns:
        return np.array([])
    # If inputs are Series with date index, align via concat
    if all(isinstance(v, pd.Series) for v in cell_returns.values()):
        df = pd.concat(cell_returns, axis=1).fillna(0.0)
        if weights is None:
            w = np.ones(df.shape[1]) / df.shape[1]
        else:
            w = np.array([weights.get(k, 0.0) for k in df.columns])
            if w.sum() > 0:
                w = w / w.sum()
        return (df.values @ w).astype(float)
    # Raw arrays: must be same length
    arrs = list(cell_returns.values())
    L = len(arrs[0])
    if not all(len(a) == L for a in arrs):
        raise ValueError("raw-array cells must have identical length")
    M = np.column_stack([np.asarray(a, dtype=float) for a in arrs])
    if weights is None:
        w = np.ones(M.shape[1]) / M.shape[1]
    else:
        keys = list(cell_returns.keys())
        w = np.array([weights.get(k, 0.0) for k in keys])
        if w.sum() > 0:
            w = w / w.sum()
    return (M @ w).astype(float)
