"""B5 — IPO cluster.

Per-theme signal: count of main-board IPOs in same Tier-1 sector / sub-sector
within rolling 6m window, normalized to [0, 1].

Data source: TD-D3 (NSE main-board IPO calendar).
PIT cutoff: listing_date <= run_date - 7d.

STUB at v1: data acquisition is Task #77.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.1 (B5)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class IPOClusterSignal(Signal):
    signal_id = "B5_ipo_cluster"
    bucket = "belief"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO(Task #77): load ipo_calendar.parquet, filter to listing_date in
        # [run_date - 6m, run_date - 7d] AND sub_sector matches theme. Score
        # by count: 0 IPOs → 0.0, 3+ IPOs → 1.0, scaled linearly.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_unavailable: TD-D3 not yet acquired",
        )
