"""Tests for C5 earnings_breadth — canonical-first (NPS) with proxy fallback.

v1.0.1 (2026-05-02): patched to prefer Net Profit Surprise Qtr % from
results_dashboard (canonical TD-D9) over the v1 Net Profit QoQ Growth % proxy.
Tests cover both paths + the threshold-based fallback boundary.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation import earnings_breadth as eb_mod
from pipeline.research.theme_detector.signals.confirmation.earnings_breadth import (
    EarningsBreadthSignal,
    GROWTH_COL,
    NPS_COL,
)


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def _patch(monkeypatch, *, canonical_df=None, proxy_df=None):
    monkeypatch.setattr(eb_mod, "load_results_dashboard", lambda _d: canonical_df)
    monkeypatch.setattr(
        eb_mod, "load_multigroup_curtailed", lambda _d, _v: proxy_df
    )


def _proxy_frame(rows: list[tuple[str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["NSE Code", GROWTH_COL]).set_index("NSE Code")


def _canonical_frame(rows: list[tuple[str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["NSE Code", NPS_COL]).set_index("NSE Code")


# ----- canonical path -----


def test_canonical_all_positive_yields_one(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", 5.0), ("B", 1.2), ("C", 3.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)
    assert "source=canonical_net_profit_surprise" in (res.notes or "")
    assert "3/3 positive" in (res.notes or "")


def test_canonical_all_negative_yields_zero(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", -5.0), ("B", -1.2)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == 0.0
    assert "source=canonical" in (res.notes or "")


def test_canonical_half_split(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", 5.0), ("B", -1.2), ("C", 3.0), ("D", -0.5)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C", "D"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)


def test_canonical_zero_treated_as_not_positive(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", 0.0), ("B", 5.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)


def test_canonical_null_values_dropped(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", 5.0), ("B", float("nan")), ("C", 1.0)]))
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)
    assert "members_used=2/3" in (res.notes or "")


# ----- canonical → proxy fallback -----


def test_below_canonical_threshold_falls_back_to_proxy(monkeypatch):
    """Only 1 member with NPS — below MIN_CANONICAL_COVERAGE — fall to proxy."""
    canonical = _canonical_frame([("A", 5.0)])
    proxy = _proxy_frame([("A", 10.0), ("B", -5.0), ("C", 3.0)])
    _patch(monkeypatch, canonical_df=canonical, proxy_df=proxy)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    # 2 of 3 proxy positive
    assert res.score == pytest.approx(2 / 3)
    assert "source=proxy_qoq_growth" in (res.notes or "")
    assert "canonical=1" in (res.notes or "")


def test_no_canonical_data_falls_back_to_proxy(monkeypatch):
    """results_dashboard missing entirely → proxy path."""
    proxy = _proxy_frame([("A", 10.0), ("B", 5.0)])
    _patch(monkeypatch, canonical_df=None, proxy_df=proxy)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)
    assert "source=proxy_qoq_growth" in (res.notes or "")
    assert "canonical=0" in (res.notes or "")


def test_canonical_no_member_overlap_falls_back(monkeypatch):
    """Canonical loaded but no theme member matches → proxy path."""
    canonical = _canonical_frame([("X", 5.0), ("Y", -3.0)])  # no A/B
    proxy = _proxy_frame([("A", 10.0), ("B", 1.0)])
    _patch(monkeypatch, canonical_df=canonical, proxy_df=proxy)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)
    assert "source=proxy_qoq_growth" in (res.notes or "")


# ----- both unavailable -----


def test_both_sources_missing_returns_none(monkeypatch):
    _patch(monkeypatch, canonical_df=None, proxy_df=None)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_proxy_below_min_after_canonical_thin(monkeypatch):
    """Canonical thin AND proxy below MIN_MEMBERS_WITH_DATA → None."""
    canonical = _canonical_frame([("A", 5.0)])
    proxy = _proxy_frame([("A", 10.0)])
    _patch(monkeypatch, canonical_df=canonical, proxy_df=proxy)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")
    assert "canonical=1" in (res.notes or "")
    assert "proxy=1/2" in (res.notes or "")


def test_proxy_schema_drift_after_canonical_thin(monkeypatch):
    canonical = _canonical_frame([("A", 5.0)])
    bad_proxy = pd.DataFrame([("A", 1.0)], columns=["NSE Code", "OTHER"]).set_index("NSE Code")
    _patch(monkeypatch, canonical_df=canonical, proxy_df=bad_proxy)
    res = EarningsBreadthSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "schema_drift" in (res.notes or "")


def test_filter_rule_theme_returns_none(monkeypatch):
    _patch(monkeypatch, canonical_df=_canonical_frame([("A", 5.0), ("B", 1.0)]))
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = EarningsBreadthSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_partial_canonical_member_coverage(monkeypatch):
    """Some members missing from canonical snapshot — counted only over present."""
    canonical = _canonical_frame([("A", 5.0), ("B", 1.0)])
    _patch(monkeypatch, canonical_df=canonical)
    res = EarningsBreadthSignal().compute_for_theme(
        _theme(["A", "B", "MISSING1", "MISSING2"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(1.0)
    assert "members_used=2/4" in (res.notes or "")
