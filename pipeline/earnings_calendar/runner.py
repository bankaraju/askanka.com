"""Universe-level fetch orchestrator.

Reads each F&O ticker, fetches corporate_actions, classifies earnings
events, writes per-day JSON snapshot + appends to history parquet.
Per-symbol HTTP failures are logged and counted but do not abort the run
(data validation policy §9.3 quarantine pattern at symbol granularity).
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Iterable

from pipeline.earnings_calendar.classifier import (
    EPOCH_SENTINEL,
    _EARN_PATTERNS,
    extract_earnings_events,
    is_sentinel_date,
)
from pipeline.earnings_calendar.client import fetch_corporate_actions
from pipeline.earnings_calendar.store import append_history, write_day_json

log = logging.getLogger("earnings_calendar.runner")


def _count_sentinels(payload: dict) -> int:
    """Count rows whose date matches the IndianAPI missing-date sentinel
    (01-01-1970) and whose agenda WOULD have classified as earnings.

    These rows are visible in the raw payload and quarantined by the
    classifier; counting them feeds the cleanliness baseline (data
    validation policy §9.1)."""
    if not isinstance(payload, dict):
        return 0
    rows = payload.get("board_meetings", {}).get("data", [])
    if not isinstance(rows, list):
        return 0
    n = 0
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        date_s, agenda = row[0], row[1]
        try:
            d = dt.datetime.strptime(date_s, "%d-%m-%Y").date()
        except (ValueError, TypeError):
            continue
        if is_sentinel_date(d) and _EARN_PATTERNS.search(agenda or ""):
            n += 1
    return n


def run_for_universe(
    symbols: Iterable[str],
    *,
    data_dir: Path | str,
    asof: dt.date,
) -> dict:
    data_dir = Path(data_dir)
    all_events: list[dict] = []
    failures: list[dict] = []
    n_with_events = 0
    n_sentinel_quarantined = 0
    symbols = list(symbols)
    for s in symbols:
        try:
            payload = fetch_corporate_actions(s)
        except Exception as exc:  # noqa: BLE001 — per-symbol quarantine
            log.warning("fetch_corporate_actions failed for %s: %s", s, exc)
            failures.append({"symbol": s, "reason": str(exc)})
            continue
        n_sentinel_quarantined += _count_sentinels(payload)
        events = extract_earnings_events(s, payload)
        if events:
            n_with_events += 1
        all_events.extend(events)
    write_day_json(all_events, data_dir, asof=asof)
    append_history(all_events, data_dir / "history.parquet", asof=asof)
    return {
        "asof": asof.isoformat(),
        "n_symbols_attempted": len(symbols),
        "n_symbols_with_events": n_with_events,
        "n_events_total": len(all_events),
        "n_sentinel_dates_quarantined": n_sentinel_quarantined,
        "failures": failures,
    }
