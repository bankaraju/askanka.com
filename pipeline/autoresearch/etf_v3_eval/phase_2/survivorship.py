"""§6 survivorship — point-in-time universe and coverage summary.

Reads pipeline/data/fno_universe_history.json which has shape:
    {"snapshots": {"YYYY-MM-DD": ["TKR1","TKR2",...], ...}}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List, Union


def _load(path: Union[Path, str]) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def eligible_universe_at(path: Union[Path, str], asof: date) -> List[str]:
    """Return the most recent snapshot at or before ``asof`` (no future-leak).

    Raises ValueError if no snapshot exists on or before ``asof``: that
    indicates the backtest is asking for a universe predating the PIT history,
    which is a config error, not a legitimate empty-universe case. Fail loud
    rather than return ``[]`` and let downstream code silently produce zero
    trades on a "no tickers" universe.
    """
    snaps = _load(path)["snapshots"]
    keys = sorted(snaps.keys())
    chosen = None
    for k in keys:
        if date.fromisoformat(k) <= asof:
            chosen = k
        else:
            break
    if chosen is None:
        raise ValueError(
            f"No snapshot on or before {asof}; earliest snapshot is {keys[0] if keys else 'none'}"
        )
    return list(snaps[chosen])


def coverage_summary(path: Union[Path, str]) -> dict:
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
