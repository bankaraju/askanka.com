"""Tests for B3 fii_drift — uses monkeypatch on data_loaders.load_fii_screener."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.belief import fii_drift as fii_mod
from pipeline.research.theme_detector.signals.belief.fii_drift import FIIDriftSignal


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def _patch_loader(monkeypatch, inc_syms: list[str] | None, dec_syms: list[str] | None):
    inc_df = pd.DataFrame(index=inc_syms) if inc_syms is not None else None
    dec_df = pd.DataFrame(index=dec_syms) if dec_syms is not None else None

    def fake_loader(_run_date, polarity):
        return inc_df if polarity == "increasing" else dec_df

    monkeypatch.setattr(fii_mod, "load_fii_screener", fake_loader)


def test_all_members_in_increasing_yields_one(monkeypatch):
    _patch_loader(monkeypatch, ["A", "B", "C"], [])
    res = FIIDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)


def test_all_members_in_decreasing_yields_zero(monkeypatch):
    _patch_loader(monkeypatch, [], ["A", "B", "C"])
    res = FIIDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.0)


def test_half_split_yields_half(monkeypatch):
    _patch_loader(monkeypatch, ["A", "B"], ["C", "D"])
    res = FIIDriftSignal().compute_for_theme(_theme(["A", "B", "C", "D"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)


def test_no_match_either_screener_yields_neutral(monkeypatch):
    _patch_loader(monkeypatch, ["X", "Y"], ["Z"])
    res = FIIDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)
    assert "fii_inc=0/2" in (res.notes or "")
    assert "fii_dec=0/2" in (res.notes or "")


def test_both_screeners_missing_returns_none(monkeypatch):
    _patch_loader(monkeypatch, None, None)
    res = FIIDriftSignal().compute_for_theme(_theme(["A"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_one_screener_present_other_missing(monkeypatch):
    """If only INCREASING exists and theme members appear there, score > 0.5."""
    _patch_loader(monkeypatch, ["A", "B", "C"], None)
    res = FIIDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)


def test_filter_rule_theme_returns_none(monkeypatch):
    _patch_loader(monkeypatch, ["A"], [])
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = FIIDriftSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")
