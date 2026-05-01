"""C5 — Earnings breadth.

Per-theme signal: % of theme members posting QoQ EPS surprise > 0 over rolling
2-quarter window.

Data source: TD-D9 (Quarterly EPS surprise data, IndianAPI + Screener).
PIT cutoff: announcement_date <= run_date - 1d.

STUB at v1: existing earnings data path needs widening beyond Banks+IT (Task #77).

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C5)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class EarningsBreadthSignal(Signal):
    signal_id = "C5_earnings_breadth"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO(Task #77): load earnings_surprise/<YYYY-Q>.parquet, filter to
        # last 2 quarters where announcement_date <= run_date - 1d,
        # n_consensus_estimates >= 3 AND symbol in members. Compute share of
        # rows with eps_surprise_pct > 0; that share IS the [0, 1] score.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_unavailable: TD-D9 needs widening beyond Banks+IT seed",
        )
