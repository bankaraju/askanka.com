"""Tests for pipeline/article_grounding.py."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from article_grounding import (
    load_market_context, build_topic_panel, verify_narrative,
    render_panel_html,
    MarketDataMissing, Violation, TOPIC_SCHEMAS, TOLERANCE_PCT,
)

FIXTURE = Path(__file__).parent / "fixtures" / "daily_dump_fixture.json"
FIXTURES = Path(__file__).parent / "fixtures"


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


def test_whitelist_pct_of_imports():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("85% of crude imports come from", 85.0, "pct_bps")


def test_whitelist_per_liter():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("retail prices up by ₹5-7 per liter", 7.0, "rupee")


def test_whitelist_year_window():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("over the next 2-3 years", 3.0, "pct_bps")


def test_whitelist_jobs():
    from article_grounding import _is_whitelisted
    assert _is_whitelisted("creating 3,000 jobs in defence", 3000.0, "pct_bps")


def test_whitelist_does_not_match_market_price():
    from article_grounding import _is_whitelisted
    assert not _is_whitelisted("Brent rose to $103 a barrel", 103.0, "dollar")


def _war_panel(tmp_path, monkeypatch):
    _stage_fixture(tmp_path, monkeypatch)
    return build_topic_panel("war", load_market_context("2026-04-15"))


def test_verify_clean_narrative_returns_no_violations(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Brent closed at $95 a barrel today, with WTI at $92.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_catches_today_bug_103_oil(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Crude spiked another 3% today to $103 a barrel.</p>"
    issues = verify_narrative(text, panel)
    assert len(issues) == 1
    v = issues[0]
    assert v.number == 103.0
    assert v.pattern_kind == "dollar"
    assert v.closest_panel_value == ("Brent", 95.07)


def test_verify_within_tolerance_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    # 95.07 * 1.018 = 96.78 — within 2% tolerance
    text = "<p>Brent at $96.78 today.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_whitelisted_85pct_of_imports_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>India imports 85% of crude oil from OPEC.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_whitelisted_per_liter_passes(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    text = "<p>Petrol prices could rise ₹5-7 per liter at the pump.</p>"
    issues = verify_narrative(text, panel)
    assert issues == []


def test_verify_index_violation(tmp_path, monkeypatch):
    panel = _war_panel(tmp_path, monkeypatch)
    # Panel Nifty 50 = 25432.1; "26500" is way outside ±2% (~510)
    text = "<p>Nifty 50 closed at 26,500 today.</p>"
    issues = verify_narrative(text, panel)
    assert len(issues) == 1
    assert issues[0].pattern_kind == "index"


def test_render_panel_html_contains_labels_and_values(tmp_path, monkeypatch):
    panel = {
        "Brent": "$93.20/bbl",
        "Nifty 50": "25,432.10",
        "_raw": {"should": "not appear"},
    }
    html = render_panel_html(panel, "2026-04-15")
    assert "Brent" in html
    assert "$93.20/bbl" in html
    assert "Nifty 50" in html
    assert "25,432.10" in html
    assert "2026-04-15" in html
    assert "_raw" not in html


def test_render_panel_html_renders_dash_for_missing():
    panel = {"India VIX": "\u2014"}
    html = render_panel_html(panel, "2026-04-15")
    assert "India VIX" in html
    assert "\u2014" in html


def test_panel_includes_delta_when_prior_present(tmp_path):
    import json as _json
    from article_grounding import build_topic_panel
    curr = _json.loads((FIXTURES / "daily_dump_fixture.json").read_text(encoding="utf-8"))
    prior = _json.loads((FIXTURES / "daily_dump_prior_fixture.json").read_text(encoding="utf-8"))
    panel = build_topic_panel("war", curr, prior_context=prior)
    assert "Brent" in panel
    # Brent fell 102.78 -> 95.07, ~-7.5%
    assert "-7.5" in panel["Brent"] or "-7.50" in panel["Brent"]
    # _deltas should be populated and numeric
    assert "_deltas" in panel
    assert panel["_deltas"]["Brent"] is not None
    assert panel["_deltas"]["Brent"] < -5


def test_panel_no_delta_when_prior_missing():
    from article_grounding import build_topic_panel
    import json as _json
    curr = _json.loads((FIXTURES / "daily_dump_fixture.json").read_text(encoding="utf-8"))
    panel = build_topic_panel("war", curr, prior_context=None)
    # No delta should appear in the Brent string
    assert "(" not in panel["Brent"] or "%" not in panel["Brent"]
    assert panel["_deltas"]["Brent"] is None


def test_load_prior_context_walks_back_past_missing(tmp_path, monkeypatch):
    from article_grounding import load_prior_context
    # Create only day -3 exists
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-04-11.json").write_text('{"ok": 1}', encoding="utf-8")
    monkeypatch.setattr("article_grounding.DAILY_DUMP_DIR", daily)
    out = load_prior_context("2026-04-14", max_lookback=5)
    assert out == {"ok": 1}
    out2 = load_prior_context("2026-04-14", max_lookback=1)
    assert out2 is None
