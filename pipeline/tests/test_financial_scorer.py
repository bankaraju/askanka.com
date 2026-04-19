"""Tests for pipeline/scorecard_v2/financial_scorer.py"""
import pytest

from pipeline.scorecard_v2.financial_scorer import (
    _percentile_rank,
    _winsorize,
    score_sector,
)


# ---------------------------------------------------------------------------
# Test 1: percentile rank — higher is better
# ---------------------------------------------------------------------------

def test_percentile_higher_is_better():
    """Value 50 in [10, 20, 30, 40, 50] should rank at ~100 (highest)."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    rank = _percentile_rank(50.0, values)
    # 50 is the max — it should be close to 100 (90th percentile by mid-rank)
    assert rank >= 80.0, f"Expected rank near 100, got {rank}"
    # And it should be strictly higher than all other ranks
    for v in [10.0, 20.0, 30.0, 40.0]:
        assert rank > _percentile_rank(v, values)


# ---------------------------------------------------------------------------
# Test 2: percentile rank — lower is better (inverted)
# ---------------------------------------------------------------------------

def test_percentile_lower_is_better():
    """For a 'lower is better' KPI, the stock with the LOWEST value should get the
    highest inverted score (100 - percentile_rank).
    """
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    # Raw percentile of 10 (the best 'lower' candidate) should be low
    raw_rank_lowest = _percentile_rank(10.0, values)
    inverted = 100.0 - raw_rank_lowest
    # Inverted score of the minimum should be the highest
    raw_rank_highest = _percentile_rank(50.0, values)
    inverted_highest = 100.0 - raw_rank_highest
    assert inverted > inverted_highest, (
        f"Lowest value should score best when inverted. "
        f"Got inverted(10)={inverted}, inverted(50)={inverted_highest}"
    )


# ---------------------------------------------------------------------------
# Test 3: score_sector returns 0-100 and best stock scores highest
# ---------------------------------------------------------------------------

def test_score_sector_returns_0_100():
    """5 stocks, 4 KPIs. All scores 0-100, best stock scores highest."""
    kpis = [
        {"name": "ROE", "direction": "higher", "weight": 0.30},
        {"name": "ROCE", "direction": "higher", "weight": 0.25},
        {"name": "Revenue_Growth_3Y", "direction": "higher", "weight": 0.25},
        {"name": "Debt_to_Equity", "direction": "lower", "weight": 0.20},
    ]
    sector_metrics = {
        "BEST":  {"ROE": 30.0, "ROCE": 28.0, "Revenue_Growth_3Y": 25.0, "Debt_to_Equity": 0.1},
        "GOOD":  {"ROE": 22.0, "ROCE": 20.0, "Revenue_Growth_3Y": 18.0, "Debt_to_Equity": 0.4},
        "MID":   {"ROE": 15.0, "ROCE": 14.0, "Revenue_Growth_3Y": 12.0, "Debt_to_Equity": 0.8},
        "POOR":  {"ROE":  8.0, "ROCE":  7.0, "Revenue_Growth_3Y":  5.0, "Debt_to_Equity": 1.5},
        "WORST": {"ROE":  3.0, "ROCE":  2.0, "Revenue_Growth_3Y": -5.0, "Debt_to_Equity": 3.0},
    }
    scores = score_sector(sector_metrics, kpis)

    assert set(scores.keys()) == {"BEST", "GOOD", "MID", "POOR", "WORST"}

    for sym, score in scores.items():
        assert 0.0 <= score <= 100.0, f"{sym} score {score} out of [0, 100]"

    # Ranking must be monotone
    assert scores["BEST"] > scores["GOOD"] > scores["MID"] > scores["POOR"] > scores["WORST"], (
        f"Expected BEST > GOOD > MID > POOR > WORST, got {scores}"
    )


# ---------------------------------------------------------------------------
# Test 4: missing metric renormalizes weights
# ---------------------------------------------------------------------------

def test_missing_metric_renormalizes_weights():
    """If one KPI is missing from ALL stocks, ranking by remaining KPIs still works."""
    kpis = [
        {"name": "ROE", "direction": "higher", "weight": 0.50},
        {"name": "MISSING_KPI", "direction": "higher", "weight": 0.50},  # absent everywhere
    ]
    sector_metrics = {
        "HIGH_ROE": {"ROE": 25.0},   # MISSING_KPI absent
        "LOW_ROE":  {"ROE":  5.0},   # MISSING_KPI absent
    }
    scores = score_sector(sector_metrics, kpis)

    # Both should still get valid 0-100 scores
    for sym, score in scores.items():
        assert 0.0 <= score <= 100.0, f"{sym} score {score} out of [0, 100]"

    # Higher ROE should win despite missing KPI
    assert scores["HIGH_ROE"] > scores["LOW_ROE"], (
        f"HIGH_ROE should outscore LOW_ROE. Got {scores}"
    )


# ---------------------------------------------------------------------------
# Test 5: winsorize clips outliers
# ---------------------------------------------------------------------------

def test_winsorize_outliers():
    """Values [1,2,...,9,100]: the extreme outlier (100) should be clipped down."""
    values = list(range(1, 10)) + [100]  # [1,2,3,4,5,6,7,8,9,100]
    result = _winsorize(values)

    # The clipped maximum must be strictly less than 100
    assert max(result) < 100.0, f"Expected max < 100 after winsorize, got max={max(result)}"
    # The minimum should remain unchanged (or slightly shifted upward from 1)
    # but should not be clipped below the 5th-percentile value, which is close to 1
    assert min(result) >= 1.0, f"Expected min >= 1.0, got min={min(result)}"


# ---------------------------------------------------------------------------
# Test 6: single-stock sector gets score 50
# ---------------------------------------------------------------------------

def test_single_stock_sector_gets_50():
    """A sector with only 1 stock should receive the default score of 50.0."""
    kpis = [
        {"name": "ROE", "direction": "higher", "weight": 0.50},
        {"name": "ROCE", "direction": "higher", "weight": 0.50},
    ]
    sector_metrics = {
        "LONELY": {"ROE": 20.0, "ROCE": 18.0},
    }
    scores = score_sector(sector_metrics, kpis)

    assert "LONELY" in scores
    assert scores["LONELY"] == pytest.approx(50.0), (
        f"Single-stock sector should score 50.0, got {scores['LONELY']}"
    )
