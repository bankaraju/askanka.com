"""Tests for C3 fo_inclusion — uses tmp_path JSON for hermetic coverage."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.research.theme_detector.signals.confirmation.fo_inclusion import (
    FOInclusionSignal,
)


def _write_history(tmp_path: Path, snapshots: list[dict]) -> Path:
    p = tmp_path / "fno_universe_history.json"
    p.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")
    return p


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def test_two_added_zero_dropped_yields_positive_score(tmp_path):
    snaps = [
        {"date": "2025-05-01", "symbols": ["A", "B"]},
        {"date": "2026-04-30", "symbols": ["A", "B", "C", "D"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B", "C", "D"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)  # 2 added / 4 members


def test_one_dropped_zero_added_yields_zero_score(tmp_path):
    snaps = [
        {"date": "2025-05-01", "symbols": ["A", "B", "C"]},
        {"date": "2026-04-30", "symbols": ["A", "B"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == 0.0  # net negative clips to 0


def test_unchanged_membership_yields_zero(tmp_path):
    snaps = [
        {"date": "2025-05-01", "symbols": ["A", "B", "C"]},
        {"date": "2026-04-30", "symbols": ["A", "B", "C"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == 0.0


def test_insufficient_history_returns_none(tmp_path):
    snaps = [{"date": "2026-04-30", "symbols": ["A"]}]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "insufficient_history" in (res.notes or "")


def test_pit_cutoff_excludes_future_snapshots(tmp_path):
    """Snapshot dated AFTER run_date - 1d must not be used."""
    snaps = [
        {"date": "2025-05-01", "symbols": ["A"]},
        {"date": "2026-05-15", "symbols": ["A", "B", "C"]},  # AFTER cutoff
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    # only 1 snapshot in window → insufficient
    assert res.score is None


def test_window_excludes_old_snapshots(tmp_path):
    """Snapshot older than 12m must not be used."""
    snaps = [
        {"date": "2024-01-01", "symbols": ["A"]},  # > 12m before run_date
        {"date": "2026-04-30", "symbols": ["A", "B", "C"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score is None  # only 1 in 12m window


def test_filter_rule_theme_returns_none(tmp_path):
    snaps = [
        {"date": "2025-05-01", "symbols": ["A"]},
        {"date": "2026-04-30", "symbols": ["A", "B"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    theme = {
        "theme_id": "T", "rule_kind": "B",
        "rule_definition": {"predicate": "..."},
    }
    res = sig.compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_history_file_missing_returns_none(tmp_path):
    sig = FOInclusionSignal(history_path=tmp_path / "does_not_exist.json")
    res = sig.compute_for_theme(_theme(["A"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_only_non_member_changes_yield_zero(tmp_path):
    """A theme of (A,B); F&O universe adds (X,Y,Z) — score 0 because none are members."""
    snaps = [
        {"date": "2025-05-01", "symbols": ["A", "B"]},
        {"date": "2026-04-30", "symbols": ["A", "B", "X", "Y", "Z"]},
    ]
    p = _write_history(tmp_path, snaps)
    sig = FOInclusionSignal(history_path=p)
    res = sig.compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == 0.0
