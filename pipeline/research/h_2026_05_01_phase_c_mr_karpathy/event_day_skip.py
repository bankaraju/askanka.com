"""Event-day skip filter for the Phase C MR Karpathy v1 engine.

Spec section 4.1 + section 6 step 6: skip if snap_day in [event - 1, event, event + 1]
for any event in the registered calendar.

Calendar at: pipeline/research/h_2026_05_01_phase_c_mr_karpathy/event_calendar.json
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

CALENDAR_PATH = Path(__file__).resolve().parent / "event_calendar.json"


@lru_cache(maxsize=1)
def _event_days_with_buffer() -> frozenset[str]:
    """Set of YYYY-MM-DD strings covering [event - 1, event, event + 1] for every event."""
    if not CALENDAR_PATH.is_file():
        return frozenset()
    try:
        payload = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    buffer = int(payload.get("skip_window_days", 1))
    out: set[str] = set()
    for ev in payload.get("events", []):
        d = ev.get("date")
        if not d:
            continue
        try:
            ev_date = date.fromisoformat(d)
        except ValueError:
            continue
        for offset in range(-buffer, buffer + 1):
            out.add((ev_date + timedelta(days=offset)).isoformat())
    return frozenset(out)


def is_event_day(date_str: str) -> bool:
    """True if `date_str` is within the skip window of any registered event."""
    return date_str in _event_days_with_buffer()


def reload_calendar() -> None:
    """Force re-read of event_calendar.json. Useful in tests."""
    _event_days_with_buffer.cache_clear()
