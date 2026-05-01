"""C1 — Relative strength breakout.

Per-theme signal: 200d RS-vs-NIFTY-50 + 90d slope on theme's matched sectoral
index OR theme-member equal-weighted basket if no matching sectoral index.

Data source: TD-D2 (sectoral indices daily history; existing Kite +
fno_historical).
PIT cutoff: close <= run_date - 1d.

STUB at v1: data wiring is Task #76 follow-up; sectoral index data exists.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C1)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class RSBreakoutSignal(Signal):
    signal_id = "C1_rs_breakout"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        # TODO: load TD-D2 sectoral index (or compute equal-weight basket of
        # members from fno_historical), compute RS = theme_close /
        # nifty_50_close, then 200d RS percentile rank + 90d slope sign.
        # Score = combined into [0, 1] via percentile.
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=None,
            notes="data_wiring_pending",
        )
