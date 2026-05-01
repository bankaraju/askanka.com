"""Tests for C1 rs_breakout — uses tmp_path-mocked CSVs for hermetic coverage."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from pipeline.research.theme_detector.signals.confirmation.rs_breakout import (
    RSBreakoutSignal,
)


def _bars_csv(path: Path, closes: list[float], end_date: date):
    """Write fno_historical-style CSV (capitalized cols)."""
    n = len(closes)
    dates = pd.date_range(end=end_date, periods=n, freq="B")
    pd.DataFrame({
        "Date": dates,
        "Close": closes,
        "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes],
        "Open": closes,
        "Volume": [1_000_000] * n,
    }).to_csv(path, index=False)


def _nifty_csv(path: Path, closes: list[float], end_date: date):
    """Write NIFTY_daily-style CSV (lowercase cols)."""
    n = len(closes)
    dates = pd.date_range(end=end_date, periods=n, freq="B")
    pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1_000_000] * n,
    }).to_csv(path, index=False)


def _theme(members: list[str]) -> dict:
    return {"theme_id": "T", "rule_kind": "A", "rule_definition": {"members": members}}


@pytest.fixture
def rs_setup(tmp_path, monkeypatch):
    fno_dir = tmp_path / "fno_historical"
    indices_dir = tmp_path / "indices"
    fno_dir.mkdir()
    indices_dir.mkdir()
    nifty_path = indices_dir / "NIFTY_daily.csv"

    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.FNO_HISTORICAL_DIR", fno_dir
    )
    monkeypatch.setattr(
        "pipeline.research.theme_detector.data_loaders.NIFTY_50_PATH", nifty_path
    )
    return fno_dir, indices_dir, nifty_path


def test_recent_breakout_yields_high_score(rs_setup):
    """Flat for 200d then sharp 90d outperformance → top percentile rank."""
    fno_dir, _, nifty_path = rs_setup
    end = date(2026, 4, 22)
    n = 350
    flat = [100.0] * (n - 90)
    breakout = [100 * (1 + 0.005 * i) for i in range(90)]
    member_closes = flat + breakout
    nifty_closes = [10000.0] * n
    for sym in ("A", "B", "C"):
        _bars_csv(fno_dir / f"{sym}.csv", member_closes, end)
    _nifty_csv(nifty_path, nifty_closes, end)

    sig = RSBreakoutSignal()
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), end + timedelta(days=1))
    assert res.score is not None
    assert res.score >= 0.95


def test_recent_breakdown_yields_low_score(rs_setup):
    """Flat for 200d then sharp 90d underperformance → bottom percentile rank."""
    fno_dir, _, nifty_path = rs_setup
    end = date(2026, 4, 22)
    n = 350
    flat = [100.0] * (n - 90)
    breakdown = [100 * (1 - 0.005 * i) for i in range(90)]
    member_closes = flat + breakdown
    nifty_closes = [10000.0] * n
    for sym in ("A", "B", "C"):
        _bars_csv(fno_dir / f"{sym}.csv", member_closes, end)
    _nifty_csv(nifty_path, nifty_closes, end)

    sig = RSBreakoutSignal()
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), end + timedelta(days=1))
    assert res.score is not None
    assert res.score <= 0.05


def test_thin_history_returns_none(rs_setup):
    fno_dir, _, nifty_path = rs_setup
    end = date(2026, 4, 22)
    short = [100.0] * 100
    for sym in ("A", "B", "C"):
        _bars_csv(fno_dir / f"{sym}.csv", short, end)
    _nifty_csv(nifty_path, [10000.0] * 100, end)

    sig = RSBreakoutSignal()
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), end + timedelta(days=1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")


def test_under_min_members_returns_none(rs_setup):
    fno_dir, _, nifty_path = rs_setup
    end = date(2026, 4, 22)
    full = [100 * (1 + 0.001 * i) for i in range(350)]
    _bars_csv(fno_dir / "A.csv", full, end)
    _nifty_csv(nifty_path, [10000.0] * 350, end)

    sig = RSBreakoutSignal()
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), end + timedelta(days=1))
    assert res.score is None
    assert "insufficient_coverage" in (res.notes or "")


def test_filter_rule_returns_none(rs_setup):
    sig = RSBreakoutSignal()
    theme = {"theme_id": "T", "rule_kind": "B", "rule_definition": {"predicate": "..."}}
    res = sig.compute_for_theme(theme, date.today())
    assert res.score is None
    assert "rule_kind_b" in (res.notes or "")


def test_recent_acceleration_scores_above_median(rs_setup):
    """Recent-90d outperformance vs flat history → high percentile rank."""
    fno_dir, _, nifty_path = rs_setup
    end = date(2026, 4, 22)
    n = 350
    flat = [100.0] * (n - 90)
    accel = [100 * (1 + 0.005 * i) for i in range(90)]
    member_closes = flat + accel
    nifty_closes = [10000.0] * n
    for sym in ("A", "B", "C"):
        _bars_csv(fno_dir / f"{sym}.csv", member_closes, end)
    _nifty_csv(nifty_path, nifty_closes, end)

    sig = RSBreakoutSignal()
    res = sig.compute_for_theme(_theme(["A", "B", "C"]), end + timedelta(days=1))
    assert res.score is not None
    assert res.score > 0.7  # recent burst is in top-30% of trailing distribution
