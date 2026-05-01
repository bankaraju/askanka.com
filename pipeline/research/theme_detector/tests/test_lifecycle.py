"""Lifecycle classifier tests — pure logic, no I/O."""
from __future__ import annotations

import pytest

from pipeline.research.theme_detector.lifecycle import (
    DECAY_TO_DORMANT_WEEKS,
    IGNITION_TO_MATURE_WEEKS,
    PRE_IGNITION_TIMEOUT_WEEKS,
    ThemeState,
    classify_transition,
    is_downstream_entry_permitted,
)


def _new(theme_id: str = "T") -> ThemeState:
    return ThemeState(theme_id=theme_id)


# ============ DORMANT transitions ============


def test_dormant_stays_dormant_when_signals_quiet():
    s = _new()
    out = classify_transition(s, belief_score=0.1, confirmation_score=0.1, run_date="2026-05-04")
    assert out.lifecycle_stage == "DORMANT"
    assert out.lifecycle_stage_age_weeks == 1


def test_dormant_to_pre_ignition_on_belief_threshold():
    s = _new()
    out = classify_transition(s, belief_score=0.5, confirmation_score=0.1, run_date="2026-05-04")
    assert out.lifecycle_stage == "PRE_IGNITION"
    assert out.lifecycle_stage_age_weeks == 0
    assert out.first_pre_ignition_date == "2026-05-04"
    assert out.first_detected_date == "2026-05-04"


def test_dormant_to_ignition_skip_logs_warning():
    """Fast-ignition (regulatory event) skipping PRE_IGNITION is legitimate but flagged."""
    s = _new()
    out = classify_transition(s, belief_score=0.1, confirmation_score=0.7, run_date="2026-05-04")
    assert out.lifecycle_stage == "IGNITION"
    assert out.first_ignition_date == "2026-05-04"
    assert "fast_ignition_skipped_pre_ignition" in out.warnings


# ============ PRE_IGNITION transitions ============


def test_pre_ignition_to_ignition_on_confirmation_break():
    s = ThemeState(theme_id="T", lifecycle_stage="PRE_IGNITION", lifecycle_stage_age_weeks=10)
    out = classify_transition(s, belief_score=0.5, confirmation_score=0.6, run_date="2026-05-04")
    assert out.lifecycle_stage == "IGNITION"
    assert out.lifecycle_stage_age_weeks == 0
    assert out.first_ignition_date == "2026-05-04"


def test_pre_ignition_holds_until_timeout():
    s = ThemeState(theme_id="T", lifecycle_stage="PRE_IGNITION", lifecycle_stage_age_weeks=10)
    out = classify_transition(s, belief_score=0.5, confirmation_score=0.2, run_date="2026-05-04")
    assert out.lifecycle_stage == "PRE_IGNITION"
    assert out.lifecycle_stage_age_weeks == 11


def test_pre_ignition_to_false_positive_at_26w():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="PRE_IGNITION",
        lifecycle_stage_age_weeks=PRE_IGNITION_TIMEOUT_WEEKS - 1,
    )
    out = classify_transition(s, belief_score=0.5, confirmation_score=0.2, run_date="2026-11-01")
    assert out.lifecycle_stage == "FALSE_POSITIVE"
    assert out.lifecycle_stage_age_weeks == 0


# ============ IGNITION transitions ============


def test_ignition_to_mature_at_12w():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="IGNITION",
        lifecycle_stage_age_weeks=IGNITION_TO_MATURE_WEEKS - 1,
    )
    out = classify_transition(s, belief_score=0.4, confirmation_score=0.6, run_date="2026-08-01")
    assert out.lifecycle_stage == "MATURE"
    assert out.lifecycle_stage_age_weeks == 0


def test_ignition_to_decay_on_confirmation_collapse():
    """Confirmation drops below 0.3 with negative 4-week trend in IGNITION → DECAY."""
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="IGNITION",
        lifecycle_stage_age_weeks=4,
        confirmation_history=[0.7, 0.6, 0.5, 0.4],
    )
    out = classify_transition(s, belief_score=0.3, confirmation_score=0.2, run_date="2026-06-01")
    assert out.lifecycle_stage == "DECAY"


# ============ MATURE transitions ============


def test_mature_to_decay_on_confirmation_drop():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="MATURE",
        lifecycle_stage_age_weeks=20,
        confirmation_history=[0.6, 0.55, 0.45, 0.35],
    )
    out = classify_transition(s, belief_score=0.3, confirmation_score=0.25, run_date="2027-01-01")
    assert out.lifecycle_stage == "DECAY"


def test_mature_holds_when_confirmation_intact():
    s = ThemeState(theme_id="T", lifecycle_stage="MATURE", lifecycle_stage_age_weeks=20)
    out = classify_transition(s, belief_score=0.4, confirmation_score=0.6, run_date="2027-01-01")
    assert out.lifecycle_stage == "MATURE"
    assert out.lifecycle_stage_age_weeks == 21


# ============ DECAY transitions ============


def test_decay_to_dormant_after_8w_below_threshold():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="DECAY",
        lifecycle_stage_age_weeks=DECAY_TO_DORMANT_WEEKS - 1,
        confirmation_history=[0.1] * (DECAY_TO_DORMANT_WEEKS - 1),
    )
    out = classify_transition(s, belief_score=0.1, confirmation_score=0.1, run_date="2027-04-01")
    assert out.lifecycle_stage == "DORMANT"
    assert out.lifecycle_stage_age_weeks == 0


def test_decay_holds_if_confirmation_recovers_above_dormant_threshold():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="DECAY",
        lifecycle_stage_age_weeks=4,
        confirmation_history=[0.25, 0.22, 0.21, 0.20],
    )
    out = classify_transition(s, belief_score=0.2, confirmation_score=0.25, run_date="2027-04-01")
    assert out.lifecycle_stage == "DECAY"


# ============ FALSE_POSITIVE transitions ============


def test_false_positive_to_dormant_after_8w_low_belief():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="FALSE_POSITIVE",
        lifecycle_stage_age_weeks=7,
        first_pre_ignition_date="2026-01-01",
    )
    out = classify_transition(s, belief_score=0.1, confirmation_score=0.0, run_date="2026-12-01")
    assert out.lifecycle_stage == "DORMANT"
    assert out.first_pre_ignition_date is None  # cleared so re-entry can happen fresh


def test_false_positive_stays_if_belief_persists():
    s = ThemeState(
        theme_id="T",
        lifecycle_stage="FALSE_POSITIVE",
        lifecycle_stage_age_weeks=4,
    )
    out = classify_transition(s, belief_score=0.5, confirmation_score=0.0, run_date="2026-12-01")
    assert out.lifecycle_stage == "FALSE_POSITIVE"
    assert out.lifecycle_stage_age_weeks == 5


# ============ Downstream entry gate ============


def test_downstream_entry_blocked_for_false_positive():
    assert not is_downstream_entry_permitted("FALSE_POSITIVE")


def test_downstream_entry_blocked_for_decay():
    assert not is_downstream_entry_permitted("DECAY")


@pytest.mark.parametrize("stage", ["DORMANT", "PRE_IGNITION", "IGNITION", "MATURE"])
def test_downstream_entry_permitted_for_other_stages(stage):
    assert is_downstream_entry_permitted(stage)
