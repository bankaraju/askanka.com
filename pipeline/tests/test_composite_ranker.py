"""Tests for pipeline/scorecard_v2/composite_ranker.py — Task 5."""
from __future__ import annotations

import pytest

from pipeline.scorecard_v2.composite_ranker import (
    compute_composite,
    compute_confidence,
    forced_rank_sector,
    generate_remark,
)

DEFAULT_WEIGHTS = {"financial": 0.70, "management": 0.30}


# ---------------------------------------------------------------------------
# 1. Weighted blend
# ---------------------------------------------------------------------------

def test_composite_weighted_blend():
    """80 financial, 60 management, 0.70/0.30 weights → 74.0."""
    result = compute_composite(80.0, 60.0, DEFAULT_WEIGHTS)
    assert result == pytest.approx(74.0)


# ---------------------------------------------------------------------------
# 2. Forced ranking assigns grades
# ---------------------------------------------------------------------------

def _make_20_stocks() -> dict[str, dict]:
    """20 stocks with linearly spaced financial scores (20 to 100) and mgmt=50."""
    stocks = {}
    for i in range(20):
        symbol = f"STOCK{i + 1:02d}"
        stocks[symbol] = {
            "financial_score": 20.0 + i * 4.0,  # 20, 24, 28, ... 96
            "management_score": 50.0,
            "sector": "TestSector",
        }
    return stocks


def test_forced_ranking_assigns_grades():
    """20 stocks: A and F must exist; rank 1 is the best (highest composite)."""
    stocks = _make_20_stocks()
    result = forced_rank_sector(stocks, DEFAULT_WEIGHTS)

    assert len(result) == 20

    grades = {v["sector_grade"] for v in result.values()}
    assert "A" in grades, "A grade must be present"
    assert "F" in grades, "F grade must be present"

    # rank 1 should have the highest composite
    rank1 = [sym for sym, v in result.items() if v["sector_rank"] == 1]
    rank20 = [sym for sym, v in result.items() if v["sector_rank"] == 20]
    assert len(rank1) == 1
    assert len(rank20) == 1

    assert result[rank1[0]]["composite_score"] > result[rank20[0]]["composite_score"]


# ---------------------------------------------------------------------------
# 3. Grade distribution — 20 stocks → A=3, F=3
# ---------------------------------------------------------------------------

def test_grade_distribution():
    """20 stocks: exactly 3 A grades and 3 F grades (15% each)."""
    stocks = _make_20_stocks()
    result = forced_rank_sector(stocks, DEFAULT_WEIGHTS)

    grade_counts: dict[str, int] = {}
    for v in result.values():
        g = v["sector_grade"]
        grade_counts[g] = grade_counts.get(g, 0) + 1

    assert grade_counts.get("A", 0) == 3, f"Expected 3 A grades, got {grade_counts}"
    assert grade_counts.get("F", 0) == 3, f"Expected 3 F grades, got {grade_counts}"


# ---------------------------------------------------------------------------
# 4. Remark generation
# ---------------------------------------------------------------------------

def test_remark_generation():
    """Remark must contain symbol, rank/total, leader, and confidence."""
    stock = {
        "symbol": "RELIANCE",
        "sector_rank": 2,
        "sector_total": 10,
        "sector": "Energy",
        "financial_score": 75,
        "management_score": 65,
        "sector_leader": "ONGC",
        "sector_leader_composite": 88.5,
        "confidence": "high",
    }
    remark = generate_remark(stock)

    assert "RELIANCE" in remark
    assert "2/10" in remark
    assert "Energy" in remark
    assert "ONGC" in remark
    assert "high" in remark

    # No red flag or strength → no dash suffix
    assert " — " not in remark


def test_remark_with_red_flag():
    """Red flag appended after management score."""
    stock = {
        "symbol": "VEDL",
        "sector_rank": 5,
        "sector_total": 10,
        "sector": "Metals",
        "financial_score": 60,
        "management_score": 30,
        "sector_leader": "HINDALCO",
        "sector_leader_composite": 80.0,
        "confidence": "medium",
        "biggest_red_flag": "persistent related-party loans",
    }
    remark = generate_remark(stock)
    assert "persistent related-party loans" in remark
    assert " — " in remark


def test_remark_strength_no_red_flag():
    """Strength appended only when no red flag present."""
    stock = {
        "symbol": "INFY",
        "sector_rank": 1,
        "sector_total": 8,
        "sector": "IT",
        "financial_score": 90,
        "management_score": 88,
        "sector_leader": "INFY",
        "sector_leader_composite": 89.4,
        "confidence": "high",
        "biggest_strength": "consistent capital return track record",
    }
    remark = generate_remark(stock)
    assert "consistent capital return track record" in remark


# ---------------------------------------------------------------------------
# 5. Sector leader and gap
# ---------------------------------------------------------------------------

def test_sector_leader_and_gap():
    """2-stock sector: leader gap is 0 for the best, > 0 for the worst."""
    stocks = {
        "ALPHA": {"financial_score": 90.0, "management_score": 80.0, "sector": "X"},
        "BETA":  {"financial_score": 50.0, "management_score": 40.0, "sector": "X"},
    }
    result = forced_rank_sector(stocks, DEFAULT_WEIGHTS)

    # ALPHA should be leader (higher composite)
    alpha_composite = compute_composite(90.0, 80.0, DEFAULT_WEIGHTS)
    beta_composite = compute_composite(50.0, 40.0, DEFAULT_WEIGHTS)

    assert result["ALPHA"]["sector_rank"] == 1
    assert result["ALPHA"]["sector_leader"] == "ALPHA"
    assert result["ALPHA"]["sector_gap_to_leader"] == pytest.approx(0.0)

    assert result["BETA"]["sector_rank"] == 2
    assert result["BETA"]["sector_leader"] == "ALPHA"
    expected_gap = alpha_composite - beta_composite
    assert result["BETA"]["sector_gap_to_leader"] == pytest.approx(expected_gap, abs=1e-3)
    assert result["BETA"]["sector_gap_to_leader"] > 0


# ---------------------------------------------------------------------------
# 6. Confidence from coverage
# ---------------------------------------------------------------------------

def test_confidence_from_coverage():
    """Verify confidence tiers: 90/3→high, 60/1→medium, 30/1→low."""
    assert compute_confidence(90.0, 3) == "high"
    assert compute_confidence(60.0, 1) == "medium"
    assert compute_confidence(30.0, 1) == "low"

    # Edge cases
    assert compute_confidence(80.0, 2) == "high"    # exactly at high threshold
    assert compute_confidence(80.0, 1) == "medium"  # coverage ok but only 1 source
    assert compute_confidence(50.0, 0) == "medium"  # exactly at medium threshold
    assert compute_confidence(49.9, 5) == "low"     # coverage too low even with sources
