from __future__ import annotations
import pandas as pd
from unittest.mock import patch
from pipeline.research.phase_c_v5.data_prep import backfill_indices as bi


def test_known_fno_indices_list_includes_banknifty_and_nifty():
    assert "BANKNIFTY" in bi.KNOWN_FNO_INDICES
    assert "NIFTY" in bi.KNOWN_FNO_INDICES


def test_backfill_daily_calls_fetcher_per_symbol(tmp_path):
    fake_df = pd.DataFrame([{"date": pd.Timestamp("2026-01-01"),
                              "open": 100, "high": 101, "low": 99,
                              "close": 100.5, "volume": 0}])
    with patch.object(bi, "_fetch_daily", return_value=fake_df) as mock_fetch:
        results = bi.backfill_daily(["NIFTY", "BANKNIFTY"], days=1500,
                                     out_dir=tmp_path)
    assert mock_fetch.call_count == 2
    assert (tmp_path / "NIFTY_daily.csv").is_file()
    assert (tmp_path / "BANKNIFTY_daily.csv").is_file()
    assert results["NIFTY"] == 1
    assert results["BANKNIFTY"] == 1


def test_backfill_minute_creates_per_day_files(tmp_path):
    fake_df = pd.DataFrame([{"date": pd.Timestamp("2026-04-01 09:15:00"),
                              "open": 100, "high": 101, "low": 99,
                              "close": 100.5, "volume": 0}])
    with patch.object(bi, "_fetch_minute", return_value=fake_df):
        results = bi.backfill_minute(
            ["NIFTY"], trade_dates=["2026-04-01", "2026-04-02"],
            out_dir=tmp_path)
    assert results["NIFTY"]["2026-04-01"] == 1
    assert (tmp_path / "NIFTY_2026-04-01.parquet").is_file()


def test_yfinance_alias_map_has_known_indices():
    """yfinance uses ^-prefixed index tickers, different from Kite."""
    assert bi._YFINANCE_ALIAS["NIFTY"] == "^NSEI"
    assert bi._YFINANCE_ALIAS["BANKNIFTY"] == "^NSEBANK"
