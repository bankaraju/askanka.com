"""Cadence formulas and market-hours gate for the watchdog.

The watchdog asks two orthogonal questions per file:
  1. Are we currently in a window where this file is expected to be fresh?
     (market-hours awareness for intraday cadence)
  2. If so, is the file older than its grace-adjusted window?
"""

from datetime import datetime, time, timedelta, timezone

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
