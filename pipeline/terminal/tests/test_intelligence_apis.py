"""Tests for intelligence API endpoints."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_trust(tmp_path, monkeypatch):
    import pipeline.terminal.api.trust_scores as ts_mod
    trust = {"updated_at": "2026-04-18T12:00:00+05:30", "total_scored": 2,
             "stocks": [
                 {"symbol": "HAL", "trust_grade": "A", "trust_score": 85, "thesis": "Strong defence play"},
                 {"symbol": "TCS", "trust_grade": "B+", "trust_score": 72, "thesis": "IT bellwether"},
             ]}
    f = tmp_path / "trust.json"
    f.write_text(json.dumps(trust))
    monkeypatch.setattr(ts_mod, "_TRUST_FILE", f)


def test_trust_scores_returns_list(mock_trust):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores").json()
    assert data["total"] == 2
    assert data["stocks"][0]["symbol"] == "HAL"


def test_trust_score_detail(mock_trust):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores/HAL").json()
    assert data["trust_grade"] == "A"
    assert data["trust_score"] == 85


def test_trust_score_missing():
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores/NONEXISTENT").json()
    assert data["trust_grade"] == "?"


def test_research_returns_list():
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research").json()
    assert "articles" in data
    assert "total" in data
