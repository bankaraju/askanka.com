"""Tests for C6 sector_breadth — uses tmp_path-mocked CSV layout to stay hermetic."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation.sector_breadth import (
    SectorBreadthSignal,
)


def _write_synthetic_bars(
    tmp_dir: Path, symbol: str, start_close: float, trend: float, n_days: int
):
    """Write a synthetic CSV: linear trend `trend` per day starting at `start_close`."""
    dates = pd.date_range(end=date.today() - timedelta(days=1), periods=n_days, freq="B")
    closes = [start_close + i * trend for i in range(n_days)]
    df = pd.DataFrame({
        "Date": dates,
        "Close": closes,
        "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes],
        "Open": closes,
        "Volume": [1_000_000] * n_days,
    })
    df.to_csv(tmp_dir / f"{symbol}.csv", index=False)


def _theme(theme_id: str, members: list[str]) -> dict:
    return {
        "theme_id": theme_id,
        "rule_kind": "A",
        "rule_definition": {"members": members},
    }


def test_sector_breadth_returns_one_when_all_members_above_ma(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", tmp_path
    )
    members = ["A", "B", "C"]
    for sym in members:
        _write_synthetic_bars(tmp_path, sym, start_close=100, trend=1.0, n_days=300)

    sig = SectorBreadthSignal()
    result = sig.compute_for_theme(_theme("UPTREND", members), date.today())
    assert result.score is not None
    assert result.score == pytest.approx(1.0)


def test_sector_breadth_returns_zero_when_all_members_below_ma(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", tmp_path
    )
    members = ["A", "B", "C"]
    for sym in members:
        _write_synthetic_bars(tmp_path, sym, start_close=300, trend=-1.0, n_days=300)

    sig = SectorBreadthSignal()
    result = sig.compute_for_theme(_theme("DOWNTREND", members), date.today())
    assert result.score is not None
    assert result.score == pytest.approx(0.0)


def test_sector_breadth_returns_none_when_under_min_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", tmp_path
    )
    _write_synthetic_bars(tmp_path, "A", start_close=100, trend=1.0, n_days=300)
    sig = SectorBreadthSignal()
    result = sig.compute_for_theme(_theme("THIN", ["A", "B", "C"]), date.today())
    assert result.score is None
    assert "insufficient_coverage" in (result.notes or "")


def test_sector_breadth_returns_none_when_no_member_has_200d_history(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", tmp_path
    )
    members = ["A", "B", "C"]
    for sym in members:
        _write_synthetic_bars(tmp_path, sym, start_close=100, trend=1.0, n_days=50)
    sig = SectorBreadthSignal()
    result = sig.compute_for_theme(_theme("YOUNG", members), date.today())
    assert result.score is None


def test_sector_breadth_handles_filter_rule_themes_gracefully(tmp_path, monkeypatch):
    """Rule kind B (filter predicate) is not yet supported at v1 — must return None."""
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", tmp_path
    )
    sig = SectorBreadthSignal()
    theme = {
        "theme_id": "FILTER",
        "rule_kind": "B",
        "rule_definition": {"predicate": "listing_year in [2020, 2021]"},
    }
    result = sig.compute_for_theme(theme, date.today())
    assert result.score is None
    assert "rule_kind_b" in (result.notes or "")
