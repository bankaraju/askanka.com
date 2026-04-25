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

from pipeline.earnings_calendar.classifier import extract_earnings_events
from pipeline.earnings_calendar.client import fetch_corporate_actions
from pipeline.earnings_calendar.store import append_history, write_day_json

log = logging.getLogger("earnings_calendar.runner")


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
    symbols = list(symbols)
    for s in symbols:
        try:
            payload = fetch_corporate_actions(s)
        except Exception as exc:  # noqa: BLE001 — per-symbol quarantine
            log.warning("fetch_corporate_actions failed for %s: %s", s, exc)
            failures.append({"symbol": s, "reason": str(exc)})
            continue
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
        "failures": failures,
    }
