"""Pure-function classifier turning IndianAPI board-meeting agenda strings
into typed quarterly-earnings events.

Source: SEBI Regulation 29 mandates listed companies to disclose Board
Meeting agenda at least 5 working days ahead. Earnings results are one of
the standard agenda items; the free-text agenda field requires regex
normalisation per data validation policy §9.1.
"""
from __future__ import annotations

import datetime as dt
import enum
import re
from typing import Optional

_EARN_PATTERNS = re.compile(
    r"(quarterly results"
    r"|audited financial results"
    r"|unaudited financial results"
    r"|financial results for the quarter"
    r"|board.*consider.*results)",
    re.I,
)
_DIV_PATTERNS = re.compile(r"(dividend|interim dividend|final dividend)", re.I)
_FUND_PATTERNS = re.compile(
    r"(raising of funds|non.?convertible debentures|qip|preferential issue|rights issue|fund.?raising)",
    re.I,
)

# IndianAPI returns 01-01-1970 as a missing-date sentinel for announcements
# whose meeting date has not been reported. These rows must be quarantined
# (data validation policy §9.1, §9.3) — silent pass-through would corrupt
# any time-window feature.
EPOCH_SENTINEL = dt.date(1970, 1, 1)


class EventKind(str, enum.Enum):
    QUARTERLY_EARNINGS = "QUARTERLY_EARNINGS"


def _parse_dmy(date_s: str) -> dt.date:
    return dt.datetime.strptime(date_s, "%d-%m-%Y").date()


def is_sentinel_date(d: dt.date) -> bool:
    return d == EPOCH_SENTINEL


def classify_board_meeting(date_s: str, agenda: str) -> Optional[dict]:
    """Return a typed event dict if the agenda matches the earnings-result
    pattern AND the date is not the IndianAPI missing-date sentinel
    (01-01-1970). Returns None if the agenda is not earnings-related or if
    the date is a sentinel. Raises ValueError on unparseable date format."""
    event_date = _parse_dmy(date_s)
    if is_sentinel_date(event_date):
        return None
    if not _EARN_PATTERNS.search(agenda or ""):
        return None
    return {
        "event_date": event_date,
        "kind": EventKind.QUARTERLY_EARNINGS,
        "has_dividend": bool(_DIV_PATTERNS.search(agenda)),
        "has_fundraise": bool(_FUND_PATTERNS.search(agenda)),
        "agenda_raw": agenda,
    }


def extract_earnings_events(symbol: str, payload: dict) -> list[dict]:
    """Walk the board_meetings.data rows in payload, classify each, dedupe by
    event_date, and return a list sorted descending by date."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("board_meetings", {}).get("data", [])
    if not isinstance(rows, list):
        return []
    seen: set[dt.date] = set()
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        date_s, agenda = row[0], row[1]
        try:
            ev = classify_board_meeting(date_s, agenda)
        except (ValueError, TypeError):
            continue
        if ev is None:
            continue
        if ev["event_date"] in seen:
            continue
        seen.add(ev["event_date"])
        ev["symbol"] = symbol
        out.append(ev)
    out.sort(key=lambda e: e["event_date"], reverse=True)
    return out
