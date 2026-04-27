"""PIT regime tape — point-in-time correct regime label per (date, time).

Audit doc: docs/superpowers/specs/2026-04-28-pit-regime-tape-data-source-audit.md

The tape resolves three feeds with explicit precedence:
  1. forward/<YYYY-MM-DD>.json — captured nightly from today_regime.json (canonical)
  2. v3_replay/<YYYY-MM-DD>.json — research-only historical replay (DEFERRED to v1)
  3. v2-hindsight from regime_history.csv — diagnostic only (CONTAMINATED, do not gate on)

Consumers call `load_zone_for(date, as_of)` and get back the zone string or None.
Live consumption defaults to the forward feed; backtest consumption rejects
requests where as_of would peek into a not-yet-captured value.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal, Optional

IST = timezone(timedelta(hours=5, minutes=30))

_HERE = Path(__file__).resolve().parent
_FORWARD_DIR = _HERE / "forward"
_V3_REPLAY_DIR = _HERE / "v3_replay"
_RESOLVED_DIR = _HERE / "resolved"

ALLOWED_ZONES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}

# The forward feed is published by AnkaETFSignal at ~04:45 IST. We treat any
# request with as_of strictly before this on the same date as PIT-illegal —
# i.e., the live engine had not yet computed a value at that timestamp.
FORWARD_PUBLISH_HHMM = (4, 45)


class PITViolation(Exception):
    """Raised when a backtest tries to read a regime value before it was published."""


def _parse_iso_aware(s: str) -> datetime:
    """Parse an ISO timestamp; require explicit timezone."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime not allowed: {s}")
    return dt


def _publish_cutoff(date_str: str) -> datetime:
    """The earliest as_of for which the forward feed can be considered published."""
    y, m, d = (int(x) for x in date_str.split("-"))
    return datetime(y, m, d, FORWARD_PUBLISH_HHMM[0], FORWARD_PUBLISH_HHMM[1], 0, tzinfo=IST)


def _try_inline_capture(date_str: str) -> bool:
    """Best-effort capture for `today` if forward feed is missing.

    Engines that fire before the 05:00 cron has run (or after a cron miss)
    call this transparently. Captures only succeed for date_str == today —
    we never invent a historical forward row.
    """
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if date_str != today:
        return False
    try:
        from pipeline.scripts.capture_pit_regime_tape_forward import capture
        capture(target_date=date_str)
        return (_FORWARD_DIR / f"{date_str}.json").is_file()
    except Exception:
        return False


def load_zone_for(
    date_str: str,
    as_of: Optional[datetime | str] = None,
    feed: Literal["auto", "forward", "v3_replay"] = "auto",
    auto_capture: bool = False,
) -> Optional[str]:
    """Return the regime zone for a given date, with PIT enforcement.

    Args:
        date_str: 'YYYY-MM-DD'.
        as_of: ISO timestamp or datetime (must be timezone-aware). If None,
               defaults to "now" (live consumption). For backtest, pass the
               trade timestamp.
        feed: 'auto' tries forward first, falls back to v3_replay; 'forward'
              and 'v3_replay' force a specific feed (raises if missing).
        auto_capture: if True and date_str == today and forward feed is
                      missing, attempt a capture before resolving. Live
                      engines should pass True; backtests must not (would
                      create rows for historical dates that never had them).

    Returns:
        Zone string ('NEUTRAL', 'RISK-ON', etc.) or None if no feed has data
        for that date.

    Raises:
        PITViolation: if as_of is earlier than the feed's publish cutoff for
                      the requested date.
    """
    if isinstance(as_of, str):
        as_of = _parse_iso_aware(as_of)
    if as_of is None:
        as_of = datetime.now(IST)
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    if feed in ("auto", "forward"):
        fp = _FORWARD_DIR / f"{date_str}.json"
        if not fp.is_file() and auto_capture:
            _try_inline_capture(date_str)
        if fp.is_file():
            cutoff = _publish_cutoff(date_str)
            if as_of < cutoff:
                raise PITViolation(
                    f"as_of {as_of.isoformat()} is before forward-feed publish cutoff "
                    f"{cutoff.isoformat()} for {date_str} — backtest cannot peek"
                )
            doc = json.loads(fp.read_text(encoding="utf-8"))
            return doc.get("zone")
        if feed == "forward":
            raise FileNotFoundError(f"forward feed missing for {date_str}")

    if feed in ("auto", "v3_replay"):
        fp = _V3_REPLAY_DIR / f"{date_str}.json"
        if fp.is_file():
            doc = json.loads(fp.read_text(encoding="utf-8"))
            return doc.get("zone")
        if feed == "v3_replay":
            raise FileNotFoundError(f"v3_replay feed missing for {date_str}")

    return None


def has_forward(date_str: str) -> bool:
    return (_FORWARD_DIR / f"{date_str}.json").is_file()


def is_neutral(date_str: str, as_of: Optional[datetime | str] = None) -> bool:
    """Convenience predicate for NEUTRAL-overlay engines."""
    return load_zone_for(date_str, as_of=as_of) == "NEUTRAL"


def feed_status(date_str: str) -> dict:
    """Diagnostic — returns which feeds are present for a date."""
    return {
        "date": date_str,
        "forward_present": has_forward(date_str),
        "v3_replay_present": (_V3_REPLAY_DIR / f"{date_str}.json").is_file(),
    }
