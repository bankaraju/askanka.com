"""Tests for GET /api/scanner — TA pattern scanner."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fingerprint_dir(tmp_path, monkeypatch):
    import pipeline.terminal.api.scanner as scanner_mod

    fp_dir = tmp_path / "ta_fingerprints"
    fp_dir.mkdir()

    (fp_dir / "RELIANCE.json").write_text(json.dumps({
        "symbol": "RELIANCE", "generated": "2026-04-17",
        "personality": "mixed", "best_pattern": "ATR_COMPRESSION",
        "best_win_rate": 0.72, "significant_patterns": 2,
        "fingerprint": [
            {"pattern": "ATR_COMPRESSION", "direction": "LONG", "significance": "STRONG",
             "win_rate_5d": 0.72, "avg_return_5d": 2.1, "avg_return_10d": 3.4,
             "avg_drawdown": -1.8, "occurrences": 45, "last_occurrence": "2026-04-14"},
            {"pattern": "MACD_CROSS_UP", "direction": "LONG", "significance": "MODERATE",
             "win_rate_5d": 0.65, "avg_return_5d": 1.5, "avg_return_10d": 2.2,
             "avg_drawdown": -1.2, "occurrences": 31, "last_occurrence": "2026-04-10"},
            {"pattern": "CANDLE_DOJI", "direction": "NEUTRAL", "significance": "WEAK",
             "win_rate_5d": 0.48, "avg_return_5d": 0.3, "avg_return_10d": 0.5,
             "avg_drawdown": -2.0, "occurrences": 80, "last_occurrence": "2026-04-16"},
        ],
    }))

    (fp_dir / "TCS.json").write_text(json.dumps({
        "symbol": "TCS", "generated": "2026-04-17",
        "personality": "bearish_reversal", "best_pattern": "BB_SQUEEZE",
        "best_win_rate": 0.75, "significant_patterns": 1,
        "fingerprint": [
            {"pattern": "BB_SQUEEZE", "direction": "SHORT", "significance": "STRONG",
             "win_rate_5d": 0.75, "avg_return_5d": -1.9, "avg_return_10d": -2.8,
             "avg_drawdown": -0.9, "occurrences": 22, "last_occurrence": "2026-04-12"},
        ],
    }))

    (fp_dir / "INFY.json").write_text(json.dumps({
        "symbol": "INFY", "generated": "2026-04-17",
        "personality": "neutral", "best_pattern": "RSI_OVERSOLD",
        "best_win_rate": 0.55, "significant_patterns": 1,
        "fingerprint": [
            {"pattern": "RSI_OVERSOLD", "direction": "LONG", "significance": "MODERATE",
             "win_rate_5d": 0.55, "avg_return_5d": 0.8, "avg_return_10d": 1.1,
             "avg_drawdown": -1.5, "occurrences": 5, "last_occurrence": "2026-04-08"},
        ],
    }))

    monkeypatch.setattr(scanner_mod, "_FINGERPRINTS_DIR", fp_dir)
    scanner_mod._cache.clear()
    return fp_dir


def test_scanner_default_filters(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner").json()
    assert data["total_stocks"] >= 1
    assert data["total_patterns"] >= 1
    assert "stocks" in data
    assert "filters" in data
    for stock in data["stocks"]:
        assert "symbol" in stock
        assert "patterns" in stock
        assert len(stock["patterns"]) >= 1


def test_scanner_min_win_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=70").json()
    symbols = [s["symbol"] for s in data["stocks"]]
    assert "RELIANCE" in symbols
    assert "TCS" in symbols
    assert "INFY" not in symbols
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["win_rate_5d"] >= 0.70


def test_scanner_direction_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=60&direction=SHORT").json()
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["direction"] == "SHORT"


def test_scanner_min_occurrences_filter(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=50&min_occ=25").json()
    for stock in data["stocks"]:
        for p in stock["patterns"]:
            assert p["occurrences"] >= 25


def test_scanner_sort_by_avg_return(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=60&sort=avg_return").json()
    if len(data["stocks"]) >= 2:
        avgs = [s["best_avg"] for s in data["stocks"]]
        assert avgs == sorted(avgs, reverse=True)


def test_scanner_empty_result(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=100").json()
    assert data["total_stocks"] == 0
    assert data["stocks"] == []


def test_scanner_filters_echoed(fingerprint_dir):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/scanner?min_win=75&direction=LONG&min_occ=20&sort=occurrences").json()
    assert data["filters"]["min_win"] == 75
    assert data["filters"]["direction"] == "LONG"
    assert data["filters"]["min_occ"] == 20
    assert data["filters"]["sort"] == "occurrences"
