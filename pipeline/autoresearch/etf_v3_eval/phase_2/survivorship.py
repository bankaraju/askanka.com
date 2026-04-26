"""§6 survivorship — point-in-time universe and coverage summary.

Reads pipeline/data/fno_universe_history.json which has shape:
    {"snapshots": {"YYYY-MM-DD": ["TKR1","TKR2",...], ...}}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def eligible_universe_at(path: Path, asof: date) -> List[str]:
    """Return the most recent snapshot at or before ``asof`` (no future-leak).

    If no snapshot is on or before ``asof``, returns an empty list.
    """
    snaps = _load(path)["snapshots"]
    keys = sorted(snaps.keys())
    chosen = None
    for k in keys:
        if date.fromisoformat(k) <= asof:
            chosen = k
        else:
            break
    return list(snaps[chosen]) if chosen else []


def coverage_summary(path: Path) -> dict:
    """Return survivorship coverage ratios across all snapshots."""
    snaps = _load(path)["snapshots"]
    keys = sorted(snaps.keys())
    if not keys:
        raise ValueError("snapshot file contains no snapshots")
    ever = set().union(*[set(v) for v in snaps.values()])
    current = set(snaps[keys[-1]])
    delisted = ever - current
    return {
        "n_tickers_current": len(current),
        "n_tickers_ever": len(ever),
        "n_tickers_delisted": len(delisted),
        "coverage_ratio": len(delisted) / max(len(ever), 1),
        "snapshots_count": len(keys),
        "earliest_snapshot": keys[0],
        "latest_snapshot": keys[-1],
    }
