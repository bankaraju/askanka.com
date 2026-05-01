"""C3 — F&O inclusion.

Per-theme signal: theme-level F&O inclusion score over rolling 12m =
(F&O_added - F&O_dropped) / theme_member_count.

Data source: TD-D8 (NSE F&O eligibility list history).
PIT cutoff: event_date <= run_date - 1d.

STUB at v1: data acquisition is Task #77.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.4 (C3)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class FOInclusionSignal(Signal):
    signal_id = "C3_fo_inclusion"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO(Task #77): load fno_eligibility_history.parquet, filter to
        # event_date in [run_date - 12m, run_date - 1d] AND symbol in members,
        # compute (added - dropped) / member_count, scale to [0, 1] via
        # theme-universe percentile.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_unavailable: TD-D8 not yet acquired",
        )
