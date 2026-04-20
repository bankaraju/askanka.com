"""Tests for /api/candidates endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_candidates(tmp_path, monkeypatch):
    import pipeline.terminal.api.candidates as cand_mod
    import pipeline.terminal.api.scanner as scanner_mod

    today_regime = {
        "regime": "NEUTRAL",
        "timestamp": "2026-04-20T10:14:36.721327+05:30",
        "eligible_spreads": {
            "Pharma vs Banks": {
                "best_win": 70, "best_period": 5,
                "1d_win": 60, "3d_win": 65, "5d_win": 70,
                "long_legs": ["SUNPHARMA", "DRREDDY"],
                "short_legs": ["HDFCBANK", "ICICIBANK"],
                "conviction": "HIGH",
            },
        },
    }
    today_recs = {
        "regime_zone": "NEUTRAL",
        "stocks": [
            {"ticker": "KAYNES", "direction": "LONG", "conviction": "HIGH",
             "hit_rate": 1.0, "episodes": 12, "reason": "regime fit"},
        ],
        "spreads": [],
    }
    # Use "symbol" key — matching production correlation_breaks.json shape
    correlation_breaks = {
        "breaks": [
            {"symbol": "TATAMOTORS", "z_score": -2.3,
             "classification": "CONFIRMED_WARNING", "oi_confirmation": "yes",
             "action": "SHORT", "regime": "CAUTION"},
        ]
    }
    fingerprints_dir = tmp_path / "ta_fingerprints"
    fingerprints_dir.mkdir()
    (fingerprints_dir / "APLAPOLLO.json").write_text(json.dumps({
        "symbol": "APLAPOLLO",
        "patterns": [{
            "pattern": "DMA200_CROSS_UP", "direction": "LONG",
            "significance": "STRONG", "win_rate_5d": 0.72,
            "occurrences": 18, "last_occurrence": "2026-04-20",
        }],
    }))

    rfile = tmp_path / "today_regime.json"
    rfile.write_text(json.dumps(today_regime))
    recfile = tmp_path / "today_recommendations.json"
    recfile.write_text(json.dumps(today_recs))
    breaksfile = tmp_path / "correlation_breaks.json"
    breaksfile.write_text(json.dumps(correlation_breaks))

    monkeypatch.setattr(cand_mod, "_TODAY_REGIME_FILE", rfile)
    monkeypatch.setattr(cand_mod, "_RECOMMENDATIONS_FILE", recfile)
    monkeypatch.setattr(cand_mod, "_BREAKS_FILE", breaksfile)
    # Fix 5: monkeypatch scanner's _FINGERPRINTS_DIR + clear cache so _load_fingerprints re-reads
    monkeypatch.setattr(scanner_mod, "_FINGERPRINTS_DIR", fingerprints_dir)
    scanner_mod._cache.clear()


def test_candidates_returns_dual_arrays(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    assert "tradeable_candidates" in data
    assert "signals" in data
    assert "updated_at" in data


def test_candidates_includes_static_spread(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    static = [c for c in data["tradeable_candidates"] if c["source"] == "static_config"]
    assert len(static) == 1
    c = static[0]
    assert c["name"] == "Pharma vs Banks"
    assert c["long_legs"] == ["SUNPHARMA", "DRREDDY"]
    assert c["short_legs"] == ["HDFCBANK", "ICICIBANK"]
    assert c["conviction"] == "HIGH"
    assert c["score"] == 70  # Fix 2: score comes from best_win
    assert c["horizon_basis"] == "mean_reversion"
    assert c["sizing_basis"] is None


def test_candidates_includes_regime_engine_pick(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    regime = [c for c in data["tradeable_candidates"] if c["source"] == "regime_engine"]
    assert len(regime) == 1
    c = regime[0]
    assert c["name"] == "Phase B: KAYNES"
    assert c["long_legs"] == ["KAYNES"]
    assert c["short_legs"] == []
    assert c["horizon_basis"] == "event_decay"


def test_candidates_signals_includes_ta_event(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    ta = [s for s in data["signals"] if s["source"] == "ta_scanner"]
    assert any(s["ticker"] == "APLAPOLLO" and s["event_type"] == "DMA200_CROSS_UP" for s in ta)


def test_candidates_signals_includes_correlation_break(mock_candidates):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    breaks = [s for s in data["signals"] if s["source"] == "correlation_break"]
    assert len(breaks) == 1
    assert breaks[0]["ticker"] == "TATAMOTORS"
    # Fix 1 regression: verify z_score + new action/regime fields are present
    assert breaks[0]["context"]["z_score"] == -2.3
    assert breaks[0]["context"]["action"] == "SHORT"
    assert breaks[0]["context"]["regime"] == "CAUTION"


def test_candidates_missing_files_returns_empty_arrays(tmp_path, monkeypatch):
    import pipeline.terminal.api.candidates as cand_mod
    import pipeline.terminal.api.scanner as scanner_mod
    monkeypatch.setattr(cand_mod, "_TODAY_REGIME_FILE", tmp_path / "nope1.json")
    monkeypatch.setattr(cand_mod, "_RECOMMENDATIONS_FILE", tmp_path / "nope2.json")
    monkeypatch.setattr(cand_mod, "_BREAKS_FILE", tmp_path / "nope3.json")
    monkeypatch.setattr(scanner_mod, "_FINGERPRINTS_DIR", tmp_path / "nope_dir")
    scanner_mod._cache.clear()
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/candidates").json()
    assert data["tradeable_candidates"] == []
    assert data["signals"] == []


def test_candidates_endpoint_registered():
    from pipeline.terminal.app import app
    routes = [r.path for r in app.routes]
    assert "/api/candidates" in routes
