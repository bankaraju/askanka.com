"""Karpathy random-search optimizer + robust-Sharpe objective.

Per spec §5:
- Search space: w in [-2, +2]^6, uniform random sampling, n_iters=2000.
- Objective J(w) = AvgRollingSharpe - 0.5*StdRollingSharpe - 0.1*Turnover - 1.0*MaxDD.
- Rolling window 10 trading days, sliding by 1 day across in-sample.
- Reproducible: fixed seed yields identical fit.
- Pooled fit: one weight vector across all instruments in the pool.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

LAMBDA_VAR = 0.5
LAMBDA_TURNOVER = 0.1
LAMBDA_DD = 1.0
ROLLING_WINDOW_DAYS = 10
WEIGHT_BOUND = 2.0
FEATURE_COLS = ["f1", "f2", "f3", "f4", "f5", "f6"]


def objective(
    weights: np.ndarray,
    df: pd.DataFrame,
    rolling_window_days: int = ROLLING_WINDOW_DAYS,
) -> float:
    """Robust-Sharpe scalar objective per §5.

    `df` columns: date, instrument, f1..f6, next_return_pct.

    ``rolling_window_days`` defaults to the spec constant (10). Pass a smaller
    value ONLY at kickoff (insufficient in-sample days) — production monthly
    recalibrate keeps the default. Returns -inf when fewer than
    ``rolling_window_days`` distinct dates are present.
    """
    feat = df[FEATURE_COLS].to_numpy()
    score = feat @ weights  # per-row signal strength
    df = df.copy()
    df["score"] = score
    # Long-short basket return per spec §4: long when score >= per-day 0.7 quantile,
    # short when score <= per-day 0.3 quantile. Daily P&L = mean(longs.next_return) -
    # mean(shorts.next_return). Matches runtime direction-handling so in-sample
    # weights actually optimize the deployed payoff.
    daily = []
    for date, group in df.groupby("date", sort=True):
        if group.empty:
            continue
        long_thresh = group["score"].quantile(0.7)
        short_thresh = group["score"].quantile(0.3)
        longs = group[group["score"] >= long_thresh]
        shorts = group[group["score"] <= short_thresh]
        long_ret = float(longs["next_return_pct"].mean()) if not longs.empty else 0.0
        short_ret = float(shorts["next_return_pct"].mean()) if not shorts.empty else 0.0
        # Long-short payoff: gain on longs going up, gain on shorts going down.
        # Zero-variance day (long_thresh == short_thresh) → both baskets equal →
        # contribution mean - mean = 0, which degrades naturally without a special case.
        daily.append(long_ret - short_ret)
    if len(daily) < rolling_window_days:
        return float("-inf")
    daily_arr = np.array(daily)
    rolling_sharpes = []
    for i in range(len(daily_arr) - rolling_window_days + 1):
        win = daily_arr[i:i + rolling_window_days]
        s = float(win.mean()) / (float(win.std()) + 1e-9)
        rolling_sharpes.append(s)
    rolling = np.array(rolling_sharpes)
    avg_sharpe = float(rolling.mean())
    std_sharpe = float(rolling.std())
    cum = np.cumsum(daily_arr)
    peak = np.maximum.accumulate(cum)
    dd = float((peak - cum).max())
    turnover = float(np.abs(np.diff(weights)).sum() if len(weights) > 1 else 0.0)
    return avg_sharpe - LAMBDA_VAR * std_sharpe - LAMBDA_TURNOVER * turnover - LAMBDA_DD * dd


def run(
    df: pd.DataFrame,
    seed: int = 42,
    n_iters: int = 2000,
    rolling_window_days: int = ROLLING_WINDOW_DAYS,
) -> Dict:
    """Random search over weight space, return best weight vector + thresholds.

    Optimizes the long-short objective per spec §4: longs are rows in the daily
    top-30% of score (score >= per-day 0.7 quantile), shorts are rows in the
    daily bottom-30% (score <= per-day 0.3 quantile), and the daily P&L is
    mean(longs.next_return_pct) - mean(shorts.next_return_pct). Threshold
    extraction below uses the in-sample pooled scores (0.3 / 0.7 quantiles) and
    is independent of the per-day objective computation.

    ``rolling_window_days`` defaults to the spec constant (10). The kickoff
    fit may pass a smaller value when the in-sample window does not yet
    contain 10 distinct trading days — the default is preserved for
    production monthly recalibrate.

    Returns: {"weights": ndarray(6,), "objective": float,
              "long_threshold": float, "short_threshold": float, "seed": int,
              "rolling_window_days": int}
    """
    rng = np.random.default_rng(seed)
    best = {"weights": None, "objective": float("-inf")}
    for _ in range(n_iters):
        w = rng.uniform(-WEIGHT_BOUND, WEIGHT_BOUND, size=6)
        j = objective(w, df, rolling_window_days=rolling_window_days)
        if j > best["objective"]:
            best = {"weights": w, "objective": j}
    if best["weights"] is None:
        raise RuntimeError("Random search failed to find any weight vector — empty in-sample?")
    feat = df[FEATURE_COLS].to_numpy()
    scores = feat @ best["weights"]
    long_thresh = float(np.quantile(scores, 0.7))
    short_thresh = float(np.quantile(scores, 0.3))
    if long_thresh <= short_thresh:
        raise ValueError(
            "Degenerate thresholds: long_threshold <= short_threshold. "
            "In-sample feature variance is near-zero — check loader output."
        )
    return {
        "weights": best["weights"],
        "objective": best["objective"],
        "long_threshold": long_thresh,
        "short_threshold": short_thresh,
        "seed": seed,
        "rolling_window_days": rolling_window_days,
    }
