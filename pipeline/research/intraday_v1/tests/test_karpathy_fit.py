"""Tests karpathy_fit.py — random search + robust-Sharpe objective."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import karpathy_fit


def _synthetic_in_sample(n_days: int = 30, n_inst: int = 10, seed: int = 0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(n_inst):
            features = rng.normal(0, 1, 6)
            label = float(np.dot(features, [0.5, -0.3, 0.2, 0.1, 0.0, 0.4])) + rng.normal(0, 0.5)
            rows.append({
                "date": f"2026-03-{1+d:02d}",
                "instrument": f"INST{i}",
                "f1": features[0], "f2": features[1], "f3": features[2],
                "f4": features[3], "f5": features[4], "f6": features[5],
                "next_return_pct": label,
            })
    return pd.DataFrame(rows)


def test_objective_robust_sharpe_returns_finite():
    df = _synthetic_in_sample()
    weights = np.array([0.5, -0.3, 0.2, 0.1, 0.0, 0.4])
    j = karpathy_fit.objective(weights, df)
    assert np.isfinite(j)


def test_random_search_reproducible_with_seed():
    df = _synthetic_in_sample()
    fit_a = karpathy_fit.run(df, seed=42, n_iters=50)
    fit_b = karpathy_fit.run(df, seed=42, n_iters=50)
    assert np.allclose(fit_a["weights"], fit_b["weights"])
    assert fit_a["objective"] == fit_b["objective"]


def test_different_seed_produces_different_weights():
    df = _synthetic_in_sample()
    fit_a = karpathy_fit.run(df, seed=1, n_iters=50)
    fit_b = karpathy_fit.run(df, seed=2, n_iters=50)
    assert not np.allclose(fit_a["weights"], fit_b["weights"])


def test_run_returns_thresholds():
    df = _synthetic_in_sample()
    fit = karpathy_fit.run(df, seed=42, n_iters=50)
    assert "long_threshold" in fit
    assert "short_threshold" in fit
    assert fit["long_threshold"] > fit["short_threshold"]


def test_run_emits_weight_vector_in_bounds():
    df = _synthetic_in_sample()
    fit = karpathy_fit.run(df, seed=42, n_iters=50)
    assert all(-2.0 <= w <= 2.0 for w in fit["weights"])


def test_objective_is_long_short_not_long_only():
    """Spec §4: longs profit on up moves, shorts profit on down moves.

    Build a 5-day panel where the long-side (top-30% by score) returns are flat 0%
    while the short-side (bottom-30% by score) returns are -2% (i.e., shorts make
    money). A long-only objective sees ~0; the long-short objective sees ~+2%.
    The rolling-Sharpe wrapper requires >= ROLLING_WINDOW_DAYS (10) days, so we
    extend the panel to 12 days.
    """
    n_days = 12
    n_inst = 10
    rows = []
    # weights = [1, 0, 0, 0, 0, 0]: f1 IS the score. We arrange:
    #  - Top-30% (3 highest f1) → next_return_pct = 0.0  (long basket flat)
    #  - Bottom-30% (3 lowest f1) → next_return_pct = -2.0  (short basket down 2%)
    #  - Middle rows → 0.0 (irrelevant; not in either basket)
    for d in range(n_days):
        # Sort instruments 0..9 by f1 ascending: instrument k gets f1=k.
        for k in range(n_inst):
            f1 = float(k)  # 0..9
            # bottom-30% = k in {0,1,2}; top-30% = k in {7,8,9}
            if k <= 2:
                ret = -2.0
            elif k >= 7:
                ret = 0.0
            else:
                ret = 0.0
            rows.append({
                "date": f"2026-03-{1+d:02d}",
                "instrument": f"INST{k}",
                "f1": f1, "f2": 0.0, "f3": 0.0, "f4": 0.0, "f5": 0.0, "f6": 0.0,
                "next_return_pct": ret,
            })
    df = pd.DataFrame(rows)
    weights = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # Inspect the daily basket math directly to assert long-short, not long-only.
    feat = df[karpathy_fit.FEATURE_COLS].to_numpy()
    df_local = df.copy()
    df_local["score"] = feat @ weights
    daily = []
    for _, group in df_local.groupby("date", sort=True):
        long_thresh = group["score"].quantile(0.7)
        short_thresh = group["score"].quantile(0.3)
        longs = group[group["score"] >= long_thresh]
        shorts = group[group["score"] <= short_thresh]
        long_ret = float(longs["next_return_pct"].mean())
        short_ret = float(shorts["next_return_pct"].mean())
        daily.append(long_ret - short_ret)

    daily_arr = np.array(daily)
    # Long-only would yield ~0 each day. Long-short should yield 0 - (-2) = +2 each day.
    assert np.allclose(daily_arr, 2.0), (
        f"Expected long-short daily P&L of +2.0 per day, got {daily_arr.tolist()}"
    )

    # Now confirm objective() consumes that long-short P&L. Rolling 10-day Sharpe
    # of a constant +2.0 series → mean=2, std=0 → Sharpe huge (numerator-bound).
    # The objective is finite (penalties subtract DD/turnover/var) but must be
    # MUCH larger than the long-only equivalent (which would be ~0).
    j_long_short = karpathy_fit.objective(weights, df)
    assert np.isfinite(j_long_short)
    assert j_long_short > 100.0, (
        f"Expected long-short objective >> 0 on this panel, got {j_long_short}"
    )


def test_run_accepts_smaller_rolling_window_for_kickoff():
    """Kickoff path: when in-sample has < ROLLING_WINDOW_DAYS distinct dates,
    the caller may pass a smaller ``rolling_window_days`` and the fit still
    completes. The default value (10) remains unchanged for production.
    """
    # 6 days of in-sample — below the default 10-day rolling window.
    df = _synthetic_in_sample(n_days=6, n_inst=10, seed=0)
    fit = karpathy_fit.run(df, seed=42, n_iters=50, rolling_window_days=3)
    assert "weights" in fit
    assert fit["rolling_window_days"] == 3
    # Default still 10 (spec constant unchanged)
    assert karpathy_fit.ROLLING_WINDOW_DAYS == 10


def test_run_default_rolling_window_unchanged_at_10():
    """Sanity: production monthly recalibrate uses the default — 10 days."""
    df = _synthetic_in_sample(n_days=30, n_inst=10, seed=0)
    fit = karpathy_fit.run(df, seed=42, n_iters=50)
    assert fit["rolling_window_days"] == 10


def test_objective_returns_neg_inf_below_rolling_window_days():
    """If distinct dates < rolling_window_days, objective returns -inf."""
    import numpy as _np
    df = _synthetic_in_sample(n_days=4, n_inst=5, seed=0)
    weights = _np.array([0.1, 0.2, -0.1, 0.0, 0.3, -0.2])
    j = karpathy_fit.objective(weights, df, rolling_window_days=10)
    assert j == float("-inf")
    # With smaller window, finite.
    j2 = karpathy_fit.objective(weights, df, rolling_window_days=3)
    assert _np.isfinite(j2)


def test_run_recovers_long_short_optimal_weights_on_synthetic():
    """Optimizer should learn weights[0] > 0.5 when f1 ranks rows long-short-correctly.

    Construct a panel where, for each day:
      - Top-30% by f1 has next_return_pct = +1.0 (longs win)
      - Bottom-30% by f1 has next_return_pct = -1.0 (shorts win when shorted)
      - Middle rows: 0.0
    The long-short P&L = +1.0 - (-1.0) = +2.0/day with weights = [+, 0, 0, 0, 0, 0].
    With weights[0] negative, the basket assignments flip and P&L becomes -2.0/day.
    The optimizer must therefore prefer a positive (and large) weights[0].
    """
    n_days = 30
    n_inst = 10
    rows = []
    for d in range(n_days):
        for k in range(n_inst):
            f1 = float(k)  # 0..9
            if k >= 7:
                ret = 1.0
            elif k <= 2:
                ret = -1.0
            else:
                ret = 0.0
            rows.append({
                "date": f"2026-03-{1+d:02d}",
                "instrument": f"INST{k}",
                "f1": f1, "f2": 0.0, "f3": 0.0, "f4": 0.0, "f5": 0.0, "f6": 0.0,
                "next_return_pct": ret,
            })
    df = pd.DataFrame(rows)
    fit = karpathy_fit.run(df, seed=42, n_iters=2000)
    assert fit["weights"][0] > 0.5, (
        f"Expected weights[0] > 0.5 (long-short-optimal), got {fit['weights'][0]}"
    )
