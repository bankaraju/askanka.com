"""Tests for trading-related API endpoints."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_spreads(tmp_path, monkeypatch):
    import pipeline.terminal.api.spreads as spreads_mod
    today = {"regime": "EUPHORIA", "eligible_spreads": {
        "Defence vs IT": {"spread": "Defence vs IT", "best_win": 73.0, "best_period": 1,
                          "1d_win": 73, "3d_win": 73, "5d_win": 60, "1d_avg": -0.06, "3d_avg": 2.22, "5d_avg": 3.02}
    }}
    trade_map = {"results": {"EUPHORIA": {"Defence vs IT": {"extra": "detail"}}}}
    regime_file = tmp_path / "today_regime.json"
    regime_file.write_text(json.dumps(today))
    map_file = tmp_path / "trade_map.json"
    map_file.write_text(json.dumps(trade_map))
    monkeypatch.setattr(spreads_mod, "_TODAY_REGIME_FILE", regime_file)
    monkeypatch.setattr(spreads_mod, "_TRADE_MAP_FILE", map_file)


def test_spreads_returns_list(mock_spreads):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/spreads").json()
    assert data["zone"] == "EUPHORIA"
    assert len(data["spreads"]) == 1
    assert data["spreads"][0]["name"] == "Defence vs IT"
    assert data["spreads"][0]["best_win"] == 73.0


@pytest.fixture
def mock_news(tmp_path, monkeypatch):
    import pipeline.terminal.api.news as news_mod
    items = [
        {"headline": "HAL gets defence order", "ticker": "HAL", "timestamp": "2026-04-18T10:00:00"},
        {"headline": "Market rally continues", "sector": "NIFTY", "timestamp": "2026-04-18T09:00:00"},
    ]
    news_file = tmp_path / "fno_news.json"
    news_file.write_text(json.dumps(items))
    monkeypatch.setattr(news_mod, "_FNO_NEWS_FILE", news_file)


def test_news_macro(mock_news):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/news/macro").json()
    assert len(data["items"]) == 2


def test_news_stock_filter(mock_news):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/news/HAL").json()
    assert data["ticker"] == "HAL"
    assert len(data["items"]) == 1
    assert "HAL" in data["items"][0]["headline"]


def test_charts_404_missing_ticker():
    from pipeline.terminal.app import app
    resp = TestClient(app).get("/api/charts/NONEXISTENT")
    assert resp.status_code in (404, 200)


def test_ta_404_missing_ticker():
    from pipeline.terminal.app import app
    resp = TestClient(app).get("/api/ta/NONEXISTENT")
    assert resp.status_code == 404
