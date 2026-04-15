"""Tests for pipeline/article_grounding.py."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from article_grounding import (
    load_market_context, build_topic_panel, verify_narrative,
    MarketDataMissing, Violation, TOPIC_SCHEMAS, TOLERANCE_PCT,
)

FIXTURE = Path(__file__).parent / "fixtures" / "daily_dump_fixture.json"


def _stage_fixture(tmp_path, monkeypatch, name="2026-04-15.json"):
    """Copy fixture into a tmp daily dir and point the loader at it."""
    daily = tmp_path / "daily"
    daily.mkdir()
    shutil.copy(FIXTURE, daily / name)
    monkeypatch.setattr("article_grounding.DAILY_DUMP_DIR", daily)
    return daily


def test_load_market_context_reads_brent(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    assert ctx["commodities"]["Brent Crude"]["close"] == 95.07


def test_load_market_context_reads_indices(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    assert ctx["indices"]["Nifty 50"]["close"] == 25432.1


def test_load_market_context_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("article_grounding.DAILY_DUMP_DIR", tmp_path / "daily")
    with pytest.raises(MarketDataMissing):
        load_market_context("2099-01-01")


def test_build_panel_war_brent_present(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    assert panel["Brent"] == "$95.07"


def test_build_panel_war_missing_field_renders_dash(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    # Fixture has no INDIA VIX or FII flow → both render as "—"
    assert panel["India VIX"] == "—"
    assert panel["FII flow Cr"] == "—"


def test_build_panel_unknown_topic_raises():
    with pytest.raises(KeyError):
        build_topic_panel("nonexistent", {})


def test_build_panel_returns_raw_alongside(tmp_path, monkeypatch):
    """Panel must include a hidden _raw map for the verifier to use."""
    _stage_fixture(tmp_path, monkeypatch)
    ctx = load_market_context("2026-04-15")
    panel = build_topic_panel("war", ctx)
    assert "_raw" in panel
    assert panel["_raw"]["Brent"] == 95.07
    assert panel["_raw"]["India VIX"] is None  # missing


def test_extract_dollar_numbers():
    from article_grounding import _extract_numbers
    text = "Brent rose to $103 a barrel and gold hit $2,478."
    found = _extract_numbers(text)
    kinds_and_vals = [(f.pattern_kind, f.value) for f in found]
    assert ("dollar", 103.0) in kinds_and_vals
    assert ("dollar", 2478.0) in kinds_and_vals


def test_extract_percent_and_bps():
    from article_grounding import _extract_numbers
    text = "CPI is 5.7% and the RBI raised by 25 bps."
    found = _extract_numbers(text)
    pcts = [f.value for f in found if f.pattern_kind == "pct_bps"]
    assert 5.7 in pcts
    assert 25.0 in pcts


def test_extract_index_levels():
    from article_grounding import _extract_numbers
    text = "Nifty 50 closed at 25,432 today."
    found = _extract_numbers(text)
    idx = [f.value for f in found if f.pattern_kind == "index"]
    assert 25432.0 in idx


def test_extract_includes_text_excerpt():
    from article_grounding import _extract_numbers
    text = "Indian refiners face $103 oil pressure today."
    found = _extract_numbers(text)
    dol = [f for f in found if f.pattern_kind == "dollar"][0]
    assert "$103" in dol.text_excerpt
