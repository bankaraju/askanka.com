"""Theme credibility penalty per design spec §3.3.

Suppresses themes firing on belief without confirmation for >= 12 weeks.
Two earnings seasons should have produced confirmation; if they didn't, theme
is press-release noise.

Pure-logic module.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.3
"""
from __future__ import annotations

# FROZEN at v1 freeze — pending Bharat sign-off (Task #80)
BELIEF_CONFIRMATION_SPREAD_THRESHOLD = 0.4
AGE_THRESHOLD_WEEKS = 12


def compute_credibility_penalty(
    belief_score: float, confirmation_score: float, age_weeks: int
) -> float:
    """Compute credibility penalty per spec §3.3.

    Formula:
        if belief > confirmation + 0.4 AND age >= 12w:
            penalty = (belief - confirmation - 0.4) clipped to [0, 1]
        else:
            penalty = 0

    Penalty SUBTRACTS from current_strength and pushes theme toward
    FALSE_POSITIVE classification (handled in lifecycle.py via PRE_IGNITION
    timeout — credibility penalty is the strength-side suppression).
    """
    if age_weeks < AGE_THRESHOLD_WEEKS:
        return 0.0
    spread = belief_score - confirmation_score
    if spread <= BELIEF_CONFIRMATION_SPREAD_THRESHOLD:
        return 0.0
    penalty = spread - BELIEF_CONFIRMATION_SPREAD_THRESHOLD
    return max(0.0, min(1.0, penalty))


def compute_current_strength(
    belief_score: float, confirmation_score: float, credibility_penalty: float
) -> float:
    """Aggregate strength score downstream hypotheses use for ranking + sizing.

    Confirmation is the dominant input; belief uplifts at small weight (capped
    so a high-belief / zero-confirmation theme can't ride to a strong score
    purely on narrative).

    Credibility penalty subtracts at full weight.

    Returns clipped [0, 1].
    """
    raw = 0.7 * confirmation_score + 0.3 * belief_score - credibility_penalty
    return max(0.0, min(1.0, raw))
