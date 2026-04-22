"""
Tests for apply_trust_modifier — Task B8.

Trust grade is ONLY a conditional modifier in NEUTRAL regime.
  A, B  → +0 (fundamental signal already priced in)
  C     → 0
  D, F  → -5 on LONG, +5 on SHORT
  Non-NEUTRAL regime → 0 regardless of grade
  INSUFFICIENT_DATA  → 0
"""
from __future__ import annotations

import pytest
from pipeline.signal_enrichment import apply_trust_modifier

# ---------------------------------------------------------------------------
# Single-ticker tests
# ---------------------------------------------------------------------------


def test_trust_modifier_neutral_d_long_penalty():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "D"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == -5
    assert out["entry_score"] == 55


def test_trust_modifier_neutral_f_long_penalty():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 70, "trust_grade": "F"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == -5
    assert out["entry_score"] == 65


def test_trust_modifier_neutral_d_short_bonus():
    sig = {"ticker": "X", "direction": "SHORT", "entry_score": 60, "trust_grade": "D"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 5
    assert out["entry_score"] == 65


def test_trust_modifier_neutral_f_short_bonus():
    sig = {"ticker": "X", "direction": "SHORT", "entry_score": 55, "trust_grade": "F"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 5
    assert out["entry_score"] == 60


def test_trust_modifier_neutral_a_no_change():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "A"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_neutral_b_no_change():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "B"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_neutral_c_no_change():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "C"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_risk_off_is_zero():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "D"}
    regime = {"zone": "RISK-OFF"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_risk_on_is_zero():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "F"}
    regime = {"zone": "RISK-ON"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_missing_grade_is_zero():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "INSUFFICIENT_DATA"}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_no_grade_field_is_zero():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60}
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 60


def test_trust_modifier_none_regime_is_zero():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "D"}
    regime = {}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0


def test_trust_modifier_does_not_mutate_input():
    sig = {"ticker": "X", "direction": "LONG", "entry_score": 60, "trust_grade": "D"}
    regime = {"zone": "NEUTRAL"}
    apply_trust_modifier(sig, regime)
    assert sig["entry_score"] == 60  # original unchanged


# ---------------------------------------------------------------------------
# Spread signal tests
# ---------------------------------------------------------------------------


def test_trust_modifier_spread_aggregates_per_leg():
    """
    Long leg D + Short leg F → -5 + 5 = 0 net (D penalizes long, F rewards short).
    """
    sig = {
        "long_legs": [{"ticker": "BADCO", "trust_grade": "D"}],
        "short_legs": [{"ticker": "BADCO2", "trust_grade": "F"}],
        "entry_score": 65,
    }
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 65


def test_trust_modifier_spread_d_long_and_a_short():
    """
    Long leg D → -5. Short leg A → 0 (A/B no change regardless of direction).
    Net: -5, capped at ±10.
    """
    sig = {
        "long_legs": [{"ticker": "BADCO", "trust_grade": "D"}],
        "short_legs": [{"ticker": "GOODCO", "trust_grade": "A"}],
        "entry_score": 70,
    }
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == -5
    assert out["entry_score"] == 65
    assert "trust_contributing_legs" in out


def test_trust_modifier_spread_two_d_longs_capped():
    """
    Two D long legs → -5 + -5 = -10, capped at -10.
    """
    sig = {
        "long_legs": [
            {"ticker": "BAD1", "trust_grade": "D"},
            {"ticker": "BAD2", "trust_grade": "D"},
            {"ticker": "BAD3", "trust_grade": "D"},  # would be -15, cap at -10
        ],
        "short_legs": [],
        "entry_score": 80,
    }
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == -10
    assert out["entry_score"] == 70


def test_trust_modifier_spread_risk_off_all_zero():
    sig = {
        "long_legs": [{"ticker": "BAD1", "trust_grade": "D"}],
        "short_legs": [{"ticker": "BAD2", "trust_grade": "F"}],
        "entry_score": 65,
    }
    regime = {"zone": "RISK-OFF"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 0
    assert out["entry_score"] == 65


def test_trust_modifier_spread_f_short_good_long():
    """
    Long leg B → 0. Short leg F → +5.
    Net: +5.
    """
    sig = {
        "long_legs": [{"ticker": "GOODCO", "trust_grade": "B"}],
        "short_legs": [{"ticker": "BADCO", "trust_grade": "F"}],
        "entry_score": 60,
    }
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    assert out["trust_modifier"] == 5
    assert out["entry_score"] == 65


def test_trust_modifier_trust_context_populated_for_contributing_legs():
    sig = {
        "long_legs": [{"ticker": "BADCO", "trust_grade": "D"}],
        "short_legs": [],
        "entry_score": 60,
    }
    regime = {"zone": "NEUTRAL"}
    out = apply_trust_modifier(sig, regime)
    legs = out.get("trust_contributing_legs", [])
    assert len(legs) == 1
    assert legs[0]["ticker"] == "BADCO"
    assert legs[0]["direction"] == "LONG"
    assert legs[0]["delta"] == -5
