"""Tests for the regime API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_data(tmp_path, monkeypatch):
    import pipeline.terminal.api.regime as regime_mod
    global_regime = {"updated_at": "2026-04-18T12:37:47+05:30", "zone": "EUPHORIA", "score": 2.3,
                     "regime_source": "etf_engine", "stable": True, "consecutive_days": 4,
                     "components": {}, "top_drivers": ["SPY", "QQQ"], "source_timestamp": "2026-04-18T12:37:41+05:30"}
    today_regime = {"timestamp": "2026-04-18T12:37:41+05:30", "regime": "EUPHORIA", "regime_source": "etf_engine",
                    "msi_score": 2.3, "msi_regime": "MACRO_EASY", "regime_stable": True, "consecutive_days": 4,
                    "trade_map_key": "EUPHORIA",
                    "eligible_spreads": {"Defence vs IT": {"spread": "Defence vs IT", "best_win": 73.0, "best_period": 1}},
                    "components": {}}
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "global_regime.json").write_text(json.dumps(global_regime))
    pipeline_data = tmp_path / "pipeline_data"
    pipeline_data.mkdir()
    (pipeline_data / "today_regime.json").write_text(json.dumps(today_regime))
    monkeypatch.setattr(regime_mod, "_GLOBAL_REGIME_FILE", data_dir / "global_regime.json")
    monkeypatch.setattr(regime_mod, "_TODAY_REGIME_FILE", pipeline_data / "today_regime.json")


def test_regime_returns_zone(mock_data):
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/regime")
    assert resp.status_code == 200
    data = resp.json()
    assert data["zone"] == "EUPHORIA"
    assert data["stable"] is True
    assert data["consecutive_days"] == 4


def test_regime_includes_msi(mock_data):
    from pipeline.terminal.app import app
    client = TestClient(app)
    data = client.get("/api/regime").json()
    assert data["msi_score"] == 2.3
    assert data["msi_regime"] == "MACRO_EASY"


def test_regime_includes_eligible_spreads(mock_data):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/regime").json()
    assert "Defence vs IT" in data["eligible_spreads"]


def test_regime_missing_files(tmp_path, monkeypatch):
    import pipeline.terminal.api.regime as regime_mod
    monkeypatch.setattr(regime_mod, "_GLOBAL_REGIME_FILE", tmp_path / "nope.json")
    monkeypatch.setattr(regime_mod, "_TODAY_REGIME_FILE", tmp_path / "nope2.json")
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/regime").json()
    assert data["zone"] == "UNKNOWN"


def test_regime_endpoint_returns_msi_updated_at(tmp_path, monkeypatch):
    """/api/regime must expose msi_updated_at distinct from updated_at,
    so the banner can show when MSI was last recomputed (not when ETF
    regime was last refreshed)."""
    import pipeline.terminal.api.regime as mod
    from fastapi.testclient import TestClient
    from pipeline.terminal.app import app

    today = tmp_path / "today_regime.json"
    today.write_text(json.dumps({
        "regime": "RISK-OFF",
        "msi_score": 48.2,
        "msi_regime": "MACRO_NEUTRAL",
        "msi_updated_at": "2026-04-22T11:30:00+05:30",
        "regime_stable": True,
        "consecutive_days": 2,
        "eligible_spreads": {},
        "timestamp": "2026-04-22T09:25:00+05:30",
    }))
    monkeypatch.setattr(mod, "_TODAY_REGIME_FILE", today)
    # Blank out the global file so the endpoint falls back to today_regime fields
    monkeypatch.setattr(mod, "_GLOBAL_REGIME_FILE", tmp_path / "missing_global.json")
    monkeypatch.setattr(mod, "_RECOMMENDATIONS_FILE", tmp_path / "missing_recs.json")

    body = TestClient(app).get("/api/regime").json()
    assert body["msi_updated_at"] == "2026-04-22T11:30:00+05:30"
    # updated_at is still the global regime timestamp, here fallen back to today's
    assert body["updated_at"] == "2026-04-22T09:25:00+05:30"
