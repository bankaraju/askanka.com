from fastapi.testclient import TestClient

from pipeline.terminal.app import app
import pipeline.terminal.api.live as live_module


def test_returns_dict_per_ticker(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {t: 100.0 + i for i, t in enumerate(tickers)})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,BEL,TCS")
    assert r.status_code == 200
    assert r.json() == {"HAL": 100.0, "BEL": 101.0, "TCS": 102.0}


def test_uppercases_tickers(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {t: 200.0 for t in tickers})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=hal,bel")
    assert r.status_code == 200
    assert set(r.json().keys()) == {"HAL", "BEL"}


def test_rejects_empty_tickers_param(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=")
    assert r.status_code == 400


def test_rejects_whitespace_only_tickers(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=%20,,%20")
    assert r.status_code == 400


def test_caps_request_size(monkeypatch):
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=" + ",".join([f"T{i}" for i in range(100)]))
    assert r.status_code == 400


def test_returns_null_for_missing_tickers(monkeypatch):
    """Unknown tickers must not render ₹0.00 in the UI. Return null so
    the frontend falls back to the live_status.json snapshot."""
    monkeypatch.setattr(live_module, "fetch_ltps", lambda tickers: {"HAL": 4200.0})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,UNKNOWN")
    assert r.status_code == 200
    assert r.json() == {"HAL": 4200.0, "UNKNOWN": None}


def test_returns_null_for_explicit_none(monkeypatch):
    """If Kite returns a ticker with value None, pass the None through."""
    monkeypatch.setattr(live_module, "fetch_ltps",
                        lambda tickers: {"HAL": None, "BEL": 450.0})
    client = TestClient(app)
    r = client.get("/api/live_ltp?tickers=HAL,BEL")
    assert r.status_code == 200
    assert r.json() == {"HAL": None, "BEL": 450.0}
