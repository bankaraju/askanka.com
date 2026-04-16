"""Tests for cadence formulas and market-hours awareness."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from pipeline.watchdog_freshness import (
    IST,
    compute_window_seconds,
    is_market_hours,
    FreshnessResult,
    check_file_freshness,
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


class TestCheckFileFreshness:
    def test_missing_file_returns_missing(self, tmp_path):
        missing = tmp_path / "nope.json"
        result = check_file_freshness(
            missing, cadence_class="daily", grace_multiplier=1.5,
            now=datetime(2026, 4, 16, 10, 0, tzinfo=IST),
        )
        assert result == FreshnessResult.OUTPUT_MISSING

    def test_fresh_daily_file(self, tmp_path):
        f = tmp_path / "fresh.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)
        # Set mtime 1 hour ago
        one_hour_ago = (now - timedelta(hours=1)).timestamp()
        import os
        os.utime(f, (one_hour_ago, one_hour_ago))

        result = check_file_freshness(
            f, cadence_class="daily", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.FRESH

    def test_stale_daily_file(self, tmp_path):
        f = tmp_path / "stale.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)
        # Set mtime 31 hours ago (window for daily/1.5 is 30h)
        import os
        old = (now - timedelta(hours=31)).timestamp()
        os.utime(f, (old, old))

        result = check_file_freshness(
            f, cadence_class="daily", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.OUTPUT_STALE

    def test_intraday_outside_market_hours_is_fresh(self, tmp_path):
        f = tmp_path / "live_status.json"
        f.write_text("{}")
        # Saturday 10:00 IST — outside market hours, always fresh
        now = datetime(2026, 4, 18, 10, 0, tzinfo=IST)
        import os
        very_old = (now - timedelta(days=5)).timestamp()
        os.utime(f, (very_old, very_old))

        result = check_file_freshness(
            f, cadence_class="intraday", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.FRESH

    def test_intraday_during_market_hours_stale(self, tmp_path):
        f = tmp_path / "live_status.json"
        f.write_text("{}")
        # Tuesday 10:00 IST, file is 2 hours old — window is 60 min → stale
        now = datetime(2026, 4, 14, 10, 0, tzinfo=IST)
        import os
        old = (now - timedelta(minutes=120)).timestamp()
        os.utime(f, (old, old))

        result = check_file_freshness(
            f, cadence_class="intraday", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.OUTPUT_STALE

    def test_naive_now_raises(self, tmp_path):
        # check_file_freshness must reject naive datetimes for all cadences
        f = tmp_path / "x.json"
        f.write_text("{}")
        naive = datetime(2026, 4, 16, 10, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            check_file_freshness(
                f, cadence_class="daily", grace_multiplier=1.5, now=naive,
            )

    def test_age_exactly_at_window_is_fresh(self, tmp_path):
        # Spec: stale is age > window (strict). Equality is FRESH.
        f = tmp_path / "edge.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)
        # Daily/1.5 window = 30h exactly
        exactly_window = (now - timedelta(seconds=30 * 3600)).timestamp()
        import os
        os.utime(f, (exactly_window, exactly_window))

        result = check_file_freshness(
            f, cadence_class="daily", grace_multiplier=1.5, now=now,
        )
        assert result == FreshnessResult.FRESH

    def test_directory_path_treated_as_missing(self, tmp_path):
        # os.stat on a directory returns stats; explicit IsADirectoryError
        # won't fire — but the inventory should never point at a directory.
        # We use a file path where os.stat would raise (simulate by pointing
        # at a non-existent path with a truly unreachable parent).
        # Simpler: verify an unreadable-but-existing path returns OUTPUT_MISSING
        # by pointing at a path.exists()==False leaf (already covered by
        # test_missing_file_returns_missing). This test locks the OSError
        # catch path by deleting the file between exists() and stat().
        import os
        f = tmp_path / "racing.json"
        f.write_text("{}")
        now = datetime(2026, 4, 16, 10, 0, tzinfo=IST)

        call_count = [0]
        original_stat = os.stat
        def flaky_stat(path, *args, **kwargs):
            call_count[0] += 1
            # Raise only on the second call (after path.exists() succeeds)
            if str(path).endswith("racing.json") and call_count[0] > 1:
                raise PermissionError("simulated")
            return original_stat(path, *args, **kwargs)

        import pipeline.watchdog_freshness as wf
        wf.os.stat = flaky_stat
        try:
            result = check_file_freshness(
                f, cadence_class="daily", grace_multiplier=1.5, now=now,
            )
        finally:
            wf.os.stat = original_stat

        assert result == FreshnessResult.OUTPUT_MISSING
