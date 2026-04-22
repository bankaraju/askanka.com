# pipeline/tests/test_news_intelligence_matching.py
from pipeline.news_intelligence import classify_event

UNIVERSE = ["HDFCBANK", "SUZLON", "RELIANCE"]

def test_alias_resolves_hdb_to_hdfcbank(monkeypatch, tmp_path):
    aliases = tmp_path / "news_aliases.json"
    aliases.write_text('{"HDB Financial Services": "HDFCBANK", "HDFC Bank": "HDFCBANK"}')
    # Reset cache so the monkeypatched file is re-read
    import pipeline.news_intelligence as ni
    monkeypatch.setattr(ni, "ALIASES_FILE", aliases)
    monkeypatch.setattr(ni, "_ALIASES_CACHE", None)
    item = {
        "title": "HDB Financial Services shares in focus on strong Q4 results",
        "source": "MoneyControl", "url": "x", "published": "2026-04-22",
    }
    result = classify_event(item, UNIVERSE)
    assert result is not None
    assert "HDFCBANK" in result["matched_stocks"]

def test_direct_ticker_match_still_works(monkeypatch, tmp_path):
    aliases = tmp_path / "news_aliases.json"
    aliases.write_text("{}")
    import pipeline.news_intelligence as ni
    monkeypatch.setattr(ni, "ALIASES_FILE", aliases)
    monkeypatch.setattr(ni, "_ALIASES_CACHE", None)
    item = {"title": "RELIANCE hits 52-week high", "source": "x", "url": "x", "published": "x"}
    result = classify_event(item, UNIVERSE)
    assert "RELIANCE" in result["matched_stocks"]

def test_no_alias_and_no_ticker_returns_none_or_empty_stocks():
    item = {"title": "Gold prices rise on global cues", "source": "x", "url": "x", "published": "x"}
    result = classify_event(item, UNIVERSE)
    # Either rejected (None) OR returned with policy match but empty stocks — both acceptable
    assert result is None or result["matched_stocks"] == []
