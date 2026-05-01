"""C2 — Market-cap drift.

Per-theme signal: rolling 6m delta in summed free-float weight (NIFTY-500) of
theme members.

Data source: TD-D1 (NIFTY-500 monthly weight files).
PIT cutoff: weight_file_date <= run_date - 7d.

STUB at v1: data acquisition is Task #77.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C2)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class CapDriftSignal(Signal):
    signal_id = "C2_cap_drift"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO(Task #77): load nifty_500_weights/<YYYY-MM>.parquet for
        # run_date - 6m and run_date - 7d, sum free_float_weight_pct over
        # theme members, return delta normalized to [0, 1] via theme-universe
        # percentile.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_unavailable: TD-D1 not yet acquired",
        )
