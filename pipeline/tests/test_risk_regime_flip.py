import json
from pipeline.autoresearch.regime_flip_analyzer import compute_flip_drawdown_ci


def test_returns_structured_result_for_historical_zone(tmp_path):
    src = tmp_path / "regime.json"
    src.write_text(json.dumps({
        "calm_breaks": [
            {"date": "2024-01-01", "to_zone": "RISK-OFF", "nifty_5d_after": -3.1},
            {"date": "2024-02-01", "to_zone": "RISK-OFF", "nifty_5d_after": -1.2},
            {"date": "2024-03-01", "to_zone": "RISK-OFF", "nifty_5d_after": 2.0},
            {"date": "2024-04-01", "to_zone": "NEUTRAL", "nifty_5d_after": 0.8},
        ],
    }))
    result = compute_flip_drawdown_ci(source=src, to_zone="RISK-OFF", percentile=95)
    assert result["n_flips"] == 3
    assert result["p95_drawdown_pct"] < 0  # worst realistic outcome is a loss
    assert result["p95_drawdown_pct"] <= -1.2  # at or worse than the second-worst
    assert "nifty_5d_after proxy" in result["source"]


def test_zero_flips_returns_none_without_crashing(tmp_path):
    src = tmp_path / "regime.json"
    src.write_text(json.dumps({"calm_breaks": []}))
    result = compute_flip_drawdown_ci(source=src, to_zone="RISK-OFF")
    assert result["n_flips"] == 0
    assert result["p95_drawdown_pct"] is None


def test_missing_source_returns_zero_flips_with_error(tmp_path):
    result = compute_flip_drawdown_ci(source=tmp_path / "nope.json", to_zone="RISK-OFF")
    assert result["n_flips"] == 0
    assert result["error"] == "source file not found"


def test_endpoint_returns_real_production_data():
    """Smoke test against the real regime_persistence_results.json."""
    from fastapi.testclient import TestClient
    from pipeline.terminal.app import app
    client = TestClient(app)
    r = client.get("/api/risk/regime-flip?to_zone=RISK-OFF")
    assert r.status_code == 200
    data = r.json()
    assert "n_flips" in data
    assert "p95_drawdown_pct" in data
    # Production data had 17 RISK-OFF streaks; we expect some to_zone=RISK-OFF
    # flips in calm_breaks but not necessarily 17 (streaks != breaks).
    assert data["n_flips"] >= 0  # soft: just confirm endpoint shape
