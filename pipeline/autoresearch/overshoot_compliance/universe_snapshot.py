"""Universe-snapshot disclosure per §6.2 of backtesting-specs.txt v1.0.

When pipeline/data/fno_universe_history.json is present, compute
coverage_ratio. When not present, emit an explicit
SURVIVORSHIP-UNCORRECTED-WAIVED disclosure pointing at the waiver file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence


def build_snapshot(
    current_tickers: Sequence[str],
    history_path: Path,
    waiver_path: Path | None,
) -> dict:
    n_cur = len(set(current_tickers))
    if not Path(history_path).exists():
        return {
            "n_tickers_current": n_cur,
            "n_tickers_ever": None,
            "n_tickers_delisted": None,
            "coverage_ratio": None,
            "status": "SURVIVORSHIP-UNCORRECTED-WAIVED",
            "history_path": str(history_path),
            "waiver_path": str(waiver_path) if waiver_path else None,
        }

    data = json.loads(Path(history_path).read_text(encoding="utf-8"))
    snapshots = data.get("snapshots", [])
    ever = set()
    for snap in snapshots:
        ever.update(snap.get("symbols", []))
    delisted = ever - set(current_tickers)
    ratio = (len(delisted) / len(ever)) if ever else 0.0
    return {
        "n_tickers_current": n_cur,
        "n_tickers_ever": len(ever),
        "n_tickers_delisted": len(delisted),
        "coverage_ratio": round(ratio, 4),
        "status": "SURVIVORSHIP-CORRECTED",
        "history_path": str(history_path),
    }
