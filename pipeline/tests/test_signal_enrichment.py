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


# ---------------------------------------------------------------------------
# Task 2 + 3 Tests
# ---------------------------------------------------------------------------

from pipeline.signal_enrichment import enrich_signal, gate_signal  # noqa: E402


def _make_signal(long_ticker="GAIL", short_ticker="HAL"):
    """Build a minimal signal dict with one long leg and one short leg."""
    return {
        "signal_id": "TEST-001",
        "long_legs": [{"ticker": long_ticker, "weight": 1.0}],
        "short_legs": [{"ticker": short_ticker, "weight": 1.0}],
    }


@pytest.fixture
def all_caches(trust_fixture, breaks_fixture, regime_profile_fixture, oi_bare_fixture, tmp_path):
    """Load all four caches from the fixture files."""
    trust_cache = load_trust_scores(trust_fixture)
    breaks_cache = load_correlation_breaks(breaks_fixture)
    profile_cache = load_regime_profile(regime_profile_fixture)
    oi_cache = load_oi_anomalies(oi_bare_fixture)
    return trust_cache, breaks_cache, profile_cache, oi_cache, trust_fixture, breaks_fixture, regime_profile_fixture, oi_bare_fixture


def test_enrich_signal_attaches_all_four_sources(all_caches):
    trust_cache, breaks_cache, profile_cache, oi_cache, tp, bp, pp, op = all_caches
    signal = _make_signal("GAIL", "HAL")
    enriched = enrich_signal(
        signal, trust_cache, breaks_cache, profile_cache, oi_cache,
        trust_path=tp, breaks_path=bp, profile_path=pp, oi_path=op,
    )
    # Original fields preserved
    assert enriched["signal_id"] == "TEST-001"
    assert enriched["long_legs"] == signal["long_legs"]
    # All four enrichment keys present
    assert "trust_scores" in enriched
    assert "regime_rank" in enriched
    assert "correlation_breaks" in enriched
    assert "oi_anomalies" in enriched
    assert "rigour_trail" in enriched
    # GAIL has trust data; HAL has regime rank data
    assert enriched["trust_scores"]["GAIL"] is not None
    assert enriched["trust_scores"]["GAIL"]["trust_grade"] == "A"
    assert enriched["regime_rank"]["HAL"] is not None
    assert enriched["regime_rank"]["HAL"]["hit_rate"] == pytest.approx(0.50)


def test_enrich_signal_rigour_trail_has_provenance(all_caches):
    trust_cache, breaks_cache, profile_cache, oi_cache, tp, bp, pp, op = all_caches
    signal = _make_signal("GAIL", "HAL")
    enriched = enrich_signal(
        signal, trust_cache, breaks_cache, profile_cache, oi_cache,
        trust_path=tp, breaks_path=bp, profile_path=pp, oi_path=op,
    )
    trail = enriched["rigour_trail"]
    assert "enriched_at" in trail
    # enriched_at must parse as ISO datetime
    from datetime import datetime
    dt = datetime.fromisoformat(trail["enriched_at"].replace("Z", "+00:00"))
    assert dt.year >= 2026
    # Sources block
    assert "sources" in trail
    sources = trail["sources"]
    for key in ("trust", "breaks", "regime_profile", "oi_anomalies"):
        assert key in sources, f"missing source key: {key}"
        src = sources[key]
        assert "path" in src
        assert "exists" in src
        assert "mtime" in src
        assert "size_bytes" in src
    # Files were written so mtime should be non-None
    assert sources["trust"]["mtime"] is not None
    assert sources["trust"]["exists"] is True


def test_gate_short_on_high_trust_name_blocks(all_caches):
    """Shorting an A-grade name should be blocked."""
    trust_cache, breaks_cache, profile_cache, oi_cache, tp, bp, pp, op = all_caches
    # GAIL is grade A — shorting it should block
    signal = _make_signal(long_ticker="HAL", short_ticker="GAIL")
    enriched = enrich_signal(
        signal, trust_cache, breaks_cache, profile_cache, oi_cache,
        trust_path=tp, breaks_path=bp, profile_path=pp, oi_path=op,
    )
    blocked, reason, score = gate_signal(enriched)
    assert blocked is True
    assert reason is not None
    assert "GAIL" in reason


