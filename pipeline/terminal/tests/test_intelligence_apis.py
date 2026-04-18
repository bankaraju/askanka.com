"""Tests for intelligence API endpoints — trust scores + research digest."""
import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

IST = timezone(timedelta(hours=5, minutes=30))


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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


@pytest.fixture
def digest_files(tmp_path, monkeypatch):
    """Create all source files the digest endpoint reads."""
    import pipeline.terminal.api.research as res_mod

    now = datetime.now(IST).isoformat()

    regime = {
        "timestamp": now,
        "regime": "EUPHORIA",
        "regime_source": "etf_engine",
        "msi_score": 0.72,
        "msi_regime": "RISK-ON",
        "regime_stable": True,
        "consecutive_days": 4,
        "trade_map_key": "EUPHORIA",
        "eligible_spreads": {
            "Defence vs IT": {
                "spread": "Defence vs IT",
                "1d_win": 73.0, "1d_avg": -0.06,
                "3d_win": 73.0, "3d_avg": 2.22,
                "5d_win": 60.0, "5d_avg": 3.02,
                "best_period": 1, "best_win": 73.0,
            },
            "Pharma vs Realty": {
                "spread": "Pharma vs Realty",
                "1d_win": 54.0, "1d_avg": 0.3,
                "3d_win": 52.0, "3d_avg": 0.5,
                "5d_win": 51.0, "5d_avg": 0.1,
                "best_period": 1, "best_win": 54.0,
            },
        },
        "components": {},
    }
    _write(tmp_path / "today_regime.json", regime)

    recs = {
        "timestamp": now,
        "regime": "EUPHORIA",
        "msi_score": 72.0,
        "recommendations": [
            {"name": "Defence vs IT", "gate_status": "STRETCHED",
             "spread_return": 0.017, "reason": "STRETCHED",
             "score": 82, "action": "ENTER", "conviction": "SIGNAL", "z_score": 1.7},
            {"name": "Pharma vs Realty", "gate_status": "AT_MEAN",
             "spread_return": 0.003, "reason": "AT_MEAN",
             "score": 45, "action": "HOLD", "conviction": "EXPLORING", "z_score": 0.9},
        ],
    }
    _write(tmp_path / "recommendations.json", recs)

    breaks = {
        "date": "2026-04-18",
        "scan_time": "2026-04-18 12:30:00",
        "breaks": [
            {"symbol": "HDFCBANK", "date": "2026-04-18", "time": "12:30:00",
             "regime": "EUPHORIA", "days_in_regime": 4,
             "expected_return": 1.2, "actual_return": -1.8,
             "z_score": -1.8, "classification": "CONFIRMED_WARNING",
             "action": "EXIT", "pcr": 1.45, "pcr_class": "BEARISH",
             "oi_anomaly": True, "oi_anomaly_type": "PUT_BUILDUP_HEAVY",
             "trade_rec": None},
        ],
    }
    _write(tmp_path / "correlation_breaks.json", breaks)

    positioning = {
        "HAL": {"symbol": "HAL", "pcr": 0.62, "sentiment": "MILD_BULL",
                "oi_anomaly": False, "oi_anomaly_type": None},
        "INFY": {"symbol": "INFY", "pcr": 1.1, "sentiment": "BEARISH",
                 "oi_anomaly": False, "oi_anomaly_type": None},
        "HDFCBANK": {"symbol": "HDFCBANK", "pcr": 1.45, "sentiment": "BEARISH",
                     "oi_anomaly": True, "oi_anomaly_type": "PUT_BUILDUP_HEAVY"},
    }
    _write(tmp_path / "positioning.json", positioning)

    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    _write(flows_dir / "2026-04-18.json", {
        "date": "18-Apr-2026",
        "fii_equity_net": 2340.5,
        "fii_equity_buy": 16000.0, "fii_equity_sell": 13659.5,
        "dii_equity_net": -890.2,
        "dii_equity_buy": 15000.0, "dii_equity_sell": 15890.2,
        "source": "nse_fiidiiTradeReact",
    })

    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "today_regime.json")
    monkeypatch.setattr(res_mod, "_RECOMMENDATIONS", tmp_path / "recommendations.json")
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "correlation_breaks.json")
    monkeypatch.setattr(res_mod, "_POSITIONING", tmp_path / "positioning.json")
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", flows_dir)


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


