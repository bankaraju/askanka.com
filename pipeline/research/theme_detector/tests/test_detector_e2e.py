"""End-to-end orchestrator test against stub signals + frozen.json.

Verifies the detector runs without error, emits valid output schema, persists
state, and that stage_counts sum equals n_themes_total.

When all signals return None (stub mode), all themes should land in DORMANT.
Stub mode is achieved here by monkeypatching the signal rosters with always-None
implementations — this keeps the test hermetic regardless of whether real
signal modules can read live data on the host running the test.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.research.theme_detector import detector as detector_mod
from pipeline.research.theme_detector.detector import (
    BELIEF_SIGNALS,
    BELIEF_WEIGHTS,
    CONFIRMATION_SIGNALS,
    CONFIRMATION_WEIGHTS,
    aggregate_bucket,
    run_detector,
)
from pipeline.research.theme_detector.lifecycle import ThemeState
from pipeline.research.theme_detector.signals.base import Signal, SignalResult
from pipeline.research.theme_detector.state import load_state, save_state


class _NullSignal(Signal):
    """Test-only signal that always returns None — used to force stub mode."""

    def __init__(self, signal_id: str, bucket: str):
        self.signal_id = signal_id
        self.bucket = bucket

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        return SignalResult(theme["theme_id"], self.signal_id, None, "stub_mode")


@pytest.fixture
def frozen_themes() -> list[dict]:
    p = Path(__file__).parent.parent / "themes_frozen.json"
    return json.loads(p.read_text(encoding="utf-8"))["themes"]


@pytest.fixture
def stub_signals(monkeypatch):
    """Replace the live signal rosters with always-None stubs.

    Preserves the per-signal IDs so output_signal_breakdown still shows the
    expected ID set; only the score becomes None universally.
    """
    belief_stubs = [_NullSignal(s.signal_id, "belief") for s in BELIEF_SIGNALS]
    conf_stubs = [_NullSignal(s.signal_id, "confirmation") for s in CONFIRMATION_SIGNALS]
    monkeypatch.setattr(detector_mod, "BELIEF_SIGNALS", belief_stubs)
    monkeypatch.setattr(detector_mod, "CONFIRMATION_SIGNALS", conf_stubs)
    return belief_stubs, conf_stubs


def test_detector_runs_against_frozen_universe_in_stub_mode(frozen_themes, stub_signals):
    """Stub mode: every signal returns None. All themes must land in DORMANT."""
    result = run_detector(date(2026, 5, 4), frozen_themes, states={})
    out = result["output"]

    assert out["n_themes_total"] == len(frozen_themes)
    assert sum(out["stage_counts"].values()) == out["n_themes_total"]
    assert out["stage_counts"]["DORMANT"] == out["n_themes_total"]
    assert all(t["belief_score"] == 0 for t in out["themes"])
    assert all(t["confirmation_score"] == 0 for t in out["themes"])
    assert all(t["credibility_penalty"] == 0 for t in out["themes"])
    assert all(t["downstream_entry_permitted"] for t in out["themes"])


def test_detector_carries_state_across_runs(frozen_themes, stub_signals, tmp_path):
    state_path = tmp_path / "states.json"

    result1 = run_detector(date(2026, 5, 4), frozen_themes, states={})
    save_state(state_path, result1["next_states"])

    states = load_state(state_path)
    assert len(states) == len(frozen_themes)

    result2 = run_detector(date(2026, 5, 11), frozen_themes, states=states)
    out = result2["output"]

    # Every theme should have aged 1 week (still DORMANT in stub mode but age++)
    for t in out["themes"]:
        assert t["lifecycle_stage_age_weeks"] >= 2


def test_aggregate_bucket_handles_all_none():
    results = [SignalResult("T", "B3_fii_drift", None), SignalResult("T", "B5_ipo_cluster", None)]
    assert aggregate_bucket(results, BELIEF_WEIGHTS) == 0.0


def test_aggregate_bucket_renormalizes_over_available():
    """B3 returns 0.6 with weight 0.20, B5 returns None. Output should be 0.6
    (the only available signal carries the full weight after renormalization)."""
    results = [
        SignalResult("T", "B3_fii_drift", 0.6),
        SignalResult("T", "B5_ipo_cluster", None),
    ]
    score = aggregate_bucket(results, BELIEF_WEIGHTS)
    assert score == pytest.approx(0.6)


def test_aggregate_bucket_weighted_blend():
    """Two signals available with different weights blend correctly."""
    results = [
        SignalResult("T", "C1_rs_breakout", 0.8),  # weight 0.30
        SignalResult("T", "C5_earnings_breadth", 0.4),  # weight 0.20
    ]
    score = aggregate_bucket(results, CONFIRMATION_WEIGHTS)
    expected = (0.8 * 0.30 + 0.4 * 0.20) / (0.30 + 0.20)
    assert score == pytest.approx(expected)


def test_phase_1_signal_roster_count():
    """Phase 1 = 2 belief + 5 confirmation signals (per spec §3.5)."""
    assert len(BELIEF_SIGNALS) == 2
    assert len(CONFIRMATION_SIGNALS) == 5


def test_output_signal_breakdown_includes_all_phase_1_signal_ids(frozen_themes):
    result = run_detector(date(2026, 5, 4), frozen_themes, states={})
    expected_ids = {s.signal_id for s in BELIEF_SIGNALS + CONFIRMATION_SIGNALS}
    for t in result["output"]["themes"]:
        assert set(t["signal_breakdown"].keys()) == expected_ids
