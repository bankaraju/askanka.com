"""Per-stock 23-column feature matrix builder for H-2026-05-04.

Pre-PCA layout (43 cols): 30 ETF 1d returns + 4 IND macro + 6 stock TA + 3 DOW.
Post-PCA layout (23 cols): K_ETF=10 PCs + 4 IND macro + 6 stock TA + 3 DOW.

PCA reduction is applied separately by pca_model.py — this file produces the
pre-PCA matrix only.

PIT contract: every column at row i depends only on data <= row i. Period.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_stock_ta(bars: pd.DataFrame, sector_ret_5d: pd.Series) -> pd.DataFrame:
    """6 stock-specific TA features. bars must have OHLCV columns."""
    out = pd.DataFrame(index=bars.index)
    delta = bars["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - 100 / (1 + rs)

    prev_close = bars["Close"].shift(1)
    tr = pd.concat(
        [(bars["High"] - bars["Low"]),
         (bars["High"] - prev_close).abs(),
         (bars["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr_14_pct"] = tr.rolling(14).mean() / bars["Close"]

    ema50 = bars["Close"].ewm(span=50, adjust=False).mean()
    out["dist_50ema_pct"] = (bars["Close"] - ema50) / ema50

    vol_mean = bars["Volume"].rolling(20).mean()
    vol_std = bars["Volume"].rolling(20).std()
    out["vol_zscore_20"] = (bars["Volume"] - vol_mean) / vol_std.replace(0, np.nan)

    out["range_pct_today"] = (bars["High"] - bars["Low"]) / bars["Close"]
    out["own_sector_ret_5d"] = sector_ret_5d.reindex(bars.index)
    return out[["own_sector_ret_5d", "atr_14_pct", "rsi_14", "dist_50ema_pct", "vol_zscore_20", "range_pct_today"]]


def build_indian_macro(
    nifty_near_month_close: pd.Series,
    india_vix: pd.Series,
    nifty_emphasis_factor: float = 1.5,
) -> pd.DataFrame:
    """4 Indian macro features. Nifty cols scaled by sqrt(emphasis_factor) at fit AND inference."""
    scale = np.sqrt(nifty_emphasis_factor)
    out = pd.DataFrame(index=nifty_near_month_close.index)
    out["nifty_near_month_ret_1d"] = nifty_near_month_close.pct_change(1) * scale
    out["nifty_near_month_ret_5d"] = nifty_near_month_close.pct_change(5) * scale
    out["india_vix_level"] = india_vix.reindex(nifty_near_month_close.index)
    out["india_vix_chg_5d"] = np.log(india_vix.reindex(nifty_near_month_close.index)).diff(5)
    return out


def build_dow(index: pd.DatetimeIndex) -> pd.DataFrame:
    """3 DOW dummies (Mon, Tue, Wed) — Thu/Fri reference."""
    out = pd.DataFrame(index=index)
    wd = index.weekday
    out["dow_mon"] = (wd == 0).astype(int)
    out["dow_tue"] = (wd == 1).astype(int)
    out["dow_wed"] = (wd == 2).astype(int)
    return out


def build_full_feature_matrix(
    *,
    bars: pd.DataFrame,
    etf_returns_1d: pd.DataFrame,
    nifty_near_month_close: pd.Series,
    india_vix: pd.Series,
    sector_ret_5d: pd.Series,
    nifty_emphasis_factor: float = 1.5,
) -> pd.DataFrame:
    """Pre-PCA 43-column matrix. PCA reduction applied later by pca_model.py."""
    ta = build_stock_ta(bars, sector_ret_5d)
    macro = build_indian_macro(nifty_near_month_close, india_vix, nifty_emphasis_factor)
    dow = build_dow(bars.index)
    etf = etf_returns_1d.reindex(bars.index)
    X = pd.concat([etf, macro, ta, dow], axis=1).dropna()
    return X
