"""Tests for B5 ipo_cluster — monkeypatches load_ipo_calendar."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.belief import ipo_cluster as ipo_mod
from pipeline.research.theme_detector.signals.belief.ipo_cluster import IPOClusterSignal


def _theme(theme_id: str, members: list[str], rule_kind: str = "A") -> dict:
    return {
        "theme_id": theme_id, "rule_kind": rule_kind,
        "rule_definition": {"members": members},
    }


def _calendar(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _patch_calendar(monkeypatch, df: pd.DataFrame | None):
    monkeypatch.setattr(ipo_mod, "load_ipo_calendar", lambda _run_date: df)


def test_three_keyword_matches_saturate_to_one(monkeypatch):
    """3+ matching IPOs hit the /3.0 saturation anchor."""
    df = _calendar([
        {"COMPANY NAME": "Solar Power One", "STOCK CODE": "SP1",
         "is_mainboard": True, "listing_date": date(2026, 3, 1)},
        {"COMPANY NAME": "Renewable Energy Corp", "STOCK CODE": "REC1",
         "is_mainboard": True, "listing_date": date(2026, 2, 1)},
        {"COMPANY NAME": "Clean Wind Holdings", "STOCK CODE": "CW1",
         "is_mainboard": True, "listing_date": date(2026, 1, 5)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(1.0)


def test_one_match_yields_third(monkeypatch):
    df = _calendar([
        {"COMPANY NAME": "Solar Power One", "STOCK CODE": "SP1",
         "is_mainboard": True, "listing_date": date(2026, 3, 1)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(1.0 / 3.0)


def test_no_matches_yields_zero(monkeypatch):
    df = _calendar([
        {"COMPANY NAME": "Random Diamond Co", "STOCK CODE": "RDC",
         "is_mainboard": True, "listing_date": date(2026, 3, 1)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == 0.0


def test_pit_cutoff_excludes_recent_listings(monkeypatch):
    """A listing inside run_date - 7d window must be excluded."""
    df = _calendar([
        {"COMPANY NAME": "Solar X", "STOCK CODE": "SX",
         "is_mainboard": True, "listing_date": date(2026, 4, 30)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == 0.0


def test_old_listings_outside_6m_excluded(monkeypatch):
    """A listing older than 180 days must not contribute."""
    df = _calendar([
        {"COMPANY NAME": "Solar Old", "STOCK CODE": "SO",
         "is_mainboard": True, "listing_date": date(2025, 9, 1)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == 0.0


def test_sme_listings_filtered_out(monkeypatch):
    df = _calendar([
        {"COMPANY NAME": "Solar SME", "STOCK CODE": "SS",
         "is_mainboard": False, "listing_date": date(2026, 3, 1)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score == 0.0


def test_member_match_counts_even_without_keyword(monkeypatch):
    """If a STOCK CODE is in theme.members, count it even with no keyword hit."""
    df = _calendar([
        {"COMPANY NAME": "Some Random Name", "STOCK CODE": "ZOMATO",
         "is_mainboard": True, "listing_date": date(2026, 3, 1)},
    ])
    _patch_calendar(monkeypatch, df)
    res = IPOClusterSignal().compute_for_theme(
        _theme("QUICK_COMMERCE", ["ZOMATO", "DELHIVERY"]), date(2026, 5, 1)
    )
    assert res.score == pytest.approx(1.0 / 3.0)


def test_rule_kind_b_returns_none(monkeypatch):
    _patch_calendar(monkeypatch, _calendar([]))
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = IPOClusterSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_calendar_missing_returns_none(monkeypatch):
    _patch_calendar(monkeypatch, None)
    res = IPOClusterSignal().compute_for_theme(
        _theme("POWER_RENEWABLE_TRANSITION", ["NTPC"]), date(2026, 5, 1)
    )
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")
