"""Tests for the signals API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_signals(tmp_path, monkeypatch):
    import pipeline.terminal.api.signals as signals_mod
    open_signals = [{"signal_id": "SIG-001", "status": "OPEN", "spread_name": "Defence vs IT",
                     "tier": "SIGNAL", "hit_rate": 0.733,
                     "long_legs": [{"ticker": "HAL", "price": 4284.8}],
                     "short_legs": [{"ticker": "TCS", "price": 2572.0}]}]
    recs = {"updated_at": "2026-04-18T12:37:58+05:30", "regime_zone": "EUPHORIA",
            "stocks": [{"ticker": "KAYNES", "direction": "LONG", "conviction": "HIGH", "is_stale": True}],
            "spreads": [], "news_driven": []}
    positions = {"updated_at": "2026-04-18T12:37:58+05:30",
                 "positions": [{"signal_id": "SIG-001", "spread_name": "Test", "tier": "SIGNAL",
                                "spread_pnl_pct": 3.4,
                                "long_legs": [{"ticker": "HAL", "entry": 4284.8, "current": 4381.0, "pnl_pct": 2.25}],
                                "short_legs": [{"ticker": "TCS", "entry": 2572.0, "current": 2583.6, "pnl_pct": -0.45}]}]}
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    (signals_dir / "open_signals.json").write_text(json.dumps(open_signals))
    data_dir = tmp_path / "web"
    data_dir.mkdir()
    (data_dir / "today_recommendations.json").write_text(json.dumps(recs))
    (data_dir / "live_status.json").write_text(json.dumps(positions))
    monkeypatch.setattr(signals_mod, "_OPEN_SIGNALS_FILE", signals_dir / "open_signals.json")
    monkeypatch.setattr(signals_mod, "_RECOMMENDATIONS_FILE", data_dir / "today_recommendations.json")
    monkeypatch.setattr(signals_mod, "_LIVE_STATUS_FILE", data_dir / "live_status.json")


def test_signals_returns_structure(mock_signals):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/signals").json()
    assert "signals" in data
    assert "recommendations" in data
    assert "positions" in data


def test_signals_has_open_signal(mock_signals):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/signals").json()
    assert len(data["signals"]) == 1
    assert data["signals"][0]["signal_id"] == "SIG-001"


def test_signals_has_recommendations(mock_signals):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/signals").json()
    assert data["recommendations"][0]["ticker"] == "KAYNES"


def test_signals_has_positions(mock_signals):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/signals").json()
    assert data["positions"][0]["spread_pnl_pct"] == 3.4


def test_signals_missing_files(tmp_path, monkeypatch):
    import pipeline.terminal.api.signals as signals_mod
    monkeypatch.setattr(signals_mod, "_OPEN_SIGNALS_FILE", tmp_path / "nope.json")
    monkeypatch.setattr(signals_mod, "_RECOMMENDATIONS_FILE", tmp_path / "nope2.json")
    monkeypatch.setattr(signals_mod, "_LIVE_STATUS_FILE", tmp_path / "nope3.json")
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/signals").json()
    assert data["signals"] == []
    assert data["recommendations"] == []
    assert data["positions"] == []
