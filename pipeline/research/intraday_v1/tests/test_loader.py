"""Tests loader.py — Kite 1-min paged fetcher + parquet cache."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.research.intraday_v1 import loader


IST = timezone(timedelta(hours=5, minutes=30))


def _fake_kite_response(start: datetime, n_minutes: int):
    """Generate a fake 1-min OHLCV bar list."""
    rows = []
    for i in range(n_minutes):
        ts = start + timedelta(minutes=i)
        rows.append({
            "date": ts,
            "open": 100.0 + i * 0.1,
            "high": 100.5 + i * 0.1,
            "low": 99.5 + i * 0.1,
            "close": 100.2 + i * 0.1,
            "volume": 1000 + i,
        })
    return rows


def _make_fake_kite(historical_rows):
    """Build a MagicMock that mimics the _KiteAdapter interface."""
    fake = MagicMock()
    fake.resolve_token.return_value = 12345
    fake.historical_data.return_value = historical_rows
    return fake


def test_paged_fetch_concatenates_pages(tmp_path, monkeypatch):
    fake_kite = _make_fake_kite(_fake_kite_response(
        datetime(2026, 4, 25, 9, 15, tzinfo=IST), 100
    ))
    monkeypatch.setattr(loader, "_kite_client", lambda: fake_kite)
    monkeypatch.setattr(loader, "CACHE_DIR", tmp_path)

    df = loader.fetch_1min("RELIANCE", days=7)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 100
    assert {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns)


def test_paged_fetch_makes_one_call_per_window(tmp_path, monkeypatch):
    """A 21-day request must invoke historical_data three times (3×7-day pages)."""
    fake_kite = _make_fake_kite(_fake_kite_response(
        datetime(2026, 4, 25, 9, 15, tzinfo=IST), 10
    ))
    monkeypatch.setattr(loader, "_kite_client", lambda: fake_kite)
    monkeypatch.setattr(loader, "CACHE_DIR", tmp_path)

    loader.fetch_1min("RELIANCE", days=21)
    # 21 / PAGE_DAYS(7) = exactly 3 pages
    assert fake_kite.historical_data.call_count == 3


def test_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "CACHE_DIR", tmp_path)
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-04-25 09:15", "2026-04-25 09:16"]).tz_localize("Asia/Kolkata"),
        "open":   [100.0, 100.1],
        "high":   [100.5, 100.6],
        "low":    [99.5, 99.6],
        "close":  [100.2, 100.3],
        "volume": [1000, 1100],
    })
    loader.write_cache("RELIANCE", df)
    df_read = loader.read_cache("RELIANCE")
    assert len(df_read) == 2
    assert list(df_read.columns) == list(df.columns)


def test_delta_refresh_only_fetches_new_bars(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "CACHE_DIR", tmp_path)

    # Seed cache with one bar
    df_old = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-04-25 09:15"]).tz_localize("Asia/Kolkata"),
        "open":   [100.0], "high": [100.5], "low": [99.5],
        "close":  [100.2], "volume": [1000],
    })
    loader.write_cache("RELIANCE", df_old)

    fake_kite = _make_fake_kite(_fake_kite_response(
        datetime(2026, 4, 25, 9, 16, tzinfo=IST), 5
    ))
    monkeypatch.setattr(loader, "_kite_client", lambda: fake_kite)

    df = loader.refresh_cache("RELIANCE", days=60)
    assert len(df) == 6  # 1 old + 5 new
    # Confirm fetch was called exactly once (delta path, not full re-fetch)
    assert fake_kite.historical_data.call_count == 1


def test_aborts_when_kite_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, "CACHE_DIR", tmp_path)
    fake_kite = _make_fake_kite([])
    monkeypatch.setattr(loader, "_kite_client", lambda: fake_kite)

    with pytest.raises(loader.LoaderError, match="empty response"):
        loader.fetch_1min("UNKNOWN", days=7)
