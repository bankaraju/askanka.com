"""
Tests for pipeline/signal_enrichment.py — Task 1: 4 rigour data loaders.
Run: pytest pipeline/tests/test_signal_enrichment.py -v
"""
import json
import pytest
from pathlib import Path

from pipeline.signal_enrichment import (
    load_trust_scores,
    load_correlation_breaks,
    load_regime_profile,
    load_oi_anomalies,
    get_trust,
    get_break,
    get_rank,
    get_oi,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def trust_fixture(tmp_path):
    data = {
        "regime": "NEUTRAL",
        "positions": [
            {
                "symbol": "GAIL",
                "side": "LONG",
                "trust_grade": "A",
                "trust_score": 85,
                "thesis": "Direct oil/coal price beneficiaries.",
            },
            {
                "symbol": "HAL",
                "side": "SHORT",
                "trust_grade": "B",
                "trust_score": 72,
                "thesis": "Defence capex tailwind.",
            },
        ],
    }
    p = tmp_path / "model_portfolio.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def breaks_fixture(tmp_path):
    data = {
        "date": "2026-04-16",
        "breaks": [
            {
                "symbol": "PIIND",
                "z_score": -2.0,
                "classification": "POSSIBLE_OPPORTUNITY",
                "action": "HOLD",
                "expected_return": 1.52,
                "actual_return": 0.47,
                "oi_anomaly": False,
                "trade_rec": None,
            }
        ],
    }
    p = tmp_path / "correlation_breaks.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def regime_profile_fixture(tmp_path):
    data = {
        "stock_profiles": {
            "HAL": {
                "summary": {
                    "episode_count": 35,
                    "tradeable_rate": 0.94,
                    "persistence_rate": 0.38,
                    "hit_rate": 0.50,
                    "avg_drift_1d": 0.00093,
                }
            }
        }
    }
    p = tmp_path / "reverse_regime_profile.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def oi_bare_fixture(tmp_path):
    data = [
        {
            "symbol": "AMBUJACEM",
            "timestamp": "2026-04-15T09:25:13+0530",
            "ltp": 450.4,
            "call_oi": 4341750,
            "put_oi": 2047500,
            "pcr": 0.4716,
            "sentiment": "BEARISH",
            "oi_change": -1622250,
            "oi_anomaly": True,
            "pcr_flip": False,
            "anomaly_type": "OI_SPIKE",
        }
    ]
    p = tmp_path / "oi_anomalies.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def oi_wrapped_fixture(tmp_path):
    data = {
        "anomalies": [
            {
                "symbol": "BPCL",
                "timestamp": "2026-04-15T09:25:13+0530",
                "ltp": 303.55,
                "pcr": 0.7166,
                "sentiment": "NEUTRAL",
                "oi_change": 3090875,
                "oi_anomaly": True,
                "pcr_flip": False,
                "anomaly_type": "OI_SPIKE",
            }
        ]
    }
    p = tmp_path / "oi_anomalies_wrapped.json"
    p.write_text(json.dumps(data))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_trust_scores_returns_dict_by_symbol(trust_fixture):
    result = load_trust_scores(trust_fixture)
    assert "GAIL" in result
    assert "HAL" in result
    gail = result["GAIL"]
    assert gail["trust_grade"] == "A"
    assert gail["trust_score"] == 85
    assert gail["opus_side"] == "LONG"
    assert "Direct oil/coal" in gail["thesis"]


def test_load_correlation_breaks(breaks_fixture):
    result = load_correlation_breaks(breaks_fixture)
    assert "PIIND" in result
    piind = result["PIIND"]
    assert piind["classification"] == "POSSIBLE_OPPORTUNITY"
    assert piind["z_score"] == pytest.approx(-2.0)
    assert piind["action"] == "HOLD"
    assert piind["expected_return"] == pytest.approx(1.52)
    assert piind["actual_return"] == pytest.approx(0.47)
    assert piind["oi_anomaly"] is False
    assert piind["trade_rec"] is None


def test_load_regime_profile(regime_profile_fixture):
    result = load_regime_profile(regime_profile_fixture)
    assert "HAL" in result
    hal = result["HAL"]
    assert hal["hit_rate"] == pytest.approx(0.50)
    assert hal["tradeable_rate"] == pytest.approx(0.94)
    assert hal["episode_count"] == 35
    assert hal["persistence_rate"] == pytest.approx(0.38)
    assert hal["avg_drift_1d"] == pytest.approx(0.00093)


def test_load_oi_anomalies(oi_bare_fixture):
    """Bare list format."""
    result = load_oi_anomalies(oi_bare_fixture)
    assert "AMBUJACEM" in result
    amb = result["AMBUJACEM"]
    assert amb["anomaly_type"] == "OI_SPIKE"
    assert amb["pcr"] == pytest.approx(0.4716)
    assert amb["sentiment"] == "BEARISH"
    assert amb["oi_change"] == -1622250
    assert amb["pcr_flip"] is False


def test_load_oi_anomalies_wrapped(oi_wrapped_fixture):
    """Dict-wrapped {"anomalies": [...]} format."""
    result = load_oi_anomalies(oi_wrapped_fixture)
    assert "BPCL" in result
    bpcl = result["BPCL"]
    assert bpcl["anomaly_type"] == "OI_SPIKE"
    assert bpcl["sentiment"] == "NEUTRAL"


def test_get_trust_returns_none_for_missing(trust_fixture):
    cache = load_trust_scores(trust_fixture)
    assert get_trust("UNKNOWN_TICKER", cache) is None
    # Known ticker still works
    assert get_trust("GAIL", cache) is not None


def test_loaders_return_empty_dict_on_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert load_trust_scores(missing) == {}
    assert load_correlation_breaks(missing) == {}
    assert load_regime_profile(missing) == {}
    assert load_oi_anomalies(missing) == {}


def test_loaders_return_empty_dict_on_corrupt_file(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("this is not valid json {{{")
    assert load_trust_scores(corrupt) == {}
    assert load_correlation_breaks(corrupt) == {}
    assert load_regime_profile(corrupt) == {}
    assert load_oi_anomalies(corrupt) == {}


def test_get_break_returns_none_for_missing(breaks_fixture):
    cache = load_correlation_breaks(breaks_fixture)
    assert get_break("NOTREAL", cache) is None
    assert get_break("PIIND", cache) is not None


def test_get_rank_returns_none_for_missing(regime_profile_fixture):
    cache = load_regime_profile(regime_profile_fixture)
    assert get_rank("NOTREAL", cache) is None
    assert get_rank("HAL", cache) is not None


def test_get_oi_returns_none_for_missing(oi_bare_fixture):
    cache = load_oi_anomalies(oi_bare_fixture)
    assert get_oi("NOTREAL", cache) is None
    assert get_oi("AMBUJACEM", cache) is not None
