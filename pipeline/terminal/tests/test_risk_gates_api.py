"""Tests for the risk gates API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_risk(tmp_path, monkeypatch):
    import pipeline.terminal.api.risk_gates as rg_mod
    closed = [
        {"signal_id": "SIG-001", "final_pnl": {"spread_pnl_pct": 2.5}, "close_timestamp": "2026-04-17T16:00:00+05:30"},
        {"signal_id": "SIG-002", "final_pnl": {"spread_pnl_pct": -1.2}, "close_timestamp": "2026-04-16T16:00:00+05:30"},
    ]
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    (signals_dir / "closed_signals.json").write_text(json.dumps(closed))
    monkeypatch.setattr(rg_mod, "_CLOSED_SIGNALS_FILE", signals_dir / "closed_signals.json")


def test_risk_gates_returns_status(mock_risk):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/risk-gates").json()
    assert "allowed" in data
    assert "level" in data
    assert "sizing_factor" in data
    assert "cumulative_pnl" in data


def test_risk_gates_allowed_when_positive(mock_risk):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/risk-gates").json()
    assert data["allowed"] is True
    assert data["level"] == "L0"
    assert data["sizing_factor"] == 1.0


def test_risk_gates_missing_file(tmp_path, monkeypatch):
    import pipeline.terminal.api.risk_gates as rg_mod
    monkeypatch.setattr(rg_mod, "_CLOSED_SIGNALS_FILE", tmp_path / "nope.json")
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/risk-gates").json()
    assert data["allowed"] is True
    assert data["level"] == "L0"
