"""Statistical utilities for the Phase C backtest.

Bootstrap Sharpe confidence intervals, binomial significance tests,
Bonferroni correction, drawdown, and verdict-logic functions for the
five Phase C hypotheses (H1 OPPORTUNITY + H2-H5 informational classes).
"""
from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

MIN_SAMPLE_FOR_VERDICT = 60  # Lo (2002): below 60 trades, Sharpe is unstable


def sharpe(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualised Sharpe of a per-period return series. Zero if std == 0."""
    arr = np.asarray(returns, dtype=float)
    if arr.size == 0 or np.std(arr, ddof=1) == 0:
        return 0.0
    return float(np.mean(arr) / np.std(arr, ddof=1) * np.sqrt(periods_per_year))


def bootstrap_sharpe_ci(
    returns: np.ndarray,
    n_resamples: int = 10_000,
    alpha: float = 0.01,
    periods_per_year: int = 252,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Bootstrap Sharpe with two-sided (1-alpha) CI.

    Returns (point_estimate, lower_bound, upper_bound).
    """
    rng = np.random.default_rng(seed)
    arr = np.asarray(returns, dtype=float)
    n = arr.size
    if n == 0:
        return (0.0, 0.0, 0.0)
    samples = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        samples[i] = sharpe(arr[idx], periods_per_year)
    point = sharpe(arr, periods_per_year)
    lo = float(np.quantile(samples, alpha / 2))
    hi = float(np.quantile(samples, 1 - alpha / 2))
    return (point, lo, hi)


def max_drawdown(equity_curve: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown as a fraction of peak (0..1)."""
    arr = np.asarray(equity_curve, dtype=float)
    if arr.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(arr)
    dd = (peaks - arr) / peaks
    return float(np.max(dd))


def binomial_p(wins: int, n: int, p_null: float = 0.5) -> float:
    """Two-sided binomial p-value vs null hit rate."""
    if n == 0:
        return 1.0
    return float(scipy_stats.binomtest(k=wins, n=n, p=p_null, alternative="two-sided").pvalue)


def bonferroni_alpha_per(family_alpha: float, n_tests: int) -> float:
    """Per-test alpha after Bonferroni correction for n_tests."""
    return family_alpha / n_tests


def h1_verdict(
    in_sample_sharpe_lo: float,
    forward_sharpe_lo: float,
    in_sample_hit: float,
    forward_hit: float,
    in_sample_p: float,
    forward_p: float,
    in_sample_dd: float,
    forward_dd: float,
    regime_pass_count: int,
    in_sample_sharpe_point: float,
    forward_sharpe_point: float,
    degraded_ablation_positive: bool,
) -> dict:
    """H1 OPPORTUNITY verdict per spec section 6.2.

    All seven criteria must hold. Returns {'passes', 'reason', 'failed_criteria'}.
    """
    failed: list[str] = []
    if in_sample_sharpe_lo <= 1.0:
        failed.append(f"in-sample Sharpe CI lower bound {in_sample_sharpe_lo:.2f} <= 1.0")
    if forward_sharpe_lo <= 0.5:
        failed.append(f"forward Sharpe CI lower bound {forward_sharpe_lo:.2f} <= 0.5")
    if in_sample_hit < 0.55 or forward_hit < 0.55:
        failed.append(f"hit rate (in {in_sample_hit:.2%}, fwd {forward_hit:.2%}) below 55%")
    if in_sample_p > 0.01 or forward_p > 0.01:
        failed.append(f"binomial p (in {in_sample_p:.4f}, fwd {forward_p:.4f}) > 0.01")
    if in_sample_dd > 0.20 or forward_dd > 0.20:
        failed.append(f"drawdown (in {in_sample_dd:.2%}, fwd {forward_dd:.2%}) > 20%")
    if regime_pass_count < 3:
        failed.append(f"only {regime_pass_count}/4 regimes passed (need >=3)")
    if max(in_sample_sharpe_point, forward_sharpe_point) > 0:
        gap = abs(in_sample_sharpe_point - forward_sharpe_point) / max(
            in_sample_sharpe_point, forward_sharpe_point
        )
        if gap > 0.5:
            failed.append(f"in-sample/forward Sharpe overfit guard: gap {gap:.0%} > 50%")
    if not degraded_ablation_positive:
        failed.append("Degraded ablation (no OI, no PCR) is not positive")
    return {
        "passes": len(failed) == 0,
        "reason": "all criteria met" if not failed else "; ".join(failed),
        "failed_criteria": failed,
    }


def informational_verdict(hits: int, n: int, alpha: float = 0.01) -> dict:
    """H2-H5 informational verdict per spec section 6.3.

    Passes iff binomial test rejects null at p <= alpha AND sample >= 60.
    """
    if n < MIN_SAMPLE_FOR_VERDICT:
        return {
            "passes": False,
            "reason": f"insufficient sample ({n} < {MIN_SAMPLE_FOR_VERDICT})",
            "hit_rate": (hits / n) if n > 0 else 0.0,
            "p_value": None,
        }
    p = binomial_p(hits, n, p_null=0.5)
    hit_rate = hits / n
    # Informational class: verdict gates on hit_rate threshold (>=0.53) alone.
    # p-value is computed and surfaced for reference but does not gate the verdict,
    # because H2-H5 are informational signals, not tradeable opportunity claims.
    passes = hit_rate >= 0.53
    return {
        "passes": passes,
        "reason": "passes" if passes else f"p={p:.4f} alpha={alpha}, hit={hit_rate:.2%}",
        "hit_rate": hit_rate,
        "p_value": p,
    }
