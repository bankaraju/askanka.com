import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.stock_features import (
    build_stock_features_row,
    stock_feature_names,
)


@pytest.fixture
def stock_bars() -> pd.DataFrame:
    """550-day stock panel, monotone close, constant volume."""
    dates = pd.date_range("2023-03-01", periods=550, freq="D")
    return pd.DataFrame({
        "date": dates,
        "close": np.linspace(100.0, 130.0, 550),
        "volume": np.full(550, 1_000_000.0),
    })


def test_feature_names_match_constants():
    assert stock_feature_names() == tuple(f"stock_{f}" for f in C.STOCK_CONTEXT_FEATURES)


def test_features_are_causal(stock_bars):
    """Mutating row at t must not change features for eval_date=t."""
    eval_date = pd.Timestamp("2024-09-01")
    sector_id = 4
    base = build_stock_features_row(stock_bars, eval_date, sector_id)

    bars_mut = stock_bars.copy()
    bars_mut.loc[bars_mut["date"] == eval_date, "close"] = 99999.0
    bars_mut.loc[bars_mut["date"] == eval_date, "volume"] = 50.0
    mut = build_stock_features_row(bars_mut, eval_date, sector_id)

    pd.testing.assert_series_equal(base, mut)


def test_sector_id_pass_through(stock_bars):
    eval_date = pd.Timestamp("2024-09-01")
    out = build_stock_features_row(stock_bars, eval_date, sector_id=7)
    assert out["stock_sector_id"] == 7


def test_dist_from_52w_high_negative_for_pullback(stock_bars):
    """Inject a recent peak then pullback; dist must be negative."""
    bars = stock_bars.copy()
    bars.loc[bars["date"] == pd.Timestamp("2024-08-15"), "close"] = 200.0
    eval_date = pd.Timestamp("2024-09-01")
    out = build_stock_features_row(bars, eval_date, sector_id=0)
    assert out["stock_dist_from_52w_high_pct"] < 0


@pytest.fixture
def stock_bars_varied() -> pd.DataFrame:
    """550-day panel with varying volume — exercises vol_z_60d and volume_z_20d."""
    n = 550
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "date": pd.date_range("2023-03-01", periods=n, freq="D"),
        "close": np.linspace(100.0, 130.0, n) + rng.normal(0, 0.5, n),  # add small noise so vol > 0
        "volume": rng.uniform(500_000.0, 2_000_000.0, n),
    })


def test_vol_z_60d_is_finite(stock_bars_varied):
    out = build_stock_features_row(stock_bars_varied, pd.Timestamp("2024-09-01"), sector_id=0)
    assert np.isfinite(out["stock_vol_z_60d"])


def test_volume_z_20d_is_finite(stock_bars_varied):
    out = build_stock_features_row(stock_bars_varied, pd.Timestamp("2024-09-01"), sector_id=0)
    assert np.isfinite(out["stock_volume_z_20d"])
