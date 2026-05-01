"""Tests for C5 earnings_breadth — monkeypatches load_multigroup_curtailed."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation import earnings_breadth as eb_mod
from pipeline.research.theme_detector.signals.confirmation.earnings_breadth import (
    EarningsBreadthSignal, GROWTH_COL,
)


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def _patch(monkeypatch, df: pd.DataFrame | None):
    monkeypatch.setattr(eb_mod, "load_multigroup_curtailed", lambda _d, _v: df)


def _frame(rows: list[tuple[str, float | None]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["NSE Code", GROWTH_COL]).set_index("NSE Code")
    return df


def test_all_positive_yields_one(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0), ("B", 5.0), ("C", 1.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)


def test_all_negative_yields_zero(monkeypatch):
    _patch(monkeypatch, _frame([("A", -10.0), ("B", -5.0), ("C", -1.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == 0.0


def test_half_split_yields_half(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0), ("B", -5.0), ("C", 1.0), ("D", -1.0)]))
    res = EarningsBreadthSignal().compute_for_theme(
        _theme(["A", "B", "C", "D"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(0.5)


def test_zero_growth_treated_as_not_positive(monkeypatch):
    """Boundary: growth == 0 is NOT counted as positive (strict >)."""
    _patch(monkeypatch, _frame([("A", 0.0), ("B", 5.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)


def test_null_values_dropped(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0), ("B", float("nan")), ("C", 5.0)]))
    res = EarningsBreadthSignal().compute_for_theme(
        _theme(["A", "B", "C"]), date(2026, 5, 1)
    )
    # 2 of 2 non-null are positive
    assert res.score == pytest.approx(1.0)
    assert "members_used=2/3" in (res.notes or "")


def test_below_min_with_data_returns_none(monkeypatch):
    """Need >= 2 members with non-null growth."""
    _patch(monkeypatch, _frame([("A", 10.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")


def test_snapshot_missing_returns_none(monkeypatch):
    _patch(monkeypatch, None)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_schema_drift_missing_column(monkeypatch):
    df = pd.DataFrame([("A", 1.0)], columns=["NSE Code", "OTHER COL"]).set_index("NSE Code")
    _patch(monkeypatch, df)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "schema_drift" in (res.notes or "")


def test_filter_rule_theme_returns_none(monkeypatch):
    _patch(monkeypatch, _frame([("A", 10.0), ("B", 5.0)]))
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = EarningsBreadthSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_partial_member_coverage(monkeypatch):
    """Members not in snapshot dropped silently."""
    _patch(monkeypatch, _frame([("A", 10.0), ("B", 5.0)]))
    res = EarningsBreadthSignal().compute_for_theme(
        _theme(["A", "B", "MISSING1", "MISSING2"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(1.0)
    assert "members_used=2/4" in (res.notes or "")
