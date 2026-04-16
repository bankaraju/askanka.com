"""Tests for cadence formulas and market-hours awareness."""

from datetime import datetime, timezone, timedelta

import pytest

from pipeline.watchdog_freshness import (
    IST,
    compute_window_seconds,
    is_market_hours,
)


class TestComputeWindow:
    def test_intraday_default_multiplier(self):
        # base 15 min + 30 min grace * 1.5 = 60 min = 3600s
        assert compute_window_seconds("intraday", 1.5) == 3600

    def test_intraday_grace_2x(self):
        # 15 min + 30 min * 2.0 = 75 min = 4500s
        assert compute_window_seconds("intraday", 2.0) == 4500

    def test_daily_default(self):
        # 24h + 4h * 1.5 = 30h = 108000s
        assert compute_window_seconds("daily", 1.5) == 108000

    def test_weekly_default(self):
        # 7d + 1d * 1.5 = 8.5d = 734400s
        assert compute_window_seconds("weekly", 1.5) == 734400

    def test_unknown_cadence_raises(self):
        with pytest.raises(ValueError, match="unknown cadence_class"):
            compute_window_seconds("hourly", 1.5)

    def test_negative_multiplier_raises(self):
        with pytest.raises(ValueError, match="grace_multiplier"):
            compute_window_seconds("daily", -0.5)


class TestMarketHours:
    def test_tuesday_10am_is_market_hours(self):
        # 2026-04-14 was a Tuesday
        t = datetime(2026, 4, 14, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_0914_before_open(self):
        t = datetime(2026, 4, 14, 9, 14, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_tuesday_0915_at_open(self):
        t = datetime(2026, 4, 14, 9, 15, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_1530_at_close(self):
        t = datetime(2026, 4, 14, 15, 30, tzinfo=IST)
        assert is_market_hours(t) is True

    def test_tuesday_1531_after_close(self):
        t = datetime(2026, 4, 14, 15, 31, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_saturday_is_not_market_hours(self):
        # 2026-04-18 is a Saturday
        t = datetime(2026, 4, 18, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_sunday_is_not_market_hours(self):
        t = datetime(2026, 4, 19, 10, 0, tzinfo=IST)
        assert is_market_hours(t) is False

    def test_utc_timestamp_converted_correctly(self):
        # 04:30 UTC on Tuesday = 10:00 IST — market hours
        t = datetime(2026, 4, 14, 4, 30, tzinfo=timezone.utc)
        assert is_market_hours(t) is True

    def test_naive_datetime_raises(self):
        # Naive datetime must be rejected to avoid platform-dependent conversion.
        naive = datetime(2026, 4, 14, 10, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            is_market_hours(naive)
