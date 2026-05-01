"""B3 — FII shareholding drift.

Per-theme signal: net FII flow polarity across theme members, derived from
Trendlyne FII increasing / decreasing screener snapshots.

v1 implementation (2026-05-01):
    score = (n_members_in_INCREASING - n_members_in_DECREASING) / n_members_total

The raw [-1, +1] balance is mapped to [0, 1] via (1 + balance) / 2 so that:
    - All members accumulating (BELIEF) -> 1.0
    - Half-and-half (mixed) -> 0.5
    - All members distributing (DECAY) -> 0.0
    - No matches in either screener -> 0.5 (neutral, not None — silence is data)

Returns None only when the screener files themselves are missing.

Data sources:
    - pipeline/data/trendlyne/raw_exports/fii_screener/fii_increasing_*.csv
    - pipeline/data/trendlyne/raw_exports/fii_screener/fii_decreasing_*.csv

PIT cutoff: snapshot_date <= run_date.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.1 (B3)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.data_loaders import load_fii_screener
from pipeline.research.theme_detector.signals.base import Signal, SignalResult


class FIIDriftSignal(Signal):
    signal_id = "B3_fii_drift"
    bucket = "belief"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        members = list(theme.get("rule_definition", {}).get("members", []))
        if not members:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="rule_kind_b_filter_predicate_unsupported_at_v1",
            )

        inc = load_fii_screener(run_date, "increasing")
        dec = load_fii_screener(run_date, "decreasing")
        if inc is None and dec is None:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: no FII screener snapshots present",
            )

        inc_set = set(inc.index) if inc is not None else set()
        dec_set = set(dec.index) if dec is not None else set()

        n_inc = sum(1 for m in members if m in inc_set)
        n_dec = sum(1 for m in members if m in dec_set)
        balance = (n_inc - n_dec) / len(members)
        score = (1.0 + balance) / 2.0
        score = max(0.0, min(1.0, score))

        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=score,
            notes=f"fii_inc={n_inc}/{len(members)} fii_dec={n_dec}/{len(members)}",
        )
