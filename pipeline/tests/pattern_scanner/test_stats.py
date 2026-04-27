"""Stats engine tests on synthetic panels with known win rates."""
from datetime import date
import math
import numpy as np
import pandas as pd
from pipeline.pattern_scanner.stats import (
    aggregate_pattern_cell, walk_forward_fold_stability, compute_z_score,
)


def test_z_score_perfect_winrate_on_30():
    z = compute_z_score(win_rate=1.0, n=30)
    # (1.0 - 0.5) / sqrt(0.25/30) ~ 5.477
    assert math.isclose(z, 5.477, rel_tol=1e-2)


def test_z_score_coinflip_zero():
    assert compute_z_score(win_rate=0.5, n=100) == 0.0


def test_z_score_zero_n_returns_nan():
    assert math.isnan(compute_z_score(win_rate=0.6, n=0))


def test_aggregate_60_percent_winrate():
    """100 fires, 60 wins (returns >= +0.008), 40 losses (returns < +0.008)."""
    fire_dates = [(pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)).date() for i in range(100)]
    returns = [0.012] * 60 + [0.001] * 40  # bullish: win = return >= +0.008
    cell = aggregate_pattern_cell(
        ticker="TEST", pattern_id="BULLISH_HAMMER", direction="LONG",
        fire_dates=fire_dates, returns=returns, win_threshold=0.008)
    assert cell["n_occurrences"] == 100
    assert cell["wins"] == 60
    assert cell["losses"] == 40
    assert math.isclose(cell["win_rate"], 0.6, rel_tol=1e-9)
    assert cell["z_score"] > 1.9  # stat-significant against H0=0.5


def test_aggregate_short_pattern_signed_pnl():
    """SHORT pattern: pnl is -return. A -1% drop is a +1% trade pnl."""
    fire_dates = [(pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)).date() for i in range(20)]
    returns = [-0.012] * 12 + [0.001] * 8  # drop of 1.2% counts as win for SHORT
    cell = aggregate_pattern_cell(
        ticker="TEST", pattern_id="SHOOTING_STAR", direction="SHORT",
        fire_dates=fire_dates, returns=returns, win_threshold=0.008)
    assert cell["wins"] == 12
    assert cell["mean_pnl_pct"] > 0  # signed P&L is positive overall


def test_walk_forward_stable_pattern_high_ratio():
    """Stable pattern across 4 folds -> high stability ratio."""
    fold_win_rates = [0.60, 0.62, 0.59, 0.61]
    ratio = walk_forward_fold_stability(fold_win_rates)
    assert ratio > 0.9


def test_walk_forward_unstable_pattern_low_ratio():
    fold_win_rates = [0.85, 0.30, 0.70, 0.45]
    ratio = walk_forward_fold_stability(fold_win_rates)
    assert ratio < 0.5


def test_walk_forward_zero_mean_returns_zero():
    assert walk_forward_fold_stability([0.0, 0.0, 0.0, 0.0]) == 0.0
