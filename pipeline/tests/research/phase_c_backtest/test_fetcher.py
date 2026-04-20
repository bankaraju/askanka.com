from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch
from pipeline.research.phase_c_backtest import fetcher


def _fake_kite_response(symbol: str, interval: str, days: int):
    if interval == "day":
        dates = pd.bdate_range(end="2026-04-19", periods=days)
        return [
            {"date": d.strftime("%Y-%m-%d"), "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 10000, "source": "kite"}
            for d in dates
        ]
    # minute
    start = pd.Timestamp("2026-04-18 09:15")
    end = pd.Timestamp("2026-04-18 15:30")
    minutes = pd.date_range(start=start, end=end, freq="1min")
    return [
        {"date": m.strftime("%Y-%m-%d %H:%M:%S"), "open": 100.0, "high": 100.1,
         "low": 99.9, "close": 100.05, "volume": 1000, "source": "kite"}
        for m in minutes
    ]


def test_fetch_daily_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "_DAILY_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.fetcher._kite_fetch", side_effect=_fake_kite_response):
        df = fetcher.fetch_daily("RELIANCE", days=30)
    cache_file = tmp_path / "RELIANCE.parquet"
    assert cache_file.is_file()
    assert isinstance(df, pd.DataFrame)
    assert {"date", "open", "high", "low", "close", "volume"}.issubset(df.columns)
    assert len(df) == 30


def test_fetch_daily_uses_cache_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "_DAILY_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.fetcher._kite_fetch", side_effect=_fake_kite_response) as m:
        fetcher.fetch_daily("RELIANCE", days=30)
        fetcher.fetch_daily("RELIANCE", days=30)  # second call
    assert m.call_count == 1, "second call should hit cache, not Kite"


def test_fetch_minute_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "_MINUTE_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.fetcher._kite_fetch", side_effect=_fake_kite_response):
        df = fetcher.fetch_minute("RELIANCE", trade_date="2026-04-18")
    cache_file = tmp_path / "RELIANCE_2026-04-18.parquet"
    assert cache_file.is_file()
    assert len(df) > 100  # full trading day of 1-min bars


def test_fetch_daily_returns_pandas_with_datetime_index(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "_DAILY_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.fetcher._kite_fetch", side_effect=_fake_kite_response):
        df = fetcher.fetch_daily("RELIANCE", days=30)
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
