"""Tests for TA data fetcher — EODHD 5yr OHLCV."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_EODHD_RESPONSE = [
    {"date": "2025-01-02", "open": 100, "high": 105, "low": 98, "close": 103, "adjusted_close": 103, "volume": 1500000},
    {"date": "2025-01-03", "open": 103, "high": 107, "low": 101, "close": 106, "adjusted_close": 106, "volume": 1200000},
]


def test_fetch_single_stock(tmp_path: Path):
    from ta_data_fetcher import fetch_stock_history
    with patch("ta_data_fetcher.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_EODHD_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp
        path = fetch_stock_history("HAL", cache_dir=tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3
    assert "Date,Open,High,Low,Close,Volume" in lines[0]


def test_fetch_uses_cache(tmp_path: Path):
    from ta_data_fetcher import fetch_stock_history
    csv = tmp_path / "HAL.csv"
    csv.write_text("Date,Open,High,Low,Close,Volume\n2025-01-02,100,105,98,103,1500000\n")
    with patch("ta_data_fetcher.requests") as mock_req:
        path = fetch_stock_history("HAL", cache_dir=tmp_path, force=False)
        mock_req.get.assert_not_called()
    assert path == csv


def test_fetch_no_key_returns_none(tmp_path: Path):
    from ta_data_fetcher import fetch_stock_history
    with patch("ta_data_fetcher._api_key", return_value=None):
        result = fetch_stock_history("HAL", cache_dir=tmp_path)
    assert result is None


def test_fetch_batch(tmp_path: Path):
    from ta_data_fetcher import fetch_batch
    with patch("ta_data_fetcher.fetch_stock_history") as mock_fetch:
        mock_fetch.return_value = tmp_path / "HAL.csv"
        result = fetch_batch(["HAL", "TCS"], cache_dir=tmp_path, delay=0)
    assert len(result) == 2
    assert mock_fetch.call_count == 2
