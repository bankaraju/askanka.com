"""Risk-adjusted metrics per §2 and §9.3 of backtesting-specs.txt v1.0.

Re-uses pipeline.research.phase_c_backtest.stats for Sharpe / bootstrap CI /
drawdown so we do not re-derive tested code. Adds hit-rate percentile CI and
a per-bucket row helper.
"""
from __future__ import annotations

import numpy as np

from pipeline.research.phase_c_backtest import stats as PC


def hit_rate_ci(
    wins: np.ndarray,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int | None = None,
) -> tuple[float, float, float]:
    arr = np.asarray(wins, dtype=int)
    n = arr.size
    if n == 0:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    resampled = arr[idx]
    rates = resampled.mean(axis=1)
    lo = float(np.quantile(rates, alpha / 2))
    hi = float(np.quantile(rates, 1 - alpha / 2))
    point = float(arr.mean())
    return (lo, point, hi)


def max_drawdown_of(returns_pct: np.ndarray) -> float:
    """Max drawdown of a percent-return series (not annualised).

    Input is in percent space (3.5 for 3.5%). Converts to decimals internally
    and builds an equity curve before delegating to phase_c_backtest.stats.
    """
    if len(returns_pct) == 0:
        return 0.0
    equity = np.cumprod(1.0 + np.asarray(returns_pct, dtype=float) / 100.0)
    return PC.max_drawdown(equity)


def per_bucket_metrics(
    returns_pct: np.ndarray,
    annualisation_factor: int = 252,
    n_resamples: int = 5_000,
    seed: int | None = 42,
) -> dict:
    arr = np.asarray(returns_pct, dtype=float)
    n = arr.size
    if n == 0:
        return {
            "n_trades": 0, "mean_ret_pct": 0.0, "hit_rate": 0.0,
            "hit_rate_ci_lo_95": 0.0, "hit_rate_ci_hi_95": 0.0,
            "sharpe": 0.0, "sharpe_ci_lo_95": 0.0, "sharpe_ci_hi_95": 0.0,
            "max_drawdown_pct": 0.0, "calmar": 0.0,
        }
    # convert percent to decimals for Sharpe / DD math
    dec = arr / 100.0
    sharpe_pt, sharpe_lo, sharpe_hi = PC.bootstrap_sharpe_ci(
        dec, n_resamples=n_resamples, alpha=0.05,
        periods_per_year=annualisation_factor, seed=seed,
    )
    wins = (arr > 0).astype(int)
    hr_lo, hr_pt, hr_hi = hit_rate_ci(wins, n_resamples=n_resamples, seed=seed)
    dd = max_drawdown_of(arr)
    mean_ret = float(arr.mean())
    annualised_mean = mean_ret / 100.0 * annualisation_factor
    calmar = annualised_mean / dd if dd > 0 else 0.0
    return {
        "n_trades": int(n),
        "mean_ret_pct": round(mean_ret, 4),
        "hit_rate": round(hr_pt, 4),
        "hit_rate_ci_lo_95": round(hr_lo, 4),
        "hit_rate_ci_hi_95": round(hr_hi, 4),
        "sharpe": round(sharpe_pt, 4),
        "sharpe_ci_lo_95": round(sharpe_lo, 4),
        "sharpe_ci_hi_95": round(sharpe_hi, 4),
        "max_drawdown_pct": round(dd * 100.0, 4),
        "calmar": round(calmar, 4),
    }
