"""C6 — Sector breadth.

Per-theme signal: % of theme members trading above 200d MA over rolling 4w window
(weekly average of daily-snapshot share).

Data source: existing fno_historical/ daily bars.
PIT cutoff: bar_date <= run_date - 1d.

This signal CAN be wired immediately — fno_historical already exists. Stubbed
here only to keep the v1 ship-vs-data atomic; wire as part of Task #76 closeout
once data plumbing for the other Phase 1 signals is in.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C6)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class SectorBreadthSignal(Signal):
    signal_id = "C6_sector_breadth"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO: load fno_historical bars for each member, compute % > 200d MA
        # daily, average over last 4w (~20 trading days). The daily share IS
        # the [0, 1] score; weekly average smooths it.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_wiring_pending (fno_historical reachable)",
        )
