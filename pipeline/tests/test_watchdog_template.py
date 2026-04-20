"""Tests for output-path template expansion in the watchdog.

Covers {today} and {last_biz_day} substitution so the inventory can declare
date-stamped output paths (e.g. data/daily/{today}.json) and the watchdog
resolves them against an IST-anchored `now` before calling os.stat.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pipeline.watchdog_freshness import (
    IST,
    expand_output_template,
    _last_business_day,
    _previous_business_day,
    _yesterday,
)


# ---- {today} ------------------------------------------------------------

def test_today_tuesday_substitutes_today_ist():
    now = datetime(2026, 4, 21, 10, 30, tzinfo=IST)  # Tuesday
    out = expand_output_template("pipeline/data/daily/{today}.json", now)
    assert out == "pipeline/data/daily/2026-04-21.json"


def test_today_handles_multiple_tokens_in_one_path():
    now = datetime(2026, 4, 21, 10, 30, tzinfo=IST)
    out = expand_output_template("a/{today}/b/{today}.json", now)
    assert out == "a/2026-04-21/b/2026-04-21.json"


def test_today_leaves_plain_paths_untouched():
    now = datetime(2026, 4, 21, 10, 30, tzinfo=IST)
    out = expand_output_template("data/articles_index.json", now)
    assert out == "data/articles_index.json"


def test_today_unknown_token_passes_through():
    now = datetime(2026, 4, 21, 10, 30, tzinfo=IST)
    out = expand_output_template("data/{garbage}.json", now)
    # Unknown tokens survive — file check will then fail OUTPUT_MISSING.
    assert out == "data/{garbage}.json"


# ---- {last_biz_day} -----------------------------------------------------

def test_last_biz_day_on_weekday_is_today():
    tue = datetime(2026, 4, 21, 10, 0, tzinfo=IST)
    assert _last_business_day(tue) == "2026-04-21"


def test_last_biz_day_on_monday_is_today():
    mon = datetime(2026, 4, 20, 10, 0, tzinfo=IST)
    assert _last_business_day(mon) == "2026-04-20"


def test_last_biz_day_on_saturday_walks_back_to_friday():
    sat = datetime(2026, 4, 25, 10, 0, tzinfo=IST)
    assert _last_business_day(sat) == "2026-04-24"


def test_last_biz_day_on_sunday_walks_back_to_friday():
    sun = datetime(2026, 4, 26, 10, 0, tzinfo=IST)
    assert _last_business_day(sun) == "2026-04-24"


def test_last_biz_day_template_expansion():
    sun = datetime(2026, 4, 26, 10, 0, tzinfo=IST)
    out = expand_output_template("daily/{last_biz_day}.json", sun)
    assert out == "daily/2026-04-24.json"


# ---- {prev_biz_day} -----------------------------------------------------

def test_prev_biz_day_on_tuesday_is_monday():
    tue = datetime(2026, 4, 21, 10, 0, tzinfo=IST)
    assert _previous_business_day(tue) == "2026-04-20"


def test_prev_biz_day_on_monday_is_previous_friday():
    mon = datetime(2026, 4, 20, 10, 0, tzinfo=IST)
    assert _previous_business_day(mon) == "2026-04-17"


def test_prev_biz_day_on_saturday_is_friday():
    sat = datetime(2026, 4, 25, 10, 0, tzinfo=IST)
    assert _previous_business_day(sat) == "2026-04-24"


def test_prev_biz_day_on_sunday_is_friday():
    sun = datetime(2026, 4, 26, 10, 0, tzinfo=IST)
    assert _previous_business_day(sun) == "2026-04-24"


def test_prev_biz_day_template_expansion():
    mon = datetime(2026, 4, 20, 10, 0, tzinfo=IST)
    out = expand_output_template("daily/{prev_biz_day}.json", mon)
    assert out == "daily/2026-04-17.json"


# ---- {yesterday} --------------------------------------------------------

def test_yesterday_subtracts_one_calendar_day():
    tue = datetime(2026, 4, 21, 10, 0, tzinfo=IST)
    assert _yesterday(tue) == "2026-04-20"


def test_yesterday_on_monday_returns_sunday():
    mon = datetime(2026, 4, 20, 10, 0, tzinfo=IST)
    assert _yesterday(mon) == "2026-04-19"


def test_yesterday_template_expansion():
    tue = datetime(2026, 4, 21, 10, 0, tzinfo=IST)
    out = expand_output_template("articles/{yesterday}-war.html", tue)
    assert out == "articles/2026-04-20-war.html"


# ---- Timezone guards ----------------------------------------------------

def test_expand_requires_timezone_aware_now():
    naive = datetime(2026, 4, 21, 10, 30)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        expand_output_template("a/{today}.json", naive)


def test_last_biz_day_requires_timezone_aware_now():
    naive = datetime(2026, 4, 21, 10, 30)
    with pytest.raises(ValueError, match="timezone-aware"):
        _last_business_day(naive)


# ---- IST boundary -------------------------------------------------------

def test_today_uses_ist_not_utc():
    from datetime import timezone as _tz
    # 00:00 UTC on 2026-04-21 → 05:30 IST on 2026-04-21 → today = 04-21
    utc_midnight = datetime(2026, 4, 21, 0, 0, tzinfo=_tz.utc)
    assert expand_output_template("{today}", utc_midnight) == "2026-04-21"
    # 18:00 UTC on 2026-04-20 → 23:30 IST on 2026-04-20 → today = 04-20
    utc_evening = datetime(2026, 4, 20, 18, 0, tzinfo=_tz.utc)
    assert expand_output_template("{today}", utc_evening) == "2026-04-20"
