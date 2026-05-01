"""5-state lifecycle classifier per design spec §5.

States: DORMANT, PRE_IGNITION, IGNITION, MATURE, DECAY, FALSE_POSITIVE.

Pure-logic module. No I/O, no data dependencies. Tested via tests/test_lifecycle.py.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §5
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Stage = Literal["DORMANT", "PRE_IGNITION", "IGNITION", "MATURE", "DECAY", "FALSE_POSITIVE"]

# FROZEN at v1 freeze — pending Bharat sign-off (Task #80)
BELIEF_PRE_IGNITION_THRESHOLD = 0.4
CONFIRMATION_IGNITION_THRESHOLD = 0.5
CONFIRMATION_DECAY_THRESHOLD = 0.3
CONFIRMATION_DORMANT_THRESHOLD = 0.2
BELIEF_DORMANT_THRESHOLD = 0.2

PRE_IGNITION_TIMEOUT_WEEKS = 26       # → FALSE_POSITIVE if no IGNITION
IGNITION_TO_MATURE_WEEKS = 12
DECAY_TO_DORMANT_WEEKS = 8
FALSE_POSITIVE_TO_DORMANT_WEEKS = 8
DECAY_TREND_WINDOW_WEEKS = 4


@dataclass
class ThemeState:
    """Carries lifecycle history for a single theme across runs."""

    theme_id: str
    lifecycle_stage: Stage = "DORMANT"
    lifecycle_stage_age_weeks: int = 0
    first_detected_date: str | None = None
    first_pre_ignition_date: str | None = None
    first_ignition_date: str | None = None
    confirmation_history: list[float] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def classify_transition(
    state: ThemeState,
    belief_score: float,
    confirmation_score: float,
    run_date: str,
) -> ThemeState:
    """Apply transition rules from spec §5 to produce next-week state.

    `confirmation_history` is appended every call; the trend check for DECAY uses
    the last 4 entries.

    Returns a NEW ThemeState (immutable input pattern).
    """
    next_state = ThemeState(
        theme_id=state.theme_id,
        lifecycle_stage=state.lifecycle_stage,
        lifecycle_stage_age_weeks=state.lifecycle_stage_age_weeks + 1,
        first_detected_date=state.first_detected_date,
        first_pre_ignition_date=state.first_pre_ignition_date,
        first_ignition_date=state.first_ignition_date,
        confirmation_history=state.confirmation_history + [confirmation_score],
        warnings=[],
    )
    if next_state.first_detected_date is None and (
        belief_score >= BELIEF_PRE_IGNITION_THRESHOLD
        or confirmation_score >= CONFIRMATION_IGNITION_THRESHOLD
    ):
        next_state.first_detected_date = run_date

    current = state.lifecycle_stage

    if current == "DORMANT":
        if confirmation_score >= CONFIRMATION_IGNITION_THRESHOLD:
            next_state.lifecycle_stage = "IGNITION"
            next_state.lifecycle_stage_age_weeks = 0
            next_state.first_ignition_date = run_date
            next_state.warnings.append("fast_ignition_skipped_pre_ignition")
        elif belief_score >= BELIEF_PRE_IGNITION_THRESHOLD:
            next_state.lifecycle_stage = "PRE_IGNITION"
            next_state.lifecycle_stage_age_weeks = 0
            next_state.first_pre_ignition_date = run_date

    elif current == "PRE_IGNITION":
        if confirmation_score >= CONFIRMATION_IGNITION_THRESHOLD:
            next_state.lifecycle_stage = "IGNITION"
            next_state.lifecycle_stage_age_weeks = 0
            next_state.first_ignition_date = run_date
        elif state.lifecycle_stage_age_weeks + 1 >= PRE_IGNITION_TIMEOUT_WEEKS:
            next_state.lifecycle_stage = "FALSE_POSITIVE"
            next_state.lifecycle_stage_age_weeks = 0

    elif current == "IGNITION":
        if state.lifecycle_stage_age_weeks + 1 >= IGNITION_TO_MATURE_WEEKS:
            next_state.lifecycle_stage = "MATURE"
            next_state.lifecycle_stage_age_weeks = 0
        elif confirmation_score < CONFIRMATION_DECAY_THRESHOLD and _trend_negative(
            next_state.confirmation_history
        ):
            next_state.lifecycle_stage = "DECAY"
            next_state.lifecycle_stage_age_weeks = 0

    elif current == "MATURE":
        if confirmation_score < CONFIRMATION_DECAY_THRESHOLD and _trend_negative(
            next_state.confirmation_history
        ):
            next_state.lifecycle_stage = "DECAY"
            next_state.lifecycle_stage_age_weeks = 0

    elif current == "DECAY":
        if _consecutive_below(
            next_state.confirmation_history,
            CONFIRMATION_DORMANT_THRESHOLD,
            DECAY_TO_DORMANT_WEEKS,
        ):
            next_state.lifecycle_stage = "DORMANT"
            next_state.lifecycle_stage_age_weeks = 0

    elif current == "FALSE_POSITIVE":
        if _belief_below_consecutive(
            state, belief_score, BELIEF_DORMANT_THRESHOLD, FALSE_POSITIVE_TO_DORMANT_WEEKS
        ):
            next_state.lifecycle_stage = "DORMANT"
            next_state.lifecycle_stage_age_weeks = 0
            next_state.first_pre_ignition_date = None  # allow re-entry fresh

    return next_state


def is_downstream_entry_permitted(stage: Stage) -> bool:
    """Per spec §6: FALSE_POSITIVE and DECAY block new entries.

    Downstream hypothesis may override scope rule, but FALSE_POSITIVE is NEVER
    eligible regardless of override (§9.1).
    """
    if stage == "FALSE_POSITIVE":
        return False
    if stage == "DECAY":
        return False
    return True


def _trend_negative(history: list[float]) -> bool:
    """4-week trend negative: last 4 confirmation scores monotonically non-increasing
    OR last value < first value of the window.
    """
    if len(history) < DECAY_TREND_WINDOW_WEEKS:
        return False
    window = history[-DECAY_TREND_WINDOW_WEEKS:]
    return window[-1] < window[0]


def _consecutive_below(history: list[float], threshold: float, n: int) -> bool:
    if len(history) < n:
        return False
    return all(v < threshold for v in history[-n:])


def _belief_below_consecutive(
    state: ThemeState, current_belief: float, threshold: float, n: int
) -> bool:
    """FALSE_POSITIVE → DORMANT requires sustained low belief; we don't keep a
    belief history vector at v1 — use age-in-state as a proxy.

    Per spec §5: 'belief_score < 0.2 for 8 consecutive weeks'. Until the detector
    accumulates a belief vector, fall back to: age in FALSE_POSITIVE >= n weeks
    AND current belief below threshold.
    """
    return state.lifecycle_stage_age_weeks + 1 >= n and current_belief < threshold
