"""Tests for spread_intelligence.py — gate + modifier scoring logic."""

import sys
from pathlib import Path

# Ensure pipeline/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spread_intelligence import apply_gates, apply_modifiers, score_spread


# ── Gate tests ────────────────────────────────────────────────────────────


def test_gate_regime_inactive():
    result = apply_gates(
        "Defence vs IT", {"eligible_spreads": {}}, {}, 0.03, "STRESS"
    )
    assert result["status"] == "INACTIVE"


def test_gate_diverging():
    stats = {
        "Defence vs IT": {
            "regimes": {
                "STRESS": {
                    "mean": 0.02,
                    "std": 0.01,
                    "correlated_warning": False,
                }
            }
        }
    }
    result = apply_gates(
        "Defence vs IT",
        {"eligible_spreads": {"Defence vs IT": {}}},
        stats,
        0.035,
        "STRESS",
    )
    assert result["status"] == "ACTIVE"
    assert abs(result["z_score"] - 1.5) < 0.1


def test_gate_at_mean():
    stats = {
        "Defence vs IT": {
            "regimes": {
                "STRESS": {
                    "mean": 0.02,
                    "std": 0.01,
                    "correlated_warning": False,
                }
            }
        }
    }
    result = apply_gates(
        "Defence vs IT",
        {"eligible_spreads": {"Defence vs IT": {}}},
        stats,
        0.025,
        "STRESS",
    )
    assert result["status"] == "AT_MEAN"


def test_gate_correlated():
    stats = {
        "Defence vs IT": {
            "regimes": {
                "STRESS": {
                    "mean": 0.02,
                    "std": 0.01,
                    "correlated_warning": True,
                    "leg_correlation": 0.85,
                }
            }
        }
    }
    result = apply_gates(
        "Defence vs IT",
        {"eligible_spreads": {"Defence vs IT": {}}},
        stats,
        0.035,
        "STRESS",
    )
    assert result["status"] == "CORRELATED"


def test_gate_insufficient_data():
    """Missing regime key in stats should return INSUFFICIENT_DATA."""
    stats = {"Defence vs IT": {"regimes": {}}}
    result = apply_gates(
        "Defence vs IT",
        {"eligible_spreads": {"Defence vs IT": {}}},
        stats,
        0.03,
        "STRESS",
    )
    assert result["status"] == "INSUFFICIENT_DATA"


def test_gate_missing_spread_in_stats():
    """Spread not in spread_stats at all should return INSUFFICIENT_DATA."""
    result = apply_gates(
        "Defence vs IT",
        {"eligible_spreads": {"Defence vs IT": {}}},
        {},
        0.03,
        "STRESS",
    )
    assert result["status"] == "INSUFFICIENT_DATA"


# ── Modifier tests ───────────────────────────────────────────────────────


def test_modifier_max_boosts():
    score = apply_modifiers(
        50,
        {"short_rsi_avg": 28, "long_rsi_avg": 55, "trend_confirming": True},
        {"short_pcr_avg": 1.3, "long_pcr_avg": 0.4},
        {"direction": "BOOST"},
    )
    # 50 + 15 (rsi<30) + 15 (trend) + 15 (short_pcr>1.2) + 15 (long_pcr<0.5) + 15 (news) = 125 -> 100
    assert score >= 80


def test_modifier_max_cautions():
    score = apply_modifiers(
        50,
        {"short_rsi_avg": 55, "long_rsi_avg": 75, "trend_conflicting": True},
        {"short_pcr_avg": 0.4, "long_pcr_avg": 0.7},
        {"direction": "CAUTION"},
    )
    # 50 - 15 (long_rsi>70) - 15 (trend_conflicting) - 15 (short_pcr<0.5) - 15 (news) = -10 -> 0
    assert score < 50


def test_modifier_clamp_to_100():
    score = apply_modifiers(
        50,
        {"short_rsi_avg": 25, "long_rsi_avg": 50, "trend_confirming": True},
        {"short_pcr_avg": 1.5, "long_pcr_avg": 0.3},
        {"direction": "BOOST"},
    )
    assert score <= 100


def test_modifier_clamp_to_0():
    score = apply_modifiers(
        10,
        {"short_rsi_avg": 55, "long_rsi_avg": 80, "trend_conflicting": True},
        {"short_pcr_avg": 0.3, "long_pcr_avg": 0.8},
        {"direction": "CAUTION"},
    )
    assert score >= 0


# ── Score spread tests ────────────────────────────────────────────────────


def test_score_spread():
    assert score_spread(85) == ("HIGH", "ENTER")
    assert score_spread(80) == ("HIGH", "ENTER")
    assert score_spread(65) == ("MEDIUM", "WATCH")
    assert score_spread(50) == ("MEDIUM", "WATCH")
    assert score_spread(30) == ("LOW", "CAUTION")
    assert score_spread(0) == ("LOW", "CAUTION")
