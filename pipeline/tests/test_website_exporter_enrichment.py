import json
import pytest
from pathlib import Path


def test_export_live_status_includes_enrichment(tmp_path, monkeypatch):
    import pipeline.website_exporter as we

    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    open_file = signals_dir / "open_signals.json"
    open_file.write_text(json.dumps([{
        "signal_id": "SIG-TEST",
        "spread_name": "X vs Y",
        "category": "test",
        "tier": "SIGNAL",
        "open_timestamp": "2026-04-16T12:00:00",
        "long_legs": [{"ticker": "HAL", "price": 100}],
        "short_legs": [{"ticker": "TCS", "price": 200}],
        "peak_spread_pnl_pct": 0,
        "_data_levels": {},
        "source": "CORRELATION_BREAK",
        "trust_scores": {"HAL": {"trust_grade": "A"}, "TCS": {"trust_grade": "B+"}},
        "regime_rank": {"HAL": {"hit_rate": 0.62}},
        "correlation_breaks": {},
        "oi_anomalies": {},
        "conviction_score": 72.5,
        "gate_reason": None,
        "rigour_trail": {"should": "NOT appear in output"},
    }]))
    monkeypatch.setattr(we, "OPEN_FILE", open_file)

    # Patch fetch_current_prices inside signal_tracker to avoid network calls
    import types
    fake_st = types.ModuleType("signal_tracker")
    fake_st.fetch_current_prices = lambda tickers: {}
    monkeypatch.setitem(__import__("sys").modules, "signal_tracker", fake_st)

    result = we.export_live_status()
    pos = result["positions"][0]

    assert pos["source"] == "CORRELATION_BREAK"
    assert pos["trust_scores"]["HAL"]["trust_grade"] == "A"
    assert pos["conviction_score"] == 72.5
    assert pos["gate_reason"] is None
    assert "rigour_trail" not in pos  # internal, not exported


def test_export_live_status_works_without_enrichment(tmp_path, monkeypatch):
    import pipeline.website_exporter as we

    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    open_file = signals_dir / "open_signals.json"
    # Old-style signal without enrichment
    open_file.write_text(json.dumps([{
        "signal_id": "SIG-OLD",
        "spread_name": "A vs B",
        "category": "test",
        "tier": "SIGNAL",
        "open_timestamp": "2026-04-16T12:00:00",
        "long_legs": [{"ticker": "HAL", "price": 100}],
        "short_legs": [],
        "peak_spread_pnl_pct": 0,
    }]))
    monkeypatch.setattr(we, "OPEN_FILE", open_file)

    # Patch fetch_current_prices inside signal_tracker to avoid network calls
    import types
    fake_st = types.ModuleType("signal_tracker")
    fake_st.fetch_current_prices = lambda tickers: {}
    monkeypatch.setitem(__import__("sys").modules, "signal_tracker", fake_st)

    result = we.export_live_status()
    pos = result["positions"][0]

    assert pos["source"] == "SPREAD"  # default
    assert pos["trust_scores"] is None  # graceful None
    assert pos["conviction_score"] is None
