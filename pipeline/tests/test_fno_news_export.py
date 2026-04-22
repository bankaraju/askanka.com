"""Tests for export_fno_news() in website_exporter.

TDD: written before the implementation — these tests are expected to fail
until export_fno_news() is added to pipeline/website_exporter.py.
"""
import json
import pathlib


def test_fno_news_carries_high_impact_verdicts(tmp_path):
    verdicts = [
        {"symbol": "SUZLON", "category": "results_announcement",
         "recommendation": "ADD", "impact": "HIGH_IMPACT",
         "event_title": "Q4 beat", "historical_avg_5d": 4.2},
        {"symbol": "X", "category": "x",
         "recommendation": "NO_ACTION", "impact": "LOW",
         "event_title": "x"},
        {"symbol": "INFY", "category": "mgmt_change",
         "recommendation": "CUT", "impact": "MODERATE",
         "event_title": "CFO exits", "historical_avg_5d": -2.1},
    ]
    vfile = tmp_path / "nv.json"
    vfile.write_text(json.dumps(verdicts), encoding="utf-8")
    out = tmp_path / "fno.json"
    from pipeline.website_exporter import export_fno_news
    n = export_fno_news(source=vfile, out=out)
    assert n == 2
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 2
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"SUZLON", "INFY"}
    for r in rows:
        assert r["direction"] in ("ADD", "CUT")
        assert r["impact"] in ("HIGH_IMPACT", "MODERATE")


def test_fno_news_missing_source_returns_zero(tmp_path):
    """Source file absent — function must not raise."""
    from pipeline.website_exporter import export_fno_news
    missing = tmp_path / "nope.json"
    out = tmp_path / "fno.json"
    n = export_fno_news(source=missing, out=out)
    assert n == 0
    assert not out.exists() or out.read_text(encoding="utf-8") == "[]"


def test_fno_news_sort_high_impact_before_moderate(tmp_path):
    """HIGH_IMPACT rows must appear before MODERATE rows regardless of hit_rate."""
    verdicts = [
        {"symbol": "AAA", "category": "results_announcement",
         "recommendation": "ADD", "impact": "MODERATE",
         "event_title": "Beat", "historical_avg_5d": 9.9},
        {"symbol": "BBB", "category": "results_announcement",
         "recommendation": "CUT", "impact": "HIGH_IMPACT",
         "event_title": "Miss", "historical_avg_5d": -1.0},
    ]
    vfile = tmp_path / "nv.json"
    vfile.write_text(json.dumps(verdicts), encoding="utf-8")
    out = tmp_path / "fno.json"
    from pipeline.website_exporter import export_fno_news
    export_fno_news(source=vfile, out=out)
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert rows[0]["ticker"] == "BBB"   # HIGH_IMPACT first despite lower |hit_rate|
    assert rows[1]["ticker"] == "AAA"


def test_fno_news_no_action_excluded(tmp_path):
    """NO_ACTION verdicts must never appear in fno_news.json."""
    verdicts = [
        {"symbol": "ZZZ", "category": "results_announcement",
         "recommendation": "NO_ACTION", "impact": "HIGH_IMPACT",
         "event_title": "Neutral", "historical_avg_5d": 0.1},
    ]
    vfile = tmp_path / "nv.json"
    vfile.write_text(json.dumps(verdicts), encoding="utf-8")
    out = tmp_path / "fno.json"
    from pipeline.website_exporter import export_fno_news
    n = export_fno_news(source=vfile, out=out)
    assert n == 0
