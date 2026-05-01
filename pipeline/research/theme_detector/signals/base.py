"""Signal interface — every Belief / Confirmation signal implements this.

A signal returns a per-theme score in [0, 1] OR None when its data source is
unavailable. The aggregator (in detector.py) renormalizes weights within each
bucket over the available signals.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SignalResult:
    """Result of running one signal for one theme on one run date."""

    theme_id: str
    signal_id: str  # e.g. "B3_fii_drift", "C1_rs_breakout"
    score: float | None  # None when data unavailable
    notes: str | None = None  # optional diagnostic text


class Signal:
    """Base class for Belief / Confirmation signals.

    Subclasses set `signal_id` and implement `compute_for_theme`.
    """

    signal_id: str = ""
    bucket: str = ""  # "belief" or "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        """Compute this signal's score for a single theme.

        Args:
            theme: theme dict from themes_frozen.json (theme_id, rule_kind, members, ...)
            run_date: detector run date (PIT cutoff)

        Returns:
            SignalResult with score in [0, 1] or None.
        """
        raise NotImplementedError
