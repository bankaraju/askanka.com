"""
Tests for pipeline/vol_engine.py — EWMA volatility engine.

Run: pytest pipeline/tests/test_vol_engine.py -v
"""
import pytest
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

IST = timezone(timedelta(hours=5, minutes=30))


SAMPLE_CLOSES = [
    100.0, 101.0, 99.5, 102.0, 100.5,
    103.0, 101.5, 104.0, 102.5, 105.0,
    103.5, 106.0, 104.5, 107.0, 105.5,
    108.0, 106.5, 109.0, 107.5, 110.0,
    108.5, 111.0, 109.5, 112.0, 110.5,
    113.0, 111.5, 114.0, 112.5, 115.0,
]


class TestComputeEWMAVol:
    def test_returns_positive_float(self):
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol(SAMPLE_CLOSES, span=30)
        assert isinstance(vol, float)
        assert vol > 0.0

    def test_annualised_range(self):
        """Annualised vol for +/- 1-2% daily moves should be 15-50%."""
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol(SAMPLE_CLOSES, span=30)
        assert 0.10 < vol < 0.60

    def test_higher_variance_gives_higher_vol(self):
        from pipeline.vol_engine import compute_ewma_vol
        calm = [100.0 + 0.1 * i for i in range(30)]
        wild = [100.0 + (3.0 if i % 2 == 0 else -3.0) for i in range(30)]
        assert compute_ewma_vol(wild, span=30) > compute_ewma_vol(calm, span=30)

    def test_minimum_two_prices(self):
        """Need at least 2 closes to compute a return."""
        from pipeline.vol_engine import compute_ewma_vol
        with pytest.raises(ValueError):
            compute_ewma_vol([100.0], span=30)

    def test_constant_prices_zero_vol(self):
        from pipeline.vol_engine import compute_ewma_vol
        vol = compute_ewma_vol([100.0] * 30, span=30)
        assert vol < 0.001


class TestCacheFreshness:
    def test_fresh_cache_is_not_stale(self):
        from pipeline.vol_engine import _is_cache_stale
        now = datetime.now(IST).isoformat()
        assert _is_cache_stale(now) is False

    def test_old_cache_is_stale(self):
        from pipeline.vol_engine import _is_cache_stale
        old = (datetime.now(IST) - timedelta(days=2)).isoformat()
        assert _is_cache_stale(old) is True


class TestGetStockVol:
    @patch("pipeline.vol_engine.fetch_and_cache_ohlcv")
    def test_returns_float_on_success(self, mock_fetch):
        from pipeline.vol_engine import get_stock_vol
        mock_fetch.return_value = [{"close": c} for c in SAMPLE_CLOSES]
        vol = get_stock_vol("HAL", cache_dir=Path("/tmp/test_vol_cache"))
        assert isinstance(vol, float)
        assert vol > 0.0

    @patch("pipeline.vol_engine.fetch_and_cache_ohlcv")
    def test_returns_none_on_failure(self, mock_fetch):
        from pipeline.vol_engine import get_stock_vol
        mock_fetch.return_value = []
        vol = get_stock_vol("BADTICKER", cache_dir=Path("/tmp/test_vol_cache"))
        assert vol is None
