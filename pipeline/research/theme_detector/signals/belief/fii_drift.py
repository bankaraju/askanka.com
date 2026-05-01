"""B3 — FII shareholding drift.

Per-theme signal: rolling 4-quarter delta in median FII holding % across theme
members.

Data source: TD-D7 (NSE quarterly shareholding pattern filings, FII column).
PIT cutoff: filing_date <= run_date - 1d.

STUB at v1: data acquisition is Task #77. Returns score=None until TD-D7 lands.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.1 (B3)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class FIIDriftSignal(Signal):
    signal_id = "B3_fii_drift"
    bucket = "belief"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO(Task #77): load fii_shareholding/<YYYY-Q>.parquet, compute
        # 4-quarter rolling delta in median FII pct across theme members,
        # normalize to [0, 1] via theme-relative percentile rank.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_unavailable: TD-D7 not yet acquired",
        )
