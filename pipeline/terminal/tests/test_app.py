"""Tests for the Anka Terminal FastAPI application."""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_200():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "timestamp" in data
    assert data["status"] == "ok"


def test_health_endpoint_includes_data_freshness(tmp_path, monkeypatch):
    import pipeline.terminal.api.health as health_mod
    monkeypatch.setattr(health_mod, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(health_mod, "_PIPELINE_DATA_DIR", tmp_path)

    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "data_files" in data


def test_static_files_mount():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