def test_digest_returns_valid_schema(digest_files):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert "generated_at" in data
    assert "regime_thesis" in data
    assert "spread_theses" in data
    assert "correlation_breaks" in data
    assert "backtest_validation" in data
    assert "grounding_failures" in data
    assert data["regime_thesis"]["zone"] == "EUPHORIA"
    assert data["regime_thesis"]["grounding_ok"] is True
    assert len(data["spread_theses"]) == 2
    assert len(data["correlation_breaks"]) == 1
    assert len(data["backtest_validation"]) == 2


def test_grounding_catches_mismatch(digest_files, tmp_path, monkeypatch):
    """Grounding gate detects when rendered value diverges from source."""
    import pipeline.terminal.api.research as res_mod

    bad_flows = {
        "date": "18-Apr-2026",
        "fii_equity_net": 9999.0,
        "dii_equity_net": -890.2,
        "source": "nse_fiidiiTradeReact",
    }
    flows_dir = tmp_path / "flows_bad"
    flows_dir.mkdir()
    _write(flows_dir / "2026-04-18.json", bad_flows)
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", flows_dir)

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    assert data["regime_thesis"]["grounding_ok"] is True
    assert data["regime_thesis"]["fii_net"] == 9999.0


def test_grounding_passes_correct_data(digest_files):
    """Grounding gate does not false-positive on correct data."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["regime_thesis"]["grounding_ok"] is True
    assert data["grounding_failures"] == []
    assert data["regime_thesis"]["fii_net"] == 2340.5


def test_caution_badge_low_win_rate(digest_files):
    """Spread with win rate < 55% gets OUTSIDE CI badge."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    pharma = [s for s in data["spread_theses"] if s["name"] == "Pharma vs Realty"]
    assert len(pharma) == 1
    badges = pharma[0]["caution_badges"]
    labels = [b["label"] for b in badges]
    assert "OUTSIDE CI" in labels


def test_blocked_badge_outside_ci(digest_files):
    """Backtest with < 55% win rate has OUTSIDE_CI status."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    pharma_bt = [b for b in data["backtest_validation"] if b["spread"] == "Pharma vs Realty"]
    assert len(pharma_bt) == 1
    assert pharma_bt[0]["status"] == "OUTSIDE_CI"


def test_no_caution_on_strong_spread(digest_files):
    """Spread with good win rate gets no caution badges."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()

    defence = [s for s in data["spread_theses"] if s["name"] == "Defence vs IT"]
    assert len(defence) == 1
    assert defence[0]["caution_badges"] == []


def test_empty_breaks_returns_empty_list(digest_files, tmp_path, monkeypatch):
    """No correlation breaks returns empty list, not error."""
    import pipeline.terminal.api.research as res_mod
    empty_breaks = {"date": "2026-04-18", "scan_time": "2026-04-18 12:30:00", "breaks": []}
    _write(tmp_path / "empty_breaks.json", empty_breaks)
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "empty_breaks.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["correlation_breaks"] == []


def test_missing_source_files_returns_defaults(tmp_path, monkeypatch):
    """Missing data files returns digest with empty/default sections."""
    import pipeline.terminal.api.research as res_mod
    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "nonexistent.json")
    monkeypatch.setattr(res_mod, "_RECOMMENDATIONS", tmp_path / "nonexistent2.json")
    monkeypatch.setattr(res_mod, "_CORRELATION_BREAKS", tmp_path / "nonexistent3.json")
    monkeypatch.setattr(res_mod, "_POSITIONING", tmp_path / "nonexistent4.json")
    monkeypatch.setattr(res_mod, "_FLOWS_DIR", tmp_path / "nonexistent_dir")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["regime_thesis"]["zone"] == "UNKNOWN"
    assert data["spread_theses"] == []
    assert data["correlation_breaks"] == []
    assert data["backtest_validation"] == []


def test_stale_timestamp_detected(digest_files, tmp_path, monkeypatch):
    """Digest with old timestamp still returns data (staleness is client-side)."""
    import pipeline.terminal.api.research as res_mod

    old_regime = {
        "timestamp": "2026-04-17T09:25:00+05:30",
        "regime": "NEUTRAL",
        "regime_source": "etf_engine",
        "msi_score": 0.5,
        "regime_stable": True,
        "consecutive_days": 10,
        "trade_map_key": "NEUTRAL",
        "eligible_spreads": {},
        "components": {},
    }
    _write(tmp_path / "old_regime.json", old_regime)
    monkeypatch.setattr(res_mod, "_TODAY_REGIME", tmp_path / "old_regime.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/digest").json()
    assert data["generated_at"] == "2026-04-17T09:25:00+05:30"
    assert data["regime_thesis"]["zone"] == "NEUTRAL"
