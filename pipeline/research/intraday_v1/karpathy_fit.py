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


def objective(weights: np.ndarray, df: pd.DataFrame) -> float:
    """Robust-Sharpe scalar objective per §5.

    `df` columns: date, instrument, f1..f6, next_return_pct.
    """
    feat = df[FEATURE_COLS].to_numpy()
    score = feat @ weights  # per-row signal strength
    df = df.copy()
    df["score"] = score
    # daily basket return = mean of next_return_pct of rows whose score > daily-90th-percentile
    # (long-only proxy here — full direction handled at runner; objective stays simple)
    daily = []
    for date, group in df.groupby("date", sort=True):
        if group.empty:
            continue
        thresh = group["score"].quantile(0.7)
        firers = group[group["score"] >= thresh]
        if firers.empty:
            daily.append(0.0)
            continue
        daily.append(float(firers["next_return_pct"].mean()))
    if len(daily) < ROLLING_WINDOW_DAYS:
        return float("-inf")
    daily_arr = np.array(daily)
    rolling_sharpes = []
    for i in range(len(daily_arr) - ROLLING_WINDOW_DAYS + 1):
        win = daily_arr[i:i + ROLLING_WINDOW_DAYS]
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


def run(df: pd.DataFrame, seed: int = 42, n_iters: int = 2000) -> Dict:
    """Random search over weight space, return best weight vector + thresholds.

    Returns: {"weights": ndarray(6,), "objective": float,
              "long_threshold": float, "short_threshold": float, "seed": int}
    """
    rng = np.random.default_rng(seed)
    best = {"weights": None, "objective": float("-inf")}
    for _ in range(n_iters):
        w = rng.uniform(-WEIGHT_BOUND, WEIGHT_BOUND, size=6)
        j = objective(w, df)
        if j > best["objective"]:
            best = {"weights": w, "objective": j}
    if best["weights"] is None:
        raise RuntimeError("Random search failed to find any weight vector — empty in-sample?")
    feat = df[FEATURE_COLS].to_numpy()
    scores = feat @ best["weights"]
    long_thresh = float(np.quantile(scores, 0.7))
    short_thresh = float(np.quantile(scores, 0.3))
    return {
        "weights": best["weights"],
        "objective": best["objective"],
        "long_threshold": long_thresh,
        "short_threshold": short_thresh,
        "seed": seed,
    }
