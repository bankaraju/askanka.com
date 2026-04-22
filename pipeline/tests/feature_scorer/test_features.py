import pandas as pd
import numpy as np
import pytest


@pytest.fixture
def prices_fixture():
    """30 trading days of synthetic price data."""
    dates = pd.date_range("2026-03-01", periods=30, freq="B")
    return pd.DataFrame({
        "date": dates,
        "close": np.linspace(100, 110, 30),  # +10% over 30 days
    })


@pytest.fixture
def sector_fixture():
    dates = pd.date_range("2026-03-01", periods=30, freq="B")
    return pd.DataFrame({
        "date": dates,
        "close": np.linspace(1000, 1050, 30),  # +5% over 30 days
    })


def test_sector_5d_return(sector_fixture):
    from pipeline.feature_scorer.features import sector_n_day_return
    v = sector_n_day_return(sector_fixture, as_of="2026-03-16", n_days=5)
    assert v is not None
    assert 0.0 < v < 0.02


def test_ticker_3d_momentum(prices_fixture):
    from pipeline.feature_scorer.features import ticker_n_day_momentum
    v = ticker_n_day_momentum(prices_fixture, as_of="2026-03-16", n_days=3)
    assert 0.0 < v < 0.02


def test_ticker_relative_strength(prices_fixture, sector_fixture):
    from pipeline.feature_scorer.features import ticker_rs_vs_sector
    v = ticker_rs_vs_sector(prices_fixture, sector_fixture, as_of="2026-03-16", n_days=10)
    assert v > 0


def test_realized_vol_60d(prices_fixture):
    from pipeline.feature_scorer.features import realized_vol
    v = realized_vol(prices_fixture, as_of="2026-03-16", n_days=60)
    assert v is None


def test_regime_one_hot():
    from pipeline.feature_scorer.features import regime_one_hot
    assert regime_one_hot("NEUTRAL") == [0, 1, 0, 0, 0]
    assert regime_one_hot("RISK-OFF") == [1, 0, 0, 0, 0]
    assert regime_one_hot("UNKNOWN") == [0, 0, 0, 0, 0]


def test_dte_bucket():
    from pipeline.feature_scorer.features import dte_bucket
    assert dte_bucket(3) == [1, 0, 0]
    assert dte_bucket(10) == [0, 1, 0]
    assert dte_bucket(25) == [0, 0, 1]


def test_trust_grade_ordinal():
    from pipeline.feature_scorer.features import trust_grade_ordinal
    assert trust_grade_ordinal("A") == 5
    assert trust_grade_ordinal("F") == 1
    assert trust_grade_ordinal(None) == 0
    assert trust_grade_ordinal("INSUFFICIENT_DATA") == 0


def test_feature_vector_happy_path(prices_fixture, sector_fixture):
    from pipeline.feature_scorer.features import build_feature_vector
    inputs = {
        "prices": prices_fixture,
        "sector": sector_fixture,
        "as_of": "2026-03-16",
        "regime": "NEUTRAL",
        "dte": 5,
        "trust_grade": "B",
        "nifty_breadth_5d": 0.6,
        "pcr_z_score": None,
    }
    v = build_feature_vector(**inputs)
    expected_keys = {
        "sector_5d_return", "sector_20d_return", "ticker_rs_10d",
        "ticker_3d_momentum", "nifty_breadth_5d",
        "regime_RISK-OFF", "regime_NEUTRAL", "regime_RISK-ON",
        "regime_EUPHORIA", "regime_CRISIS",
        "pcr_z_score",
        "dte_0_5", "dte_6_15", "dte_16_plus",
        "trust_grade_ordinal", "realized_vol_60d",
    }
    assert set(v.keys()) == expected_keys
    assert v["regime_NEUTRAL"] == 1
    assert v["pcr_z_score"] == 0.0
    assert v["realized_vol_60d"] is None


def test_feature_vector_missing_sector_raises():
    from pipeline.feature_scorer.features import build_feature_vector
    with pytest.raises(ValueError, match="sector"):
        build_feature_vector(prices=None, sector=None, as_of="2026-03-16",
                             regime="NEUTRAL", dte=5, trust_grade="A",
                             nifty_breadth_5d=0.5, pcr_z_score=None)
