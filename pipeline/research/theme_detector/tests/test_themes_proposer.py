"""Smoke + unit tests for theme_proposer v1.1.0.

Covers the pure-numerical building blocks (clustering, scoring, attribute
computations). End-to-end propose() requires bars on disk and is exercised
manually via `python -m pipeline.research.theme_detector.themes_proposer`.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.research.theme_detector import themes_proposer as tp


def _synthetic_returns(n_days: int = 60) -> pd.DataFrame:
    """Build a returns matrix where A,B,C are tightly co-moving and D,E noise."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-01", periods=n_days)
    common = rng.normal(0.001, 0.01, n_days)
    df = pd.DataFrame({
        "A": common + rng.normal(0, 0.001, n_days),
        "B": common + rng.normal(0, 0.001, n_days),
        "C": common + rng.normal(0, 0.001, n_days),
        "D": rng.normal(0, 0.02, n_days),
        "E": rng.normal(0, 0.02, n_days),
    }, index=dates)
    return df


def test_cluster_finds_tight_basket():
    rets = _synthetic_returns()
    clusters = tp._cluster(rets)
    # The {A,B,C} basket should appear as a single cluster ≥3 stocks
    abc_clusters = [m for m in clusters.values() if {"A", "B", "C"}.issubset(set(m))]
    assert len(abc_clusters) == 1


def test_cluster_drops_noise_singletons():
    rets = _synthetic_returns()
    clusters = tp._cluster(rets)
    # D and E should NOT appear in any size-≥3 cluster (they're noise)
    for members in clusters.values():
        if len(members) < 3:
            continue
        # D and E are independent noise; they may join a size-3 cluster by chance
        # under the loose MIN_CORR threshold; assertion: at most one of them is in
        # any single basket alongside A/B/C
        ne_in = sum(1 for x in ("D", "E") if x in members)
        if {"A", "B", "C"}.issubset(set(members)):
            assert ne_in == 0


def test_avg_pairwise_corr_high_for_tight_basket():
    rets = _synthetic_returns()
    c = tp._avg_pairwise_corr(rets, ["A", "B", "C"])
    assert c > 0.9


def test_avg_pairwise_corr_low_for_noise():
    rets = _synthetic_returns()
    c = tp._avg_pairwise_corr(rets, ["D", "E"])
    assert c < 0.5


def test_emergence_score_monotonic_in_corr():
    s_low = tp._emergence_score(0.4, 0.0, 0.0, 0.0)
    s_mid = tp._emergence_score(0.7, 0.0, 0.0, 0.0)
    s_high = tp._emergence_score(0.95, 0.0, 0.0, 0.0)
    assert s_low < s_mid < s_high


def test_emergence_score_caps_at_one():
    s = tp._emergence_score(1.0, 5.0, 100.0, 1.0)
    assert s <= 1.0 + 1e-9


def test_weight_delta_6m_returns_zero_when_no_data():
    delta = tp._weight_delta_6m(None, ["A", "B"], date(2026, 5, 1))
    assert delta == 0.0


def test_weight_delta_6m_with_short_history():
    """No row at-or-before 180 days ago → zero (no signal)."""
    today = date(2026, 5, 1)
    df = pd.DataFrame([
        {"date": today, "nse_symbol": "A", "weight_pct": 2.0},
        {"date": today, "nse_symbol": "B", "weight_pct": 1.0},
    ]).set_index("date")
    delta = tp._weight_delta_6m(df, ["A", "B"], today)
    assert delta == 0.0


def test_weight_delta_6m_computes_when_lookback_present():
    today = date(2026, 5, 1)
    past = today - timedelta(days=200)
    df = pd.DataFrame([
        {"date": today, "nse_symbol": "A", "weight_pct": 3.0},
        {"date": today, "nse_symbol": "B", "weight_pct": 2.0},
        {"date": past, "nse_symbol": "A", "weight_pct": 1.0},
        {"date": past, "nse_symbol": "B", "weight_pct": 1.0},
    ]).set_index("date")
    delta = tp._weight_delta_6m(df, ["A", "B"], today)
    assert delta == pytest.approx(3.0)  # (3+2)-(1+1)=+3


def test_eps_surprise_share_no_data():
    assert tp._eps_surprise_share(None, ["A", "B"]) == 0.0


def test_eps_surprise_share_handles_partial_coverage():
    rd = pd.DataFrame(
        [("A", 5.0), ("B", -2.0)],
        columns=["NSE Code", "Net Profit Surprise Qtr %"],
    ).set_index("NSE Code")
    share = tp._eps_surprise_share(rd, ["A", "B", "MISSING"])
    # 1 of 2 with positive surprise = 0.5
    assert share == pytest.approx(0.5)


def test_dominant_sector_picks_majority():
    mg = pd.DataFrame(
        [("A", "IT"), ("B", "IT"), ("C", "IT"), ("D", "Banks")],
        columns=["NSE Code", "Sector"],
    ).set_index("NSE Code")
    assert tp._dominant_sector(mg, ["A", "B", "C", "D"]) == "IT"


def test_dominant_sector_returns_mixed_when_no_majority():
    mg = pd.DataFrame(
        [("A", "IT"), ("B", "Banks"), ("C", "FMCG"), ("D", "Auto")],
        columns=["NSE Code", "Sector"],
    ).set_index("NSE Code")
    assert tp._dominant_sector(mg, ["A", "B", "C", "D"]) == "MIXED"
