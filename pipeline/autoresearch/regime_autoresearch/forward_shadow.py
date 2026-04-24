"""Forward-shadow gate: 60d/50-event minimum + beats incumbent on same window."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.constants import (
    FORWARD_SHADOW_MIN_DAYS, FORWARD_SHADOW_MIN_EVENTS,
)


def ready_for_promotion(days_since_start: int, n_events: int,
                         forward_sharpe: float, incumbent_sharpe: float) -> bool:
    """True iff all three gates pass."""
    return (days_since_start >= FORWARD_SHADOW_MIN_DAYS
            and n_events >= FORWARD_SHADOW_MIN_EVENTS
            and forward_sharpe >= incumbent_sharpe)
