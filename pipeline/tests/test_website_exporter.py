"""Tests for pipeline/website_exporter.py — Global Regime Score export."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from website_exporter import export_global_regime

FIXTURE = Path(__file__).parent / "fixtures" / "today_regime_fixture.json"


def test_global_regime_basic_fields(tmp_path, monkeypatch):
    """Reads today_regime.json fixture and emits zone, score, source, stability."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    assert out["zone"] == "NEUTRAL"
    assert out["score"] == 43.7
    assert out["regime_source"] == "etf_engine"
    assert out["stable"] is True
    assert out["consecutive_days"] == 2


def test_global_regime_top_drivers(monkeypatch):
    """Top 3 drivers ordered by absolute contribution descending."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    assert out["top_drivers"] == ["inst_flow", "india_vix", "nifty_30d"]


def test_global_regime_components_passthrough(monkeypatch):
    """Full components dict is preserved for the website to render."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    out = export_global_regime()
    assert "components" in out
    assert out["components"]["india_vix"]["raw"] == 19.93


def test_global_regime_missing_file(tmp_path, monkeypatch):
    """If today_regime.json is missing, return a sentinel record (not crash)."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", tmp_path / "nope.json")
    out = export_global_regime()
    assert out["zone"] == "UNKNOWN"
    assert out["score"] is None
    assert out["top_drivers"] == []


OPEN_SIG_FIXTURE = Path(__file__).parent / "fixtures" / "open_signals_fixture.json"


def test_live_status_only_positions_and_fragility(tmp_path, monkeypatch):
    """Slimmed live_status emits updated_at, positions, fragility — no win/loss/track stats."""
    monkeypatch.setattr("website_exporter.OPEN_FILE", OPEN_SIG_FIXTURE)
    monkeypatch.setattr("website_exporter.CLOSED_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.DATA_DIR", tmp_path)
    from website_exporter import export_live_status
    out = export_live_status()
    assert set(out.keys()) == {"updated_at", "positions", "fragility"}
    assert len(out["positions"]) == 1
    pos = out["positions"][0]
    assert pos["spread_name"] == "Defence vs IT"
    assert pos["spread_pnl_pct"] == 11.14


from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def test_stale_check_recent_returns_false():
    from website_exporter import stale_check
    recent = (datetime.now(IST) - timedelta(hours=1)).isoformat()
    assert stale_check(recent) is False


def test_stale_check_old_returns_true():
    from website_exporter import stale_check
    old = (datetime.now(IST) - timedelta(hours=5)).isoformat()
    assert stale_check(old) is True


def test_stale_check_none_returns_true():
    from website_exporter import stale_check
    assert stale_check(None) is True


def test_stale_check_empty_string_returns_true():
    from website_exporter import stale_check
    assert stale_check("") is True
