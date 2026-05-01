"""Tests for C2 cap_drift — monkeypatches load_multigroup_curtailed."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation import cap_drift as cd_mod
from pipeline.research.theme_detector.signals.confirmation.cap_drift import (
    CapDriftSignal, REL_RET_COL, SATURATION_PCT,
)


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def _patch(monkeypatch, df: pd.DataFrame | None):
    monkeypatch.setattr(cd_mod, "load_multigroup_curtailed", lambda _d, _v: df)


def _frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["NSE Code", REL_RET_COL]).set_index("NSE Code")
    return df


def test_strong_outperformance_saturates_to_one(monkeypatch):
    _patch(monkeypatch, _frame([("A", 25.0), ("B", 30.0), ("C", 22.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)


def test_strong_underperformance_saturates_to_zero(monkeypatch):
    _patch(monkeypatch, _frame([("A", -25.0), ("B", -30.0), ("C", -22.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.0)


def test_zero_relative_returns_yields_half(monkeypatch):
    _patch(monkeypatch, _frame([("A", 0.0), ("B", 0.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)


def test_linear_interpolation_in_window(monkeypatch):
    """proxy = +10% with SATURATION_PCT=20 → score = (10+20)/40 = 0.75."""
    _patch(monkeypatch, _frame([("A", 10.0), ("B", 10.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.75)
    assert SATURATION_PCT == 20.0  # contract assertion


def test_partial_member_coverage_uses_only_present(monkeypatch):
    """Members not in snapshot are silently dropped."""
    _patch(monkeypatch, _frame([("A", 10.0), ("B", 10.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "MISSING"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.75)
    assert "members_used=2/3" in (res.notes or "")


def test_below_min_member_coverage_returns_none(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")


def test_snapshot_missing_returns_none(monkeypatch):
    _patch(monkeypatch, None)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_schema_drift_missing_column(monkeypatch):
    """If REL_RET_COL is absent, signal returns None with schema_drift note."""
    df = pd.DataFrame([("A", 1.0)], columns=["NSE Code", "OTHER COL"]).set_index("NSE Code")
    _patch(monkeypatch, df)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "schema_drift" in (res.notes or "")


def test_filter_rule_theme_returns_none(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0)]))
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = CapDriftSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_all_null_values_returns_none(monkeypatch):
    """If all member rows have null in the proxy column, signal returns None."""
    df = pd.DataFrame(
        [("A", float("nan")), ("B", float("nan"))],
        columns=["NSE Code", REL_RET_COL],
    ).set_index("NSE Code")
    _patch(monkeypatch, df)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
