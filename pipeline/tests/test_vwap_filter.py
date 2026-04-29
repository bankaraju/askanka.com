"""Tests for pipeline.research.vwap_filter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pipeline.research.vwap_filter import (
    DROP, KEEP, WATCH,
    VWAP_DEV_SIGNED_HI_CUT,
    VWAP_DEV_SIGNED_LO_CUT,
    classify,
    compute_filter_tag,
    compute_vwap_dev_signed,
)


IST = timezone(timedelta(hours=5, minutes=30))


def _make_bars(n: int, base_close: float, base_vol: float = 100000.0,
                drift: float = 0.0, date_iso: str = "2026-04-29") -> list[dict]:
    """Generate n minute bars with optional linear drift on close."""
    rows = []
    for i in range(n):
        c = base_close + drift * i
        rows.append({
            "date": f"{date_iso} 09:{15+i:02d}:00",
            "open": c, "high": c + 0.1, "low": c - 0.1,
            "close": c, "volume": base_vol,
        })
    return rows


class TestClassify:
    def test_keep_when_below_hi_cut(self):
        assert classify(VWAP_DEV_SIGNED_HI_CUT - 0.0001) == KEEP
        assert classify(VWAP_DEV_SIGNED_LO_CUT - 0.001) == KEEP
        assert classify(0.0) == KEEP

    def test_drop_at_or_above_hi_cut(self):
        assert classify(VWAP_DEV_SIGNED_HI_CUT) == DROP
        assert classify(VWAP_DEV_SIGNED_HI_CUT + 0.001) == DROP
        assert classify(0.05) == DROP

    def test_watch_on_none(self):
        assert classify(None) == WATCH


class TestComputeVwapDevSigned:
    def test_long_with_price_below_vwap_returns_negative(self):
        # 15 bars rising — last close above mean → vwap_dev > 0 unsigned;
        # for SHORT side, signed = -dev → negative; for LONG, positive.
        bars = _make_bars(15, base_close=100.0, drift=0.05)
        with patch("pipeline.kite_client.fetch_historical", return_value=bars):
            d = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
            dev_long = compute_vwap_dev_signed("ABC", "LONG", as_of_dt=d)
            dev_short = compute_vwap_dev_signed("ABC", "SHORT", as_of_dt=d)
        assert dev_long is not None and dev_long > 0
        assert dev_short is not None and dev_short < 0
        assert dev_long == pytest.approx(-dev_short)

    def test_returns_none_on_insufficient_bars(self):
        bars = _make_bars(5, base_close=100.0)
        with patch("pipeline.kite_client.fetch_historical", return_value=bars):
            d = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
            assert compute_vwap_dev_signed("ABC", "LONG", as_of_dt=d) is None

    def test_returns_none_on_empty_bars(self):
        with patch("pipeline.kite_client.fetch_historical", return_value=[]):
            assert compute_vwap_dev_signed("ABC", "LONG") is None

    def test_returns_none_on_fetch_exception(self):
        with patch("pipeline.kite_client.fetch_historical",
                   side_effect=RuntimeError("kite down")):
            assert compute_vwap_dev_signed("ABC", "LONG") is None

    def test_returns_none_when_no_bars_today(self):
        # Bars exist but for a different date
        bars = _make_bars(15, base_close=100.0, date_iso="2026-04-28")
        with patch("pipeline.kite_client.fetch_historical", return_value=bars):
            d = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
            assert compute_vwap_dev_signed("ABC", "LONG", as_of_dt=d) is None

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError):
            compute_vwap_dev_signed("ABC", "FLAT")


class TestComputeFilterTag:
    def test_keep_when_close_at_vwap(self):
        bars = _make_bars(15, base_close=100.0, drift=0.0)
        with patch("pipeline.kite_client.fetch_historical", return_value=bars):
            d = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
            dev, tag = compute_filter_tag("ABC", "LONG", as_of_dt=d)
        assert tag == KEEP
        assert dev == pytest.approx(0.0, abs=1e-6)

    def test_drop_for_extended_long(self):
        # Rising aggressively — last close ~0.4% above first → > HI cut for LONG
        bars = _make_bars(15, base_close=100.0, drift=0.06)
        with patch("pipeline.kite_client.fetch_historical", return_value=bars):
            d = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
            dev, tag = compute_filter_tag("ABC", "LONG", as_of_dt=d)
        assert tag == DROP
        assert dev is not None and dev >= VWAP_DEV_SIGNED_HI_CUT

    def test_watch_when_data_unavailable(self):
        with patch("pipeline.kite_client.fetch_historical", return_value=[]):
            dev, tag = compute_filter_tag("ABC", "LONG")
        assert tag == WATCH
        assert dev is None
