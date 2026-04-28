"""Tests for /api/sidebar-status."""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stub_files(tmp_path, monkeypatch):
    """Lay out the artifact files the endpoint reads, then monkeypatch the
    module's _DATA_DIR / _PIPELINE_DATA_DIR + rebuild the _TABS table to point
    at tmp_path."""
    import pipeline.terminal.api.sidebar_status as ss

    data_dir = tmp_path / "data"
    pipe_dir = tmp_path / "pdata"
    data_dir.mkdir()
    pipe_dir.mkdir()

    (data_dir / "live_status.json").write_text(json.dumps([{"id": 1}, {"id": 2}, {"id": 3}]))
    (pipe_dir / "open_signals.json").write_text(json.dumps([{"id": "a"}, {"id": "b"}]))
    (pipe_dir / "today_regime.json").write_text(json.dumps({"regime": "NEUTRAL"}))
    (pipe_dir / "pattern_signals_today.json").write_text(json.dumps({"top_10": [1, 2, 3, 4, 5]}))
    (data_dir / "trust_scores.json").write_text(json.dumps({"scores": [{}] * 210}))
    (pipe_dir / "news_verdicts.json").write_text(json.dumps([{"e": 1}] * 12))
    (pipe_dir / "oi_anomalies.json").write_text(json.dumps({"anomalies": [{}, {}, {}]}))
    (data_dir / "gap_risk.json").write_text(json.dumps({"items": [{}, {}]}))
    (data_dir / "articles_index.json").write_text(json.dumps({"articles": [{}] * 7}))
    (data_dir / "track_record.json").write_text(json.dumps({"closed": [{}] * 50}))

    monkeypatch.setattr(ss, "_DATA_DIR", data_dir)
    monkeypatch.setattr(ss, "_PIPELINE_DATA_DIR", pipe_dir)
    monkeypatch.setattr(ss, "_TABS", [
        ss.TabSpec("dashboard",     data_dir / "live_status.json",                900,        "open_signals"),
        ss.TabSpec("live-monitor",  pipe_dir / "open_signals.json",               900,        "open_signals"),
        ss.TabSpec("regime",        pipe_dir / "today_regime.json",               86400,      "open_signals"),
        ss.TabSpec("scanner",       pipe_dir / "pattern_signals_today.json",      86400,      "pattern_signals"),
        ss.TabSpec("trust",         data_dir / "trust_scores.json",               7 * 86400,  "trust_scores"),
        ss.TabSpec("news",          pipe_dir / "news_verdicts.json",              3600,       "news"),
        ss.TabSpec("options",       pipe_dir / "oi_anomalies.json",               900,        "options_oi"),
        ss.TabSpec("risk",          data_dir / "gap_risk.json",                   86400,      "risk"),
        ss.TabSpec("research",      data_dir / "articles_index.json",             86400,      "articles"),
        ss.TabSpec("track-record",  data_dir / "track_record.json",               86400,      "track_record_closed"),
    ])
    return tmp_path


def _get(client) -> dict:
    return client.get("/api/sidebar-status").json()


def test_endpoint_returns_one_entry_per_tab(stub_files):
    from pipeline.terminal.app import app
    data = _get(TestClient(app))
    assert "timestamp" in data
    tabs = {t["tab"]: t for t in data["tabs"]}
    expected = {"dashboard", "live-monitor", "regime", "scanner", "trust",
                "news", "options", "risk", "research", "track-record"}
    assert set(tabs.keys()) == expected


def test_counts_match_artifacts(stub_files):
    from pipeline.terminal.app import app
    tabs = {t["tab"]: t for t in _get(TestClient(app))["tabs"]}
    assert tabs["live-monitor"]["count"] == 2
    assert tabs["scanner"]["count"] == 5
    assert tabs["trust"]["count"] == 210
    assert tabs["news"]["count"] == 12
    assert tabs["options"]["count"] == 3
    assert tabs["risk"]["count"] == 2
    assert tabs["research"]["count"] == 7
    assert tabs["track-record"]["count"] == 50


def test_freshly_written_files_are_live(stub_files):
    from pipeline.terminal.app import app
    tabs = {t["tab"]: t for t in _get(TestClient(app))["tabs"]}
    # Files were just written; every age should be < cadence.
    for tab in tabs.values():
        assert tab["status"] == "live", f"{tab['tab']} should be live, got {tab['status']} (age={tab['age_s']})"


def test_missing_file_reports_missing_status(stub_files):
    from pipeline.terminal.app import app
    import pipeline.terminal.api.sidebar_status as ss
    # Remove one of the artifacts to simulate a never-written file.
    (stub_files / "pdata" / "oi_anomalies.json").unlink()
    tabs = {t["tab"]: t for t in _get(TestClient(app))["tabs"]}
    assert tabs["options"]["status"] == "missing"
    assert tabs["options"]["count"] is None
    assert tabs["options"]["age_s"] is None


def test_aged_file_drops_to_fresh_then_stale(stub_files, monkeypatch):
    """Backdate one file's mtime and confirm bucketing transitions."""
    from pipeline.terminal.app import app
    import pipeline.terminal.api.sidebar_status as ss

    f = stub_files / "pdata" / "oi_anomalies.json"  # cadence_s = 900
    # 2x cadence → fresh
    aged = time.time() - 1800
    os.utime(f, (aged, aged))
    tabs = {t["tab"]: t for t in _get(TestClient(app))["tabs"]}
    assert tabs["options"]["status"] == "fresh"

    # 5x cadence → stale
    aged = time.time() - (5 * 900)
    os.utime(f, (aged, aged))
    tabs = {t["tab"]: t for t in _get(TestClient(app))["tabs"]}
    assert tabs["options"]["status"] == "stale"
