"""Tests for Kite minute-bar backfill."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.kite_backfill import (
    fetch_minute_bars,
    BackfillFailure,
)


def _kite_response_factory():
    """Mock Kite response for one ticker, two minutes."""
    return [
        {"date": pd.Timestamp("2026-04-23 09:15:00+0530"), "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 1000},
        {"date": pd.Timestamp("2026-04-23 09:16:00+0530"), "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1500},
    ]


def test_fetch_minute_bars_returns_dataframe() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {"NSE:RELIANCE": {"instrument_token": 738561}}
    kite.historical_data.return_value = _kite_response_factory()
    df = fetch_minute_bars(kite, "RELIANCE", date(2026, 4, 23), date(2026, 4, 23))
    assert len(df) == 2
    assert set(df.columns) >= {"ticker", "trade_date", "timestamp", "open", "high", "low", "close", "volume"}
    assert (df["ticker"] == "RELIANCE").all()


def test_fetch_minute_bars_raises_on_empty_response() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {"NSE:GHOST": {"instrument_token": 999999}}
    kite.historical_data.return_value = []
    with pytest.raises(BackfillFailure, match="empty"):
        fetch_minute_bars(kite, "GHOST", date(2026, 4, 23), date(2026, 4, 23))


def test_fetch_minute_bars_raises_on_unknown_ticker() -> None:
    kite = MagicMock()
    kite.ltp.return_value = {}
    with pytest.raises(BackfillFailure, match="instrument_token"):
        fetch_minute_bars(kite, "UNKNOWN", date(2026, 4, 23), date(2026, 4, 23))
