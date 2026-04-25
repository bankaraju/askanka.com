"""Fetcher TDD — uses fake kite session and tmp cache directory."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_shape_audit import fetcher


def _synthetic_minute_bars(trade_date: date, n_bars: int = 375) -> pd.DataFrame:
    """Build a 375-bar synthetic session DataFrame (09:15-15:29)."""
    rows = []
    base = datetime.combine(trade_date, datetime.min.time()).replace(hour=9, minute=15)
    for i in range(n_bars):
        ts = base + pd.Timedelta(minutes=i)
        rows.append({
            "timestamp_ist": ts,
            "open": 100.0 + i * 0.01,
            "high": 100.5 + i * 0.01,
            "low": 99.5 + i * 0.01,
            "close": 100.2 + i * 0.01,
            "volume": 1000,
        })
    return pd.DataFrame(rows)


def test_fetch_returns_cached_parquet_without_calling_kite(tmp_path: Path) -> None:
    trade_date = date(2026, 4, 22)
    cache_path = tmp_path / "TICKERA_20260422.parquet"
    cached = _synthetic_minute_bars(trade_date)
    cached.to_parquet(cache_path, index=False)

    fake_session = MagicMock()
    df = fetcher.fetch_minute_bars(
        ticker="TICKERA",
        trade_date=trade_date,
        bars_dir=tmp_path,
        kite_session=fake_session,
        token_resolver=lambda _t: 12345,
    )

    fake_session.historical_data.assert_not_called()
    assert len(df) == 375
    assert list(df.columns) == ["timestamp_ist", "open", "high", "low", "close", "volume"]


def test_fetch_calls_kite_on_miss_and_writes_parquet(tmp_path: Path) -> None:
    trade_date = date(2026, 4, 22)
    fake_candles = [
        {
            "date": datetime(2026, 4, 22, 9, 15),
            "open": 100.0, "high": 100.5, "low": 99.8, "close": 100.2,
            "volume": 1500,
        },
        {
            "date": datetime(2026, 4, 22, 9, 16),
            "open": 100.2, "high": 100.7, "low": 100.0, "close": 100.4,
            "volume": 1200,
        },
    ]
    fake_session = MagicMock()
    fake_session.historical_data.return_value = fake_candles

    df = fetcher.fetch_minute_bars(
        ticker="NEWTICK",
        trade_date=trade_date,
        bars_dir=tmp_path,
        kite_session=fake_session,
        token_resolver=lambda _t: 99999,
    )

    fake_session.historical_data.assert_called_once()
    call_kwargs = fake_session.historical_data.call_args.kwargs
    assert call_kwargs["instrument_token"] == 99999
    assert call_kwargs["interval"] == "minute"
    assert call_kwargs["from_date"] == "2026-04-22 09:15:00"
    assert call_kwargs["to_date"] == "2026-04-22 15:35:00"

    assert len(df) == 2
    assert df.iloc[0]["open"] == pytest.approx(100.0)

    cache_file = tmp_path / "NEWTICK_20260422.parquet"
    assert cache_file.exists()
    reread = pd.read_parquet(cache_file)
    assert len(reread) == 2


def test_fetch_raises_when_token_unresolvable(tmp_path: Path) -> None:
    fake_session = MagicMock()
    with pytest.raises(ValueError, match="No instrument token"):
        fetcher.fetch_minute_bars(
            ticker="UNKNOWN",
            trade_date=date(2026, 4, 22),
            bars_dir=tmp_path,
            kite_session=fake_session,
            token_resolver=lambda _t: None,
        )
