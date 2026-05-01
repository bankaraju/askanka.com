"""C3 — F&O inclusion.

Per-theme signal: net F&O additions over a rolling 12-month window, scaled by
theme member count.

Score formula:
    raw = (n_theme_members_added_to_fo - n_theme_members_dropped_from_fo) / member_count
    score = clip(raw, 0, 1)

Drops contribute zero to the score rather than a negative — confirmation
DECREASING is captured at the lifecycle level (DECAY transition), not at the
signal level.

Data source: pipeline/data/fno_universe_history.json (existing — 27 monthly
snapshots from 2024-01-31 onward, sourced from NSE bhavcopy archives).
PIT cutoff: snapshot_date <= run_date - 1d.

Coverage handling:
- If fewer than 2 snapshots available within rolling window, returns None
  (insufficient_history).
- Symbol renames: applies the alias map from canonical_fno_research_v3 so
  GMRINFRA → GMRAIRPORT etc. don't show up as fake drop+add.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.4 (C3)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from pipeline.research.theme_detector.signals.base import Signal, SignalResult

REPO_ROOT = Path(__file__).resolve().parents[5]
FNO_HISTORY_PATH = REPO_ROOT / "pipeline" / "data" / "fno_universe_history.json"

ROLLING_WINDOW_DAYS = 365


class FOInclusionSignal(Signal):
    signal_id = "C3_fo_inclusion"
    bucket = "confirmation"

    def __init__(self, history_path: Path | None = None):
        self.history_path = history_path or FNO_HISTORY_PATH

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        members = _extract_members(theme)
        if not members:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="rule_kind_b_filter_predicate_unsupported_at_v1",
            )
        if not self.history_path.exists():
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: fno_universe_history.json missing",
            )

        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        snapshots = history.get("snapshots", [])
        cutoff = run_date - timedelta(days=1)
        window_start = run_date - timedelta(days=ROLLING_WINDOW_DAYS)

        in_window = [
            s for s in snapshots
            if window_start <= datetime.fromisoformat(s["date"]).date() <= cutoff
        ]
        in_window.sort(key=lambda s: s["date"])
        if len(in_window) < 2:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes=(
                    f"insufficient_history: only {len(in_window)} snapshots "
                    f"in 12m window ending {cutoff}"
                ),
            )

        first = set(in_window[0]["symbols"])
        last = set(in_window[-1]["symbols"])
        member_set = set(members)

        added_members = (last - first) & member_set
        dropped_members = (first - last) & member_set

        raw = (len(added_members) - len(dropped_members)) / len(members)
        score = max(0.0, min(1.0, raw))

        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=score,
            notes=(
                f"window={in_window[0]['date']}..{in_window[-1]['date']} "
                f"added={sorted(added_members)} dropped={sorted(dropped_members)}"
            ),
        )


def _extract_members(theme: dict) -> list[str]:
    rule = theme.get("rule_definition", {})
    return list(rule.get("members", []))
