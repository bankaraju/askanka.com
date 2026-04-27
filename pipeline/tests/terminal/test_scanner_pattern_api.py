import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pipeline.terminal.api.scanner_pattern import router, _resolve_signals_path


@pytest.fixture
def client_with_fixture(tmp_path, monkeypatch):
    fixture = {
        "as_of": "2026-04-27T16:30:00+05:30",
        "universe_size": 213,
        "today_flags_total": 47,
        "qualified_count": 18,
        "below_threshold_count": 29,
        "top_10": [
            {"signal_id": "2026-04-27_BPCL_BULLISH_HAMMER",
             "date": "2026-04-27", "ticker": "BPCL",
             "pattern_id": "BULLISH_HAMMER", "direction": "LONG",
             "composite_score": 4.27, "n_occurrences": 156,
             "win_rate": 0.62, "z_score": 3.0, "mean_pnl_pct": 0.012,
             "fold_stability": 0.78, "last_seen": "2026-03-12"}
        ],
    }
    f = tmp_path / "pattern_signals_today.json"
    f.write_text(json.dumps(fixture))
    monkeypatch.setattr(
        "pipeline.terminal.api.scanner_pattern._resolve_signals_path",
        lambda: f,
    )
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_endpoint_returns_full_payload(client_with_fixture):
    r = client_with_fixture.get("/api/scanner/pattern-signals")
    assert r.status_code == 200
    data = r.json()
    assert data["as_of"].startswith("2026-04-27")
    assert data["universe_size"] == 213
    assert len(data["top_10"]) == 1
    assert "cumulative_paired_shadow" in data


def test_endpoint_missing_file_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.terminal.api.scanner_pattern._resolve_signals_path",
        lambda: tmp_path / "does_not_exist.json",
    )
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/scanner/pattern-signals")
    assert r.status_code == 404
