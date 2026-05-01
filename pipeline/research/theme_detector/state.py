"""ThemeState persistence layer.

Stores `ThemeState` objects across weekly runs as JSON. Long-format diff history
is appended to theme_history.parquet by the detector after each run.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §7
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.research.theme_detector.lifecycle import ThemeState


def load_state(state_path: Path) -> dict[str, ThemeState]:
    """Load ThemeState dict keyed by theme_id. Returns empty dict if file absent."""
    if not state_path.exists():
        return {}
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    return {tid: ThemeState(**s) for tid, s in raw.items()}


def save_state(state_path: Path, states: dict[str, ThemeState]) -> None:
    """Persist ThemeState dict to JSON."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    serial = {
        tid: {
            "theme_id": s.theme_id,
            "lifecycle_stage": s.lifecycle_stage,
            "lifecycle_stage_age_weeks": s.lifecycle_stage_age_weeks,
            "first_detected_date": s.first_detected_date,
            "first_pre_ignition_date": s.first_pre_ignition_date,
            "first_ignition_date": s.first_ignition_date,
            "confirmation_history": s.confirmation_history,
            "warnings": s.warnings,
        }
        for tid, s in states.items()
    }
    state_path.write_text(json.dumps(serial, indent=2), encoding="utf-8")
