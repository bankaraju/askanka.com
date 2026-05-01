"""Tests for C2 cap_drift — canonical-first (TD-D1 weight delta) with proxy fallback.

v1.0.2 (2026-05-02): patched to prefer 6-month delta in summed NIFTY-500 weight
from the reconstructed weight history, fall back to v1 proxy
(Relative returns vs Nifty50 quarter%) when canonical lacks coverage.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation import cap_drift as cd_mod
from pipeline.research.theme_detector.signals.confirmation.cap_drift import (
    CapDriftSignal,
    REL_RET_COL,
    PROXY_SATURATION_PCT,
    SATURATION_DELTA_PP,
)


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


def _patch(monkeypatch, *, canonical_df=None, proxy_df=None):
    monkeypatch.setattr(
        cd_mod, "load_nifty500_weights_reconstructed", lambda _d: canonical_df
    )
    monkeypatch.setattr(cd_mod, "load_multigroup_curtailed", lambda _d, _v: proxy_df)


def _proxy_frame(rows: list[tuple[str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["NSE Code", REL_RET_COL]).set_index("NSE Code")


def _canonical_frame(today_d: date, past_d: date, rows_today: list[tuple[str, float]],
                     rows_past: list[tuple[str, float]]) -> pd.DataFrame:
    """Build a 2-date DataFrame indexed by date with nse_symbol + weight_pct cols."""
    rows = []
    for sym, w in rows_today:
        rows.append({"date": today_d, "nse_symbol": sym, "weight_pct": w})
    for sym, w in rows_past:
        rows.append({"date": past_d, "nse_symbol": sym, "weight_pct": w})
    df = pd.DataFrame(rows)
    return df.set_index("date")


# ----- canonical path -----


def test_canonical_strong_positive_delta_saturates_one(monkeypatch):
    """Theme weight rises ≥ SATURATION_DELTA_PP over 6m → score = 1.0."""
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=180)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 3.0), ("B", 2.5), ("X", 5.0)],
        rows_past=[("A", 1.0), ("B", 1.5), ("X", 5.0)],
    )
    _patch(monkeypatch, canonical_df=canonical)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    # delta = (3.0 + 2.5) - (1.0 + 1.5) = +3.0pp, saturates to 1.0
    assert res.score == pytest.approx(1.0)
    assert "source=canonical_nifty500_weight_delta_6m" in (res.notes or "")


def test_canonical_strong_negative_delta_saturates_zero(monkeypatch):
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=180)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 1.0), ("B", 1.0)],
        rows_past=[("A", 3.0), ("B", 2.0)],
    )
    _patch(monkeypatch, canonical_df=canonical)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    # delta = 2 - 5 = -3pp, saturates to 0
    assert res.score == pytest.approx(0.0)


def test_canonical_zero_delta_yields_half(monkeypatch):
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=180)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 2.0), ("B", 1.0)],
        rows_past=[("A", 2.0), ("B", 1.0)],
    )
    _patch(monkeypatch, canonical_df=canonical)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    assert res.score == pytest.approx(0.5)


def test_canonical_linear_interpolation(monkeypatch):
    """delta = +0.5pp with SATURATION_DELTA_PP=1.0 → score = (0.5+1)/2 = 0.75."""
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=180)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 1.5), ("B", 1.5)],
        rows_past=[("A", 1.25), ("B", 1.25)],
    )
    _patch(monkeypatch, canonical_df=canonical)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    assert res.score == pytest.approx(0.75)
    assert SATURATION_DELTA_PP == 1.0


# ----- canonical → proxy fallback -----


def test_canonical_thin_coverage_falls_back_to_proxy(monkeypatch):
    """Only 1 member in canonical → fallback to proxy."""
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=180)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 2.0)],
        rows_past=[("A", 1.0)],
    )
    proxy = _proxy_frame([("A", 10.0), ("B", 10.0)])
    _patch(monkeypatch, canonical_df=canonical, proxy_df=proxy)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    # proxy 10% with PROXY_SATURATION_PCT=20 → 0.75
    assert res.score == pytest.approx(0.75)
    assert "source=proxy_rel_ret_qtr" in (res.notes or "")
    assert "canonical_skip" in (res.notes or "")


def test_no_canonical_falls_back_to_proxy(monkeypatch):
    proxy = _proxy_frame([("A", 0.0), ("B", 0.0)])
    _patch(monkeypatch, canonical_df=None, proxy_df=proxy)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.5)
    assert "source=proxy_rel_ret_qtr" in (res.notes or "")


def test_canonical_short_lookback_falls_back_to_proxy(monkeypatch):
    """Only 30d of canonical history → below MIN_LOOKBACK_DAYS → proxy."""
    today_d = date(2026, 5, 1)
    past_d = today_d - timedelta(days=30)
    canonical = _canonical_frame(
        today_d, past_d,
        rows_today=[("A", 2.0), ("B", 1.0)],
        rows_past=[("A", 1.0), ("B", 0.5)],
    )
    proxy = _proxy_frame([("A", 0.0), ("B", 0.0)])
    _patch(monkeypatch, canonical_df=canonical, proxy_df=proxy)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), today_d)
    assert res.score == pytest.approx(0.5)
    assert "source=proxy" in (res.notes or "")


# ----- proxy edge cases (preserved from v1) -----


def test_proxy_strong_outperformance_saturates_to_one(monkeypatch):
    _patch(monkeypatch, canonical_df=None,
           proxy_df=_proxy_frame([("A", 25.0), ("B", 30.0), ("C", 22.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score == pytest.approx(1.0)
    assert PROXY_SATURATION_PCT == 20.0


def test_proxy_below_min_member_returns_none(monkeypatch):
    _patch(monkeypatch, canonical_df=None,
           proxy_df=_proxy_frame([("A", 10.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "C"]), date(2026, 5, 1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")


def test_both_sources_missing_returns_none(monkeypatch):
    _patch(monkeypatch, canonical_df=None, proxy_df=None)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "data_unavailable" in (res.notes or "")


def test_proxy_schema_drift(monkeypatch):
    bad = pd.DataFrame([("A", 1.0)], columns=["NSE Code", "OTHER"]).set_index("NSE Code")
    _patch(monkeypatch, canonical_df=None, proxy_df=bad)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None
    assert "schema_drift" in (res.notes or "")


def test_filter_rule_theme_returns_none(monkeypatch):
    _patch(monkeypatch, canonical_df=None,
           proxy_df=_proxy_frame([("A", 10.0), ("B", 10.0)]))
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = CapDriftSignal().compute_for_theme(theme, date(2026, 5, 1))
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_proxy_all_null_returns_none(monkeypatch):
    df = pd.DataFrame(
        [("A", float("nan")), ("B", float("nan"))],
        columns=["NSE Code", REL_RET_COL],
    ).set_index("NSE Code")
    _patch(monkeypatch, canonical_df=None, proxy_df=df)
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B"]), date(2026, 5, 1))
    assert res.score is None


def test_proxy_partial_member_coverage(monkeypatch):
    _patch(monkeypatch, canonical_df=None,
           proxy_df=_proxy_frame([("A", 10.0), ("B", 10.0)]))
    res = CapDriftSignal().compute_for_theme(_theme(["A", "B", "MISSING"]), date(2026, 5, 1))
    assert res.score == pytest.approx(0.75)
    assert "members_used=2/3" in (res.notes or "")
