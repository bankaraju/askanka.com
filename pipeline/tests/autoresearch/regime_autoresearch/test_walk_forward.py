"""Tests for K-fold time-series CV in the in-sample runner (Task #191)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.regime_autoresearch._walk_forward import (
    MIN_EVENTS_PER_FOLD, split_walk_forward,
)
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    run_in_sample,
)


# ---------------------------------------------------------------------------
# split_walk_forward
# ---------------------------------------------------------------------------


def test_split_walk_forward_basic_4_fold():
    """40 event dates -> 4 folds of 10 each before embargo; after 2-day
    embargo, folds 1-3 lose 2 events each (8 events) and fold 0 keeps
    all 10.
    """
    dates = pd.bdate_range("2022-01-03", periods=40)
    folds = split_walk_forward(dates, n_folds=4, embargo_days=2)
    assert len(folds) == 4
    assert len(folds[0]) == 10  # no embargo on first fold
    assert len(folds[1]) == 8
    assert len(folds[2]) == 8
    assert len(folds[3]) == 8
    # Folds are strictly chronologically ordered — fold k+1 starts after
    # fold k ends.
    for i in range(len(folds) - 1):
        assert folds[i][-1] < folds[i + 1][0]


def test_split_walk_forward_embargo_matches_hold_horizon():
    """embargo=5 should drop 5 events from each post-first fold, not 2."""
    dates = pd.bdate_range("2022-01-03", periods=40)
    folds = split_walk_forward(dates, n_folds=4, embargo_days=5)
    assert len(folds[0]) == 10
    assert len(folds[1]) == 5  # 10 - 5 embargo
    assert len(folds[2]) == 5
    assert len(folds[3]) == 5


def test_split_walk_forward_drops_tiny_folds():
    """When embargo shrinks post-first folds below MIN_EVENTS_PER_FOLD=5,
    those folds are dropped from the return list.
    """
    # 24 events, K=4 -> 6 per chunk; embargo=2 drops fold 1-3 to 4
    # events each, which is below MIN_EVENTS_PER_FOLD=5 — only fold 0
    # should survive. But that means <2 folds, so ValueError.
    dates = pd.bdate_range("2022-01-03", periods=24)
    with pytest.raises(ValueError, match="insufficient events"):
        split_walk_forward(dates, n_folds=4, embargo_days=2)

    # With 40 events: chunks of 10, embargo=2 -> post-first folds have 8
    # events each which is >= MIN_EVENTS_PER_FOLD, so all 4 survive.
    dates40 = pd.bdate_range("2022-01-03", periods=40)
    folds = split_walk_forward(dates40, n_folds=4, embargo_days=2)
    assert len(folds) == 4

    # With 36 events: chunks of 9, embargo=5 -> post-first folds have 4
    # events each (below MIN), dropped. Only fold 0 (9 events) survives,
    # which is < 2 folds, so ValueError.
    dates36 = pd.bdate_range("2022-01-03", periods=36)
    with pytest.raises(ValueError, match="insufficient events"):
        split_walk_forward(dates36, n_folds=4, embargo_days=5)


def test_split_walk_forward_insufficient_raises():
    """3 event dates, K=4 -> two-chunk 0-event folds and a 1-event fold;
    all below MIN_EVENTS_PER_FOLD -> ValueError.
    """
    dates = pd.DatetimeIndex(
        ["2022-01-03", "2022-01-04", "2022-01-05"]
    )
    with pytest.raises(ValueError, match="insufficient events"):
        split_walk_forward(dates, n_folds=4, embargo_days=2)


def test_split_walk_forward_handles_unsorted_and_duplicates():
    """Input is de-duplicated and sorted internally — the same set of
    dates passed in any order produces the same folds.
    """
    dates_in_order = pd.bdate_range("2022-01-03", periods=40)
    dates_out_of_order = pd.DatetimeIndex(
        list(dates_in_order[::-1]) + [dates_in_order[0]]  # reversed + duplicate
    )
    folds_a = split_walk_forward(dates_in_order, n_folds=4, embargo_days=2)
    folds_b = split_walk_forward(dates_out_of_order, n_folds=4, embargo_days=2)
    assert len(folds_a) == len(folds_b)
    for a, b in zip(folds_a, folds_b):
        assert list(a) == list(b)


# ---------------------------------------------------------------------------
# run_in_sample with folds
# ---------------------------------------------------------------------------


def _synthetic_panel(seed: int = 1, n_days: int = 500, n_tickers: int = 8):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    tickers = [f"T{i}" for i in range(n_tickers)]
    rows = []
    for d in dates:
        for t in tickers:
            rows.append({
                "date": d,
                "ticker": t,
                "close": 100 + rng.standard_normal() * 5,
                "volume": 1e6,
                "regime_zone": "NEUTRAL",
            })
    return pd.DataFrame(rows), dates, tickers


def test_run_in_sample_with_folds_aggregates_mean(tmp_path, monkeypatch):
    """4-fold run aggregates per-fold Sharpes via mean, reports OOS sigma
    via sample-stddev, and fold_sharpes has K entries.

    We stub `_compile_proposal_returns` to return a controlled set of
    returns per fold so fold Sharpes are deterministic and distinct.
    """
    from pipeline.autoresearch.regime_autoresearch import in_sample_runner

    panel, _dates, tickers = _synthetic_panel(seed=1, n_days=200)
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))[:40]

    # Stub: return a different distribution per fold call so mean/std are
    # non-trivial. We key off the number of events passed in (each fold
    # has a distinct length after embargo: 10, 8, 8, 8).
    # Each fold's returns must have std > 0 so _net_sharpe is non-zero
    # and the per-fold Sharpes are distinct enough to produce a non-zero
    # OOS sigma.
    rng = np.random.default_rng(42)
    call_counter = {"n": 0}
    returns_by_call = [
        # fold 0: strong positive, tight spread -> high Sharpe
        pd.Series(rng.normal(0.020, 0.010, 10), dtype=float),
        # fold 1: mild positive
        pd.Series(rng.normal(0.010, 0.015, 8), dtype=float),
        # fold 2: strong positive, different mean
        pd.Series(rng.normal(0.030, 0.012, 8), dtype=float),
        # fold 3: negative — this is the one that pulls the mean down
        pd.Series(rng.normal(-0.010, 0.015, 8), dtype=float),
    ]

    def fake_compile(p, panel, event_dates_arg, tickers_arg):
        i = call_counter["n"]
        call_counter["n"] += 1
        return returns_by_call[i]

    monkeypatch.setattr(
        in_sample_runner, "_compile_proposal_returns", fake_compile,
    )

    p = Proposal("single_long", "ret_5d", ">", 0.5, 5, "NEUTRAL", None)
    log_path = tmp_path / "proposal_log.jsonl"
    result = run_in_sample(
        p, panel, log_path=log_path, incumbent_sharpe=0.0,
        event_dates=event_dates, tickers=tickers, n_folds=4,
    )

    assert result["insufficient_for_folds"] is False
    assert result["fold_sharpes"] is not None
    assert len(result["fold_sharpes"]) == 4
    assert result["fold_n_events"] == [10, 8, 8, 8]
    # net_sharpe_mean = mean of fold sharpes
    expected_mean = round(float(np.mean(result["fold_sharpes"])), 4)
    assert result["net_sharpe_in_sample"] == pytest.approx(
        expected_mean, abs=1e-4,
    )
    # OOS sigma > 0 given the distinct fold distributions.
    assert result["sharpe_oos_std"] > 0.0
    # n_events_in_sample = sum of fold counts
    assert result["n_events_in_sample"] == 10 + 8 + 8 + 8


def test_run_in_sample_falls_back_on_insufficient_events(tmp_path, monkeypatch):
    """With only 3 event_dates and K=4, fold split raises and the
    runner falls back to a single-pass evaluation with
    `insufficient_for_folds=True` in the log row.
    """
    from pipeline.autoresearch.regime_autoresearch import in_sample_runner

    panel, _dates, tickers = _synthetic_panel(seed=2, n_days=50)
    event_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))[:3]

    # Stub compile to return 3 mild-positive returns.
    def fake_compile(p, panel, event_dates_arg, tickers_arg):
        return pd.Series([0.01, 0.02, 0.015], dtype=float)

    monkeypatch.setattr(
        in_sample_runner, "_compile_proposal_returns", fake_compile,
    )

    p = Proposal("single_long", "ret_5d", ">", 0.5, 5, "NEUTRAL", None)
    log_path = tmp_path / "proposal_log.jsonl"
    result = run_in_sample(
        p, panel, log_path=log_path, incumbent_sharpe=0.0,
        event_dates=event_dates, tickers=tickers, n_folds=4,
    )

    assert result["insufficient_for_folds"] is True
    assert result["fold_sharpes"] is None
    assert result["fold_n_events"] is None
    assert result["sharpe_oos_std"] is None
    assert result["n_events_in_sample"] == 3
    # net_sharpe_in_sample is still computed from the single-pass path.
    assert result["net_sharpe_in_sample"] is not None
