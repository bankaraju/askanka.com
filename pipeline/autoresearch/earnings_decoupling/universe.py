"""PIT F&O membership helpers, sourced from fno_universe_history.json."""
from __future__ import annotations

import bisect
import json
from pathlib import Path


def load_history(path: Path | str) -> list[dict]:
    body = json.loads(Path(path).read_text())
    snaps = sorted(body["snapshots"], key=lambda s: s["date"])
    return snaps


def is_in_fno(history: list[dict], symbol: str, event_date: str) -> bool:
    dates = [s["date"] for s in history]
    idx = bisect.bisect_right(dates, event_date) - 1
    if idx < 0:
        return False
    return symbol in history[idx]["symbols"]
