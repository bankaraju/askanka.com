"""Integration tests: full app serves correctly."""
from fastapi.testclient import TestClient


def test_index_html_has_app_shell():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "Anka Terminal" in html
    assert "app-shell" in html
    assert "sidebar" in html
    assert "topbar" in html
    assert "main-content" in html


def test_css_served():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/static/css/terminal.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
    assert "--bg-primary" in resp.text


def test_js_app_served():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


def test_health_returns_valid_json():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "data_files" in data


def test_nonexistent_api_returns_404():
    from pipeline.terminal.app import app
    client = TestClient(app)
    resp = client.get("/api/nonexistent")
    assert resp.status_code in (404, 405)
