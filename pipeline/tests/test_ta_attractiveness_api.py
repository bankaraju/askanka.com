from fastapi.testclient import TestClient
from pipeline.terminal.app import app
from pipeline.ta_scorer import storage


def test_ta_attractiveness_all(monkeypatch):
    def fake(path=None):
        return {"updated_at": "2026-04-23T16:00:00+05:30",
                "scores": {"RELIANCE": {"ticker": "RELIANCE", "score": 72,
                                         "band": "HIGH", "health": "GREEN",
                                         "source": "own", "top_features": [],
                                         "computed_at": "2026-04-23T16:00:00+05:30"}}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness")
    assert r.status_code == 200
    assert r.json()["scores"]["RELIANCE"]["score"] == 72


def test_ta_attractiveness_ticker_hit(monkeypatch):
    def fake(path=None):
        return {"updated_at": "x", "scores": {"RELIANCE": {"score": 55}}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness/RELIANCE")
    assert r.status_code == 200
    assert r.json()["score"] == 55


def test_ta_attractiveness_ticker_miss(monkeypatch):
    def fake(path=None):
        return {"updated_at": "x", "scores": {}}
    monkeypatch.setattr(storage, "read_scores", fake)
    with TestClient(app) as c:
        r = c.get("/api/ta_attractiveness/ITC")
    assert r.status_code == 404
