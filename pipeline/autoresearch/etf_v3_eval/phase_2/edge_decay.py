# pipeline/autoresearch/etf_v3_eval/phase_2/edge_decay.py
"""§12 edge decay — rolling 12-month Sharpe + CUSUM regime-change detector.

rolling_12mo_sharpe:
    Computes a per-day rolling-window risk-adjusted return (annualised Sharpe).
    NaN values in the output indicate either insufficient data in the window
    (leading NaNs) or insufficient variance within the window (constant series).
    Both are by design — callers should not suppress them.

cusum_regime_change:
    Two-sided CUSUM detector. Returns positional indices where the cumulative
    sum of deviations from `target_mean` exceeds `threshold * σ`.

    `target_mean` defaults to 0.0, which means the algorithm detects when
    daily P&L drifts AWAY from positive expectation back toward zero or
    negative — the standard "edge decay" use case. Pass the in-sample mean
    if you want to detect deviations relative to a known prior level.

    On each trigger the accumulators are reset to zero; this is the standard
    CUSUM reset that prevents the same regime break from triggering repeatedly
    within the very next bar.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd


def rolling_12mo_sharpe(
    daily_pnl: pd.Series,
    window: int = 252,
) -> pd.Series:
    """Rolling annualised Sharpe ratio.

    Parameters
    ----------
    daily_pnl:
        Daily P&L (or return) series.
    window:
        Look-back window in trading days (default 252 ≈ 12 months).

    Returns
    -------
    pd.Series
        Same index as ``daily_pnl``. Leading values within the first
        ``window - 1`` bars are NaN (insufficient history). Values where
        the rolling standard deviation is zero are NaN (insufficient
        variance) — this is intentional; do not suppress.
    """
    if len(daily_pnl) == 0:
        return pd.Series([], dtype=float)

    roll_mean = daily_pnl.rolling(window).mean()
    roll_std = daily_pnl.rolling(window).std(ddof=1)
    # NaN where std == 0 (constant window) is by design; indicates no variance
    return (roll_mean / roll_std) * np.sqrt(252)


def cusum_regime_change(
    daily_pnl: pd.Series,
    threshold: float = 3.0,
    target_mean: float = 0.0,
) -> List[int]:
    """Two-sided CUSUM detector.

    Returns positional indices where the cumulative sum of deviations from
    ``target_mean`` exceeds ``threshold * σ`` in either direction.

    Parameters
    ----------
    daily_pnl:
        Daily P&L (or return) series.
    threshold:
        Number of standard deviations that triggers a detection.
    target_mean:
        The reference level deviations are measured against. Defaults to
        0.0 (detect when daily P&L drifts back to zero / negative).
        Pass the in-sample mean to detect decay relative to a known prior.

    Returns
    -------
    List[int]
        Positional indices (0-based) of detected regime breaks.
    """
    if len(daily_pnl) == 0:
        return []

    # Floor std at 1e-12 (consistent with T13/T17/T19 idiom) to avoid
    # division-by-zero on perfectly constant series.
    sigma = max(float(daily_pnl.std(ddof=1)), 1e-12)
    limit = threshold * sigma

    pos, neg = 0.0, 0.0
    triggers: List[int] = []

    for i, x in enumerate(daily_pnl.values):
        deviation = float(x) - target_mean
        pos = max(0.0, pos + deviation)
        # neg accumulates negative deviations; kept ≤ 0 so abs() gives magnitude
        neg = min(0.0, neg + deviation)

        if pos > limit or abs(neg) > limit:
            triggers.append(i)
            # Reset both accumulators so the same break does not keep firing
            # on every subsequent bar within the same regime shift.
            pos, neg = 0.0, 0.0

    return triggers
