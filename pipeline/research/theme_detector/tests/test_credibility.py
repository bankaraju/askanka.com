"""Credibility penalty tests — pure logic per spec §3.3."""
from __future__ import annotations

import pytest

from pipeline.research.theme_detector.credibility import (
    AGE_THRESHOLD_WEEKS,
    BELIEF_CONFIRMATION_SPREAD_THRESHOLD,
    compute_credibility_penalty,
    compute_current_strength,
)


# ============ Penalty zero conditions ============


def test_penalty_zero_when_age_below_threshold():
    """No penalty until 12w in PRE_IGNITION; first earnings season hasn't happened yet."""
    p = compute_credibility_penalty(belief_score=0.9, confirmation_score=0.1, age_weeks=8)
    assert p == 0.0


def test_penalty_zero_when_spread_within_tolerance():
    p = compute_credibility_penalty(
        belief_score=0.5,
        confirmation_score=0.3,
        age_weeks=AGE_THRESHOLD_WEEKS + 5,
    )
    assert p == 0.0


def test_penalty_zero_when_confirmation_dominates():
    p = compute_credibility_penalty(
        belief_score=0.2, confirmation_score=0.8, age_weeks=20
    )
    assert p == 0.0


# ============ Penalty positive conditions ============


def test_penalty_fires_when_belief_outpaces_confirmation():
    p = compute_credibility_penalty(
        belief_score=0.9,
        confirmation_score=0.2,
        age_weeks=AGE_THRESHOLD_WEEKS,
    )
    expected = 0.9 - 0.2 - BELIEF_CONFIRMATION_SPREAD_THRESHOLD
    assert p == pytest.approx(expected)


def test_penalty_clipped_at_one():
    p = compute_credibility_penalty(belief_score=1.0, confirmation_score=0.0, age_weeks=20)
    assert p <= 1.0


# ============ Current strength composition ============


def test_strength_dominant_confirmation_path():
    s = compute_current_strength(belief_score=0.0, confirmation_score=0.6, credibility_penalty=0.0)
    assert s == pytest.approx(0.42)  # 0.7 * 0.6


def test_strength_belief_uplifts_modestly():
    s_no = compute_current_strength(0.0, 0.5, 0.0)
    s_yes = compute_current_strength(0.5, 0.5, 0.0)
    assert s_yes > s_no
    assert (s_yes - s_no) == pytest.approx(0.15)  # 0.3 * 0.5


def test_strength_clipped_zero():
    s = compute_current_strength(belief_score=0.5, confirmation_score=0.5, credibility_penalty=0.9)
    assert s == 0.0


def test_strength_clipped_one():
    s = compute_current_strength(belief_score=1.0, confirmation_score=1.0, credibility_penalty=0.0)
    assert s == 1.0


def test_penalty_subtracts_at_full_weight_from_strength():
    """A high-belief / zero-confirmation theme aged > 12w should be heavily suppressed."""
    belief = 0.9
    conf = 0.1
    age = 20
    pen = compute_credibility_penalty(belief, conf, age)
    str_ = compute_current_strength(belief, conf, pen)
    raw_no_penalty = 0.7 * conf + 0.3 * belief
    assert str_ < raw_no_penalty
