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


RECS_FIXTURE = Path(__file__).parent / "fixtures" / "recommendations_fixture.json"
RANKER_FIXTURE = Path(__file__).parent / "fixtures" / "regime_ranker_state_fixture.json"
NEWS_EVENTS_FIXTURE = Path(__file__).parent / "fixtures" / "news_events_today_fixture.json"
NEWS_VERDICTS_FIXTURE = Path(__file__).parent / "fixtures" / "news_verdicts_fixture.json"


def _patch_all_sources(monkeypatch):
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", FIXTURE)
    monkeypatch.setattr("website_exporter.RECOMMENDATIONS_FILE", RECS_FIXTURE)
    monkeypatch.setattr("website_exporter.RANKER_STATE_FILE", RANKER_FIXTURE)
    monkeypatch.setattr("website_exporter.NEWS_EVENTS_FILE", NEWS_EVENTS_FIXTURE)
    monkeypatch.setattr("website_exporter.NEWS_VERDICTS_FILE", NEWS_VERDICTS_FIXTURE)


def test_today_recommendations_top_level_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert set(out.keys()) == {"updated_at", "regime_zone", "regime_source_timestamp",
                                "spreads", "stocks", "news_driven", "holiday_mode"}
    assert out["regime_zone"] == "NEUTRAL"
    assert out["regime_source_timestamp"] == "2026-04-14T09:25:08.354943+05:30"
    assert out["holiday_mode"] is False
    assert isinstance(out["spreads"], list)
    assert isinstance(out["stocks"], list)
    assert isinstance(out["news_driven"], list)


def test_spreads_drop_inactive_and_none(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    names = [s["name"] for s in out["spreads"]]
    assert "PSU Banks vs Private" not in names  # action=INACTIVE conv=NONE


def test_spreads_top_3_by_conviction_then_zscore(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert len(out["spreads"]) <= 3
    # Fixture: HIGH (Pharma z=2.31, Upstream z=-2.05), MEDIUM (Defence 1.42, Metals -1.18)
    # Expected order: Pharma, Upstream, Defence
    assert [s["name"] for s in out["spreads"]] == ["Pharma vs Auto", "Upstream vs Downstream", "Defence vs IT"]


def test_spread_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    s = out["spreads"][0]
    assert set(s.keys()) == {"name", "action", "conviction", "z_score", "reason",
                              "source_timestamp", "is_stale"}
    assert s["source_timestamp"] == "2026-04-15T09:25:08.000+05:30"
    assert s["is_stale"] in (True, False)


def test_stocks_top_3_from_ranker(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert len(out["stocks"]) <= 3
    tickers = [s["ticker"] for s in out["stocks"]]
    # Fixture: HAL (HIGH), INFY (MED), RELIANCE (MED), ITC (LOW)
    # ITC (LOW) drops out at top-3
    assert "HAL" in tickers
    assert "ITC" not in tickers


def test_stock_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    s = out["stocks"][0]
    assert set(s.keys()) == {"ticker", "direction", "conviction", "trigger",
                              "source", "source_timestamp", "is_stale"}
    assert s["ticker"] == "HAL"
    assert s["direction"] == "LONG"
    assert s["conviction"] == "HIGH"
    assert s["source"] == "ranker"


def test_news_only_today_events(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    tickers = [n["ticker"] for n in out["news_driven"]]
    # OLDSTUFF is in verdicts but not in today's events — must be excluded
    assert "OLDSTUFF" not in tickers


def test_news_drops_hold_recommendations(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    # All fixture today-events have BUY/SELL verdicts; no HOLD should appear
    assert all(n["direction"] in ("LONG", "SHORT") for n in out["news_driven"])


def test_news_sorted_by_hit_rate_desc(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    rates = [n["historical_hit_rate"] for n in out["news_driven"]]
    assert rates == sorted(rates, reverse=True)
    # RELIANCE hit_rate 0.71 wins
    assert out["news_driven"][0]["ticker"] == "RELIANCE"


def test_news_card_fields(monkeypatch):
    _patch_all_sources(monkeypatch)
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    n = out["news_driven"][0]
    assert set(n.keys()) == {"ticker", "headline", "category", "direction",
                              "shelf_days", "historical_hit_rate", "precedent_count",
                              "source_timestamp", "is_stale"}
    assert n["headline"] == "Q4 results beat estimates by 8%"
    assert n["historical_hit_rate"] == 0.71
    assert n["precedent_count"] == 14


def test_missing_engine_files_returns_empty_lists(tmp_path, monkeypatch):
    """All engine source files missing → empty lists, UNKNOWN zone, no crash."""
    monkeypatch.setattr("website_exporter.TODAY_REGIME_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.RECOMMENDATIONS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.RANKER_STATE_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.NEWS_EVENTS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr("website_exporter.NEWS_VERDICTS_FILE", tmp_path / "missing.json")
    from website_exporter import export_today_recommendations
    out = export_today_recommendations()
    assert out["spreads"] == []
    assert out["stocks"] == []
    assert out["news_driven"] == []
    assert out["regime_zone"] == "UNKNOWN"
    assert out["holiday_mode"] is False
