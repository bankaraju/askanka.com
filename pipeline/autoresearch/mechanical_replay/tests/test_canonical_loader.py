"""TDD for canonical_loader — wraps canonical_fno_research_v1 + daily CSVs + sectoral CSVs."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import canonical_loader, constants as C


@pytest.fixture(scope="module")
def loader():
    return canonical_loader.CanonicalLoader()


def test_universe_has_154_tickers(loader):
    assert len(loader.universe) == 154
    # spot-check a few known tickers
    assert "ABB" in loader.universe
    assert "RELIANCE" in loader.universe
    assert "TCS" in loader.universe


def test_is_in_universe_within_valid_range(loader):
    # ABB has bars from 2021-04-23 onward per CSV
    assert loader.is_in_universe("ABB", date(2026, 4, 22)) is True


def test_is_in_universe_rejects_unknown(loader):
    assert loader.is_in_universe("NOTATICKER", date(2026, 4, 22)) is False


def test_daily_bars_normalized_schema(loader):
    df = loader.daily_bars("ABB")
    assert set(["date", "open", "high", "low", "close", "volume"]).issubset(df.columns)
    assert df["date"].is_monotonic_increasing
    assert df["close"].notna().all()


def test_daily_bars_caching(loader):
    df1 = loader.daily_bars("RELIANCE")
    df2 = loader.daily_bars("RELIANCE")
    assert df1 is df2  # same object — cache hit


def test_sector_bars_returns_normalized_frame(loader):
    df = loader.sector_bars("BANKNIFTY")
    assert set(["date", "open", "high", "low", "close"]).issubset(df.columns)
    assert df["date"].is_monotonic_increasing


def test_sector_bars_all_10_indices_loadable(loader):
    expected = ["BANKNIFTY", "NIFTYAUTO", "NIFTYENERGY", "NIFTYFMCG", "NIFTYIT",
                "NIFTYMEDIA", "NIFTYMETAL", "NIFTYPHARMA", "NIFTYPSUBANK", "NIFTYREALTY"]
    for idx in expected:
        df = loader.sector_bars(idx)
        assert len(df) > 100
