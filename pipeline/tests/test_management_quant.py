"""
Tests for pipeline/scorecard_v2/management_quant.py

7 tests covering pledge scoring, stability comparisons, hard caps, and range.
"""

import pytest
from pipeline.scorecard_v2.management_quant import (
    _pledge_score,
    _roe_stability_score,
    _margin_stability_score,
    _cfo_pat_consistency_score,
    _skin_in_game_score,
    compute_management_quant,
)


# ---------------------------------------------------------------------------
# Test 1 — pledge scoring buckets
# ---------------------------------------------------------------------------

def test_pledge_scoring():
    assert _pledge_score(0) == 5,   "0% pledge → best score 5"
    assert _pledge_score(5) == 4,   "5% pledge → score 4"
    assert _pledge_score(20) == 3,  "20% pledge → score 3"
    assert _pledge_score(40) == 2,  "40% pledge → score 2"
    assert _pledge_score(60) == 1,  "60% pledge → worst score 1"


# ---------------------------------------------------------------------------
# Test 2 — ROE stability: stable > volatile
# ---------------------------------------------------------------------------

def test_roe_stability_higher_is_better():
    stable_roe = [18.0, 19.0, 20.0, 19.5, 18.5]   # mean~19, std~0.6
    volatile_roe = [5.0, 25.0, 2.0, 30.0, 8.0]    # same rough mean, high std

    stable_score = _roe_stability_score(stable_roe)
    volatile_score = _roe_stability_score(volatile_roe)

    assert stable_score > volatile_score, (
        f"Stable ROE should score higher: {stable_score:.2f} vs {volatile_score:.2f}"
    )
    assert 0 <= stable_score <= 20
    assert 0 <= volatile_score <= 20


# ---------------------------------------------------------------------------
# Test 3 — margin stability: stable > volatile
# ---------------------------------------------------------------------------

def test_margin_volatility_lower_is_better():
    stable_margins = [18.0, 18.5, 19.0, 18.2, 18.8]   # std ~ 0.3
    volatile_margins = [10.0, 25.0, 8.0, 30.0, 12.0]  # std ~ 8.5

    stable_score = _margin_stability_score(stable_margins)
    volatile_score = _margin_stability_score(volatile_margins)

    assert stable_score > volatile_score, (
        f"Stable margins should score higher: {stable_score:.2f} vs {volatile_score:.2f}"
    )
    assert stable_score == 20.0, "std < 2 should return max score 20"
    assert 2.0 <= volatile_score < 20.0


# ---------------------------------------------------------------------------
# Test 4 — CFO/PAT consistency: high ratio > low ratio
# ---------------------------------------------------------------------------

def test_cfo_pat_consistency():
    good_cfo_pat = [1.1, 1.2, 0.9, 1.0, 1.3]   # all positive, avg ~ 1.1
    bad_cfo_pat = [0.2, -0.1, 0.1, -0.3, 0.2]   # near zero + negatives

    good_score = _cfo_pat_consistency_score(good_cfo_pat)
    bad_score = _cfo_pat_consistency_score(bad_cfo_pat)

    assert good_score > bad_score, (
        f"Good CFO/PAT should score higher: {good_score:.2f} vs {bad_score:.2f}"
    )
    assert 0 <= bad_score <= 20
    assert 0 <= good_score <= 20


# ---------------------------------------------------------------------------
# Test 5 — hard cap: pledge > 30% → score capped at 40
# ---------------------------------------------------------------------------

def test_hard_cap_pledge():
    metrics_high_pledge = {
        "ROE_history": [22.0, 23.0, 21.0, 22.5, 21.5],  # excellent ROE
        "Margin_history": [20.0, 20.5, 19.5, 20.0, 20.2],  # very stable
        "CFO_PAT": 1.2,
        "promoter_pledge_pct": 45.0,   # > 30% → hard cap
        "promoter_holding_pct": 65.0,
    }
    score = compute_management_quant(metrics_high_pledge)
    assert score <= 40.0, f"Score {score} should be capped at 40 when pledge > 30%"


# ---------------------------------------------------------------------------
# Test 6 — hard cap: CFO/PAT average < 0.3 → score capped at 50
# ---------------------------------------------------------------------------

def test_hard_cap_cfo_pat():
    metrics_low_cfo = {
        "ROE_history": [22.0, 23.0, 21.0],
        "Margin_history": [20.0, 20.5, 19.5],
        "CFO_PAT": 0.2,              # < 0.3 → hard cap at 50
        "promoter_pledge_pct": 0.0,  # no pledge penalty
        "promoter_holding_pct": 75.0,
    }
    score = compute_management_quant(metrics_low_cfo)
    assert score <= 50.0, f"Score {score} should be capped at 50 when CFO/PAT avg < 0.3"


# ---------------------------------------------------------------------------
# Test 7 — full score range: good inputs > bad inputs, both in [0, 100]
# ---------------------------------------------------------------------------

def test_full_score_range():
    good_metrics = {
        "ROE_history": [21.0, 22.0, 20.5, 21.5, 22.5],
        "Margin_history": [19.0, 19.5, 18.5, 19.2, 19.8],
        "CFO_PAT": 1.1,
        "promoter_pledge_pct": 0.0,
        "promoter_holding_pct": 72.0,
    }
    bad_metrics = {
        "ROE_history": [3.0, -2.0, 8.0, -5.0, 1.0],
        "Margin_history": [5.0, 20.0, 2.0, 25.0, 3.0],
        "CFO_PAT": 0.1,
        "promoter_pledge_pct": 55.0,
        "promoter_holding_pct": 5.0,
    }

    good_score = compute_management_quant(good_metrics)
    bad_score = compute_management_quant(bad_metrics)

    assert 0 <= bad_score <= 100,  f"Bad score {bad_score} out of range"
    assert 0 <= good_score <= 100, f"Good score {good_score} out of range"
    assert good_score > bad_score, (
        f"Good metrics should outscore bad: {good_score:.2f} vs {bad_score:.2f}"
    )
