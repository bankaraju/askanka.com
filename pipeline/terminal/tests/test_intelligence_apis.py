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
                 {"symbol": "HAL", "sector_grade": "A", "composite_score": 85, "grade_reason": "Strong defence play"},
                 {"symbol": "TCS", "sector_grade": "B+", "composite_score": 72, "grade_reason": "IT bellwether"},
             ]}
    f = tmp_path / "trust.json"
    f.write_text(json.dumps(trust))
    monkeypatch.setattr(ts_mod, "_V2_FILE", f)
    monkeypatch.setattr(ts_mod, "_V1_FILE", f)


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
    assert data["sector_grade"] == "A"
    assert data["composite_score"] == 85


def test_trust_score_missing():
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/trust-scores/NONEXISTENT").json()
    assert data["sector_grade"] == "?"


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


# ---------------------------------------------------------------------------
# /api/research/karpathy-v1 — H-2026-04-29-ta-karpathy-v1 holdout ledger
# ---------------------------------------------------------------------------

def _write_karp_csv(path, rows):
    import csv as _csv
    cols = [
        "signal_id", "ticker", "date", "direction", "regime",
        "p_long", "p_short", "side", "entry_time", "entry_px",
        "atr_14", "stop_px", "exit_time", "exit_px", "exit_reason",
        "pnl_pct", "status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def test_karpathy_v1_empty(tmp_path, monkeypatch):
    """Endpoint returns empty rows + null aggregates when no ledger present."""
    import pipeline.terminal.api.research as res_mod
    monkeypatch.setattr(res_mod, "_KARP_LEDGER", tmp_path / "missing.csv")
    monkeypatch.setattr(res_mod, "_KARP_TEST_LEDGER", tmp_path / "missing_test.csv")
    monkeypatch.setattr(res_mod, "_KARP_PREDICTIONS", tmp_path / "missing_pred.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/karpathy-v1").json()
    assert data["engine_label"] == "ta_karpathy_v1"
    assert data["spec_id"] == "H-2026-04-29-ta-karpathy-v1"
    assert data["holdout_window"] == ["2026-04-29", "2026-05-28"]
    assert data["rows"] == []
    assert data["summary"]["n_open"] == 0
    assert data["summary"]["n_closed"] == 0
    assert data["summary"]["win_rate_pct"] is None
    assert data["summary"]["avg_pnl_pct"] is None


def test_karpathy_v1_real_and_test_rows(tmp_path, monkeypatch):
    """Real + test rows merge; is_test flag propagates; summary aggregates correctly."""
    import pipeline.terminal.api.research as res_mod

    real_rows = [
        {"signal_id": "KARP-2026-04-29-RELIANCE-LONG", "ticker": "RELIANCE",
         "date": "2026-04-29", "direction": "long", "regime": "NEUTRAL",
         "p_long": "0.6234", "p_short": "0.3766", "side": "LONG",
         "entry_time": "2026-04-29T09:15:00+05:30", "entry_px": "1380.50",
         "atr_14": "20.0", "stop_px": "1340.50",
         "exit_time": "2026-04-29T15:25:00+05:30", "exit_px": "1395.00",
         "exit_reason": "TIME_STOP", "pnl_pct": "1.0500", "status": "CLOSED"},
        {"signal_id": "KARP-2026-04-30-INFY-LONG", "ticker": "INFY",
         "date": "2026-04-30", "direction": "long", "regime": "NEUTRAL",
         "p_long": "0.5500", "p_short": "0.4500", "side": "LONG",
         "entry_time": "2026-04-30T09:15:00+05:30", "entry_px": "1100.00",
         "atr_14": "12.0", "stop_px": "1076.00",
         "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN"},
    ]
    test_rows = [
        {"signal_id": "TEST-2026-04-28-TCS-SHORT", "ticker": "TCS",
         "date": "2026-04-28", "direction": "short", "regime": "NEUTRAL",
         "p_long": "0.4000", "p_short": "0.6000", "side": "SHORT",
         "entry_time": "2026-04-28T09:15:00+05:30", "entry_px": "2400.00",
         "atr_14": "30.0", "stop_px": "2460.00",
         "exit_time": "2026-04-28T15:25:00+05:30", "exit_px": "2380.00",
         "exit_reason": "TIME_STOP", "pnl_pct": "0.8333", "status": "CLOSED"},
    ]
    real_path = tmp_path / "recommendations.csv"
    test_path = tmp_path / "recommendations_test.csv"
    _write_karp_csv(real_path, real_rows)
    _write_karp_csv(test_path, test_rows)

    monkeypatch.setattr(res_mod, "_KARP_LEDGER", real_path)
    monkeypatch.setattr(res_mod, "_KARP_TEST_LEDGER", test_path)
    monkeypatch.setattr(res_mod, "_KARP_PREDICTIONS", tmp_path / "missing_pred.json")

    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/research/karpathy-v1").json()
    assert len(data["rows"]) == 3
    by_id = {r["signal_id"]: r for r in data["rows"]}
    assert by_id["KARP-2026-04-29-RELIANCE-LONG"]["is_test"] is False
    assert by_id["TEST-2026-04-28-TCS-SHORT"]["is_test"] is True
    assert by_id["KARP-2026-04-29-RELIANCE-LONG"]["entry_px"] == 1380.50
    assert by_id["KARP-2026-04-29-RELIANCE-LONG"]["pnl_pct"] == 1.05

    s = data["summary"]
    assert s["n_open"] == 1
    assert s["n_closed"] == 2
    assert s["n_test"] == 1
    assert s["wins"] == 2  # RELIANCE +1.05, TCS +0.8333
    assert s["win_rate_pct"] == 100.0
    assert abs(s["avg_pnl_pct"] - (1.05 + 0.8333) / 2) < 1e-3
