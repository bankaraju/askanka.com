"""Unit tests for the shared yfinance download wrapper.

All tests monkeypatch yf.download so they run offline and deterministically.
"""
from __future__ import annotations

import sys
import types

import pandas as pd
import pytest


@pytest.fixture
def fake_yf(monkeypatch):
    """Provide a patchable yfinance stub in sys.modules."""
    mod = types.ModuleType("yfinance")
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return mod


def _make_ohlcv(ticker: str, n: int = 3) -> pd.DataFrame:
    """Build a MultiIndex-columns frame like yfinance returns for single-ticker."""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    fields = ["Open", "High", "Low", "Close", "Volume"]
    cols = pd.MultiIndex.from_product([fields, [ticker]])
    vals = [[i + 1.0, i + 2.0, i + 0.5, i + 1.5, 1000 * (i + 1)] for i in range(n)]
    df = pd.DataFrame(vals, index=pd.Index(dates, name="Date"), columns=cols)
    return df


def test_happy_path_returns_6_col_lowercase(fake_yf):
    from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv

    fake_yf.download = lambda *a, **kw: _make_ohlcv("EWZ", n=3)
    out = download_ohlcv("EWZ", "2024-01-01", "2024-01-05")
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(out) == 3
    assert out["close"].notna().all()
    # crucial: high != close (no fabrication)
    assert (out["high"] != out["close"]).all()


def test_empty_raw_returns_empty(fake_yf):
    from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv

    fake_yf.download = lambda *a, **kw: pd.DataFrame()
    out = download_ohlcv("EWZ", "2024-01-01", "2024-01-05")
    assert out.empty


def test_missing_column_returns_empty(fake_yf):
    from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv

    # return frame with only Close (no Open/High/Low/Volume) -- should fail out
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    cols = pd.MultiIndex.from_product([["Close"], ["EWZ"]])
    raw = pd.DataFrame([[100.0], [101.0]], index=dates, columns=cols)
    fake_yf.download = lambda *a, **kw: raw
    out = download_ohlcv("EWZ", "2024-01-01", "2024-01-05")
    assert out.empty


def test_download_exception_returns_empty(fake_yf):
    from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv

    def boom(*a, **kw):
        raise ConnectionError("network down")

    fake_yf.download = boom
    out = download_ohlcv("EWZ", "2024-01-01", "2024-01-05")
    assert out.empty


def test_flat_columns_not_multiindex(fake_yf):
    from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv

    # Some yfinance versions return flat columns for single-ticker
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    raw = pd.DataFrame({
        "Open": [1.0, 2.0], "High": [1.5, 2.5], "Low": [0.5, 1.5],
        "Close": [1.2, 2.2], "Volume": [100, 200],
    }, index=pd.Index(dates, name="Date"))
    fake_yf.download = lambda *a, **kw: raw
    out = download_ohlcv("EWZ", "2024-01-01", "2024-01-05")
    assert len(out) == 2
    assert out["high"].iloc[0] == 1.5  # real high, not close
