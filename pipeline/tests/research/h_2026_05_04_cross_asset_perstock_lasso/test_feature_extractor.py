import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.feature_extractor import (
    build_indian_macro,
    build_stock_ta,
    build_dow,
    build_full_feature_matrix,
)


def _synthetic_bars(n_days=300, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    close = 100 * (1 + rng.normal(0, 0.01, n_days)).cumprod()
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))
    open_ = close * (1 + rng.normal(0, 0.005, n_days))
    vol = rng.integers(1_000_000, 5_000_000, n_days)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=dates)


def test_stock_ta_has_six_columns():
    bars = _synthetic_bars()
    ta = build_stock_ta(bars, sector_ret_5d=pd.Series(0.01, index=bars.index))
    expected = {"own_sector_ret_5d", "atr_14_pct", "rsi_14", "dist_50ema_pct", "vol_zscore_20", "range_pct_today"}
    assert set(ta.columns) == expected


def test_stock_ta_no_lookahead():
    """rsi_14 at row i must use only data through bar i (no future)."""
    bars = _synthetic_bars()
    ta_full = build_stock_ta(bars, sector_ret_5d=pd.Series(0.01, index=bars.index))
    ta_truncated = build_stock_ta(bars.iloc[:200], sector_ret_5d=pd.Series(0.01, index=bars.index[:200]))
    # rsi_14 at row 100 must equal whether full or truncated
    assert ta_full["rsi_14"].iloc[100] == pytest.approx(ta_truncated["rsi_14"].iloc[100], rel=1e-9)


def test_dow_has_three_columns_and_one_hot():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")  # Mon-Fri
    dow = build_dow(idx)
    assert set(dow.columns) == {"dow_mon", "dow_tue", "dow_wed"}
    # Monday: dow_mon=1, others 0
    monday = dow[idx.weekday == 0].iloc[0]
    assert monday["dow_mon"] == 1 and monday["dow_tue"] == 0 and monday["dow_wed"] == 0


def test_indian_macro_has_four_columns_and_emphasis():
    nifty_fut = pd.Series(np.linspace(20000, 22000, 100), index=pd.date_range("2024-01-01", periods=100, freq="B"))
    vix = pd.Series(np.linspace(15, 18, 100), index=nifty_fut.index)
    macro = build_indian_macro(nifty_fut, vix, nifty_emphasis_factor=1.5)
    assert set(macro.columns) == {"nifty_near_month_ret_1d", "nifty_near_month_ret_5d", "india_vix_level", "india_vix_chg_5d"}
    # Emphasis is applied to nifty_*: scaled by sqrt(1.5)
    raw_macro = build_indian_macro(nifty_fut, vix, nifty_emphasis_factor=1.0)
    assert macro["nifty_near_month_ret_1d"].iloc[10] == pytest.approx(
        raw_macro["nifty_near_month_ret_1d"].iloc[10] * np.sqrt(1.5), rel=1e-9
    )
    # india_vix_level is NOT scaled
    assert macro["india_vix_level"].iloc[10] == pytest.approx(raw_macro["india_vix_level"].iloc[10], rel=1e-9)


def test_full_matrix_has_pre_pca_columns():
    """Pre-PCA: 30 ETFs (1d) + 4 IND macro + 6 TA + 3 DOW = 43 columns. PCA happens later."""
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    bars = _synthetic_bars(n_days=n)
    panel_etf_1d = pd.DataFrame(
        np.random.default_rng(1).normal(0, 0.01, (n, 30)),
        columns=[f"etf{i}" for i in range(30)],
        index=dates,
    )
    nifty_fut = pd.Series(np.linspace(20000, 22000, n), index=dates)
    vix = pd.Series(np.linspace(15, 18, n), index=dates)
    sector_ret = pd.Series(np.random.default_rng(2).normal(0, 0.005, n), index=dates)

    X = build_full_feature_matrix(
        bars=bars,
        etf_returns_1d=panel_etf_1d,
        nifty_near_month_close=nifty_fut,
        india_vix=vix,
        sector_ret_5d=sector_ret,
        nifty_emphasis_factor=1.5,
    )
    assert X.shape[1] == 43  # pre-PCA
    # No NaN in last 100 rows (warmup absorbed)
    assert X.iloc[-100:].isna().sum().sum() == 0
