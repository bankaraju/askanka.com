"""Cadence formulas and market-hours gate for the watchdog.

The watchdog asks two orthogonal questions per file:
  1. Are we currently in a window where this file is expected to be fresh?
     (market-hours awareness for intraday cadence)
  2. If so, is the file older than its grace-adjusted window?
"""

import enum
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# (base_interval_seconds, base_grace_seconds) per cadence class.
_CADENCE_BASE = {
    "intraday": (15 * 60, 30 * 60),       # 15 min expected, 30 min base grace
    "daily":    (24 * 3600, 4 * 3600),    # 24 h, 4 h base grace
    "weekly":   (7 * 86400, 1 * 86400),   # 7 d, 1 d base grace
}

_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def compute_window_seconds(cadence_class: str, grace_multiplier: float) -> int:
    """Return window = base_interval + base_grace * grace_multiplier (seconds)."""
    if cadence_class not in _CADENCE_BASE:
        raise ValueError(f"unknown cadence_class: {cadence_class!r}")
    if grace_multiplier < 0:
        raise ValueError(f"grace_multiplier must be >= 0, got {grace_multiplier}")
    base_interval, base_grace = _CADENCE_BASE[cadence_class]
    return int(base_interval + base_grace * grace_multiplier)


def is_market_hours(now: datetime) -> bool:
    """True if `now` is within Mon-Fri 09:15-15:30 IST.

    Accepts any timezone-aware datetime; converts to IST internally.
    """
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")
    now_ist = now.astimezone(IST)
    if now_ist.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return _MARKET_OPEN <= now_ist.time() <= _MARKET_CLOSE


class FreshnessResult(enum.Enum):
    FRESH = "FRESH"
    OUTPUT_STALE = "OUTPUT_STALE"
    OUTPUT_MISSING = "OUTPUT_MISSING"


def _last_business_day(now: datetime) -> str:
    """Return the most recent Mon-Fri date in IST as YYYY-MM-DD.

    If `now` is a weekend, walks back to the previous Friday. Otherwise
    returns today's IST date.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    d = now.astimezone(IST).date()
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d = d - timedelta(days=1)
    return d.isoformat()


def _previous_business_day(now: datetime) -> str:
    """Return the most recent Mon-Fri date *strictly before* today in IST.

    Use this for tasks whose completion we verify against yesterday's
    output, so the check is robust to being invoked before today's task
    has fired. Monday resolves to Friday; Saturday/Sunday resolve to the
    previous Friday.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    d = now.astimezone(IST).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d.isoformat()


def _yesterday(now: datetime) -> str:
    """Return yesterday's calendar date in IST. No business-day skipping."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return (now.astimezone(IST).date() - timedelta(days=1)).isoformat()


def expand_output_template(template: str, now: datetime) -> str:
    """Substitute supported tokens in an inventory `outputs` path.

    Supported tokens (IST-anchored):
      {today}        → today's date YYYY-MM-DD
      {yesterday}    → today - 1 day (calendar; no weekend skipping)
      {last_biz_day} → most recent Mon-Fri (today on weekdays,
                       previous Friday on weekends)
      {prev_biz_day} → most recent Mon-Fri STRICTLY BEFORE today
                       (Monday→Friday, Tuesday→Monday, weekends→Friday)

    ``{prev_biz_day}`` and ``{yesterday}`` are the right choice when the
    watchdog is expected to run before today's task has fired — they
    validate that yesterday's output landed without false-alarming on the
    absence of today's (not-yet-produced) output.

    Unknown tokens are left in place — the resulting path will simply fail
    `exists()` and the watchdog will report OUTPUT_MISSING. Plain paths
    pass through unchanged.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.astimezone(IST).date().isoformat()
    return (
        template
        .replace("{today}", today)
        .replace("{yesterday}", _yesterday(now))
        .replace("{last_biz_day}", _last_business_day(now))
        .replace("{prev_biz_day}", _previous_business_day(now))
    )


def check_file_freshness(
    output_path: Path,
    cadence_class: str,
    grace_multiplier: float,
    now: datetime,
) -> FreshnessResult:
    """Classify one file's freshness per the spec's stale-detection logic.

    1. If file missing → OUTPUT_MISSING.
    2. If intraday AND not market hours → FRESH (always fresh outside market hours).
    3. If file age > window → OUTPUT_STALE.
    4. Else → FRESH.
    """
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")
    path = Path(output_path)
    if not path.exists():
        return FreshnessResult.OUTPUT_MISSING

    if cadence_class == "intraday" and not is_market_hours(now):
        return FreshnessResult.FRESH

    window = compute_window_seconds(cadence_class, grace_multiplier)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return FreshnessResult.OUTPUT_MISSING
    age = now.timestamp() - mtime
    if age > window:
        return FreshnessResult.OUTPUT_STALE
    return FreshnessResult.FRESH