def test_gate_long_on_low_trust_blocks(tmp_path, breaks_fixture, regime_profile_fixture, oi_bare_fixture):
    """Longing a C-grade name should be blocked."""
    # Build a trust cache with a C-grade long ticker
    trust_data = {
        "positions": [
            {"symbol": "BADCO", "side": "LONG", "trust_grade": "C", "trust_score": 40, "thesis": "weak"},
            {"symbol": "GOODCO", "side": "SHORT", "trust_grade": "B", "trust_score": 70, "thesis": "ok"},
        ]
    }
    tp = tmp_path / "trust_c.json"
    tp.write_text(json.dumps(trust_data))
    trust_cache = load_trust_scores(tp)
    breaks_cache = load_correlation_breaks(breaks_fixture)
    profile_cache = load_regime_profile(regime_profile_fixture)
    oi_cache = load_oi_anomalies(oi_bare_fixture)

    signal = _make_signal(long_ticker="BADCO", short_ticker="GOODCO")
    enriched = enrich_signal(
        signal, trust_cache, breaks_cache, profile_cache, oi_cache,
        trust_path=tp, breaks_path=breaks_fixture, profile_path=regime_profile_fixture, oi_path=oi_bare_fixture,
    )
    blocked, reason, score = gate_signal(enriched)
    assert blocked is True
    assert "BADCO" in reason


def test_gate_passes_good_spread(tmp_path):
    """A clean spread with good data should pass, with score > 50."""
    # Build fixtures where long ticker has A trust + good hit_rate + matching break
    trust_data = {
        "positions": [
            {"symbol": "LONGCO", "side": "LONG", "trust_grade": "A+", "trust_score": 92, "thesis": "great"},
            {"symbol": "SHORTCO", "side": "SHORT", "trust_grade": "D", "trust_score": 30, "thesis": "weak"},
        ]
    }
    breaks_data = {
        "breaks": [
            {"symbol": "LONGCO", "z_score": 2.5, "classification": "MOMENTUM", "action": "BUY",
             "expected_return": 2.0, "actual_return": 2.1, "oi_anomaly": True, "trade_rec": "BUY"},
        ]
    }
    profile_data = {
        "stock_profiles": {
            "LONGCO": {
                "summary": {
                    "episode_count": 40, "tradeable_rate": 0.90, "persistence_rate": 0.50,
                    "hit_rate": 0.65, "avg_drift_1d": 0.002
                }
            }
        }
    }
    oi_data = [
        {"symbol": "LONGCO", "anomaly_type": "CALL_BUILDUP", "pcr": 0.8, "sentiment": "BULLISH",
         "oi_change": 500000, "pcr_flip": False}
    ]
    tp = tmp_path / "trust_good.json"
    bp = tmp_path / "breaks_good.json"
    pp = tmp_path / "profile_good.json"
    op = tmp_path / "oi_good.json"
    tp.write_text(json.dumps(trust_data))
    bp.write_text(json.dumps(breaks_data))
    pp.write_text(json.dumps(profile_data))
    op.write_text(json.dumps(oi_data))

    trust_cache = load_trust_scores(tp)
    breaks_cache = load_correlation_breaks(bp)
    profile_cache = load_regime_profile(pp)
    oi_cache = load_oi_anomalies(op)

    signal = _make_signal("LONGCO", "SHORTCO")
    enriched = enrich_signal(
        signal, trust_cache, breaks_cache, profile_cache, oi_cache,
        trust_path=tp, breaks_path=bp, profile_path=pp, oi_path=op,
    )
    blocked, reason, score = gate_signal(enriched)
    assert blocked is False
    assert score > 50


def test_gate_missing_enrichment_does_not_block():
    """When all enrichment is None, gate should fail-open: blocked=False, score=50."""
    signal = {
        "signal_id": "EMPTY-001",
        "long_legs": [{"ticker": "UNKNOWN_A", "weight": 1.0}],
        "short_legs": [{"ticker": "UNKNOWN_B", "weight": 1.0}],
        "trust_scores": {"UNKNOWN_A": None, "UNKNOWN_B": None},
        "regime_rank": {"UNKNOWN_A": None, "UNKNOWN_B": None},
        "correlation_breaks": {"UNKNOWN_A": None, "UNKNOWN_B": None},
        "oi_anomalies": {"UNKNOWN_A": None, "UNKNOWN_B": None},
        "rigour_trail": {"enriched_at": "2026-04-16T10:00:00+00:00", "sources": {}},
    }
    blocked, reason, score = gate_signal(signal)
    assert blocked is False
    assert score == pytest.approx(50.0)
