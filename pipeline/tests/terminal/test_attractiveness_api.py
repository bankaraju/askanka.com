import json
from fastapi.testclient import TestClient


def _write_scores(tmp_path, monkeypatch):
    from pipeline.feature_scorer import storage
    f = tmp_path / "scores.json"
    f.write_text(json.dumps({
        "updated_at": "2026-04-22T14:45:00+05:30",
        "scores": {
            "KAYNES": {"score": 67, "band": "AMBER", "source": "own",
                        "top_features": [{"name": "sector_5d_return", "contribution": 0.24}],
                        "computed_at": "2026-04-22T14:45:00+05:30"},
            "TCS": {"score": 54, "band": "GREEN", "source": "own",
                     "top_features": [{"name": "nifty_breadth_5d", "contribution": 0.18}],
                     "computed_at": "2026-04-22T14:45:00+05:30"},
        },
    }), encoding="utf-8")
    monkeypatch.setattr(storage, "_SCORES_FILE", f, raising=False)


def _app_client():
    from pipeline.terminal.app import app
    return TestClient(app)


def test_get_all_attractiveness_returns_dict(tmp_path, monkeypatch):
    _write_scores(tmp_path, monkeypatch)
    client = _app_client()
    r = client.get("/api/attractiveness")
    assert r.status_code == 200
    data = r.json()
    assert "updated_at" in data and "scores" in data
    assert "KAYNES" in data["scores"]


def test_get_single_ticker_attractiveness(tmp_path, monkeypatch):
    _write_scores(tmp_path, monkeypatch)
    client = _app_client()
    r = client.get("/api/attractiveness/KAYNES")
    assert r.status_code == 200
    data = r.json()
    assert data["score"] == 67
    assert data["band"] == "AMBER"


def test_missing_ticker_returns_404(tmp_path, monkeypatch):
    _write_scores(tmp_path, monkeypatch)
    client = _app_client()
    r = client.get("/api/attractiveness/NONSUCH")
    assert r.status_code == 404
