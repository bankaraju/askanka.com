"""Compute regime-flip drawdown CI from historical calm_breaks.

Reads pipeline/autoresearch/regime_persistence_results.json. For each
transition into `to_zone`, collects nifty_5d_after as a Nifty-index
proxy for per-position exposure. Returns a percentile summary so the
Risk tab can render "p95 of N=k historical flips into TO_ZONE" instead
of a hardcoded -2%/position placeholder.

Caveat: nifty_5d_after is an index proxy. Per-spread P&L backtest data
is not yet stored day-by-day; once unified_backtest emits a daily
series, swap that in.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_SOURCE = (
    Path(__file__).parent / "regime_persistence_results.json"
)


def compute_flip_drawdown_ci(
    source: Optional[Path] = None,
    to_zone: str = "RISK-OFF",
    percentile: int = 95,
) -> dict:
    """p95 drawdown observed in the `nifty_5d_after` series for flips into `to_zone`.

    Returns dict:
      - to_zone: str
      - n_flips: int
      - p95_drawdown_pct: float | None   # worst-realistic post-flip Nifty 5d return
      - median_drawdown_pct: float | None
      - sample_returns: list[float]
      - source: "nifty_5d_after proxy (not per-position)"
      - data_file: absolute path read
    """
    source = Path(source) if source else DEFAULT_SOURCE
    if not source.exists():
        return {
            "to_zone": to_zone, "n_flips": 0,
            "p95_drawdown_pct": None, "median_drawdown_pct": None,
            "sample_returns": [],
            "source": "nifty_5d_after proxy (not per-position)",
            "data_file": str(source),
            "error": "source file not found",
        }

    data = json.loads(source.read_text(encoding="utf-8"))
    breaks = data.get("calm_breaks", [])
    matched = [
        float(b["nifty_5d_after"]) for b in breaks
        if b.get("to_zone") == to_zone and "nifty_5d_after" in b
    ]
    if not matched:
        return {
            "to_zone": to_zone, "n_flips": 0,
            "p95_drawdown_pct": None, "median_drawdown_pct": None,
            "sample_returns": [],
            "source": "nifty_5d_after proxy (not per-position)",
            "data_file": str(source),
        }

    # "Drawdown" = low percentile of the observed return distribution
    arr = np.array(matched, dtype=float)
    # For a 95-percentile "worst-realistic loss", take the 5th percentile
    # of the return distribution (return lower -> worse outcome).
    p_worst = float(np.percentile(arr, 100 - percentile))
    p_median = float(np.median(arr))
    return {
        "to_zone": to_zone,
        "n_flips": len(matched),
        "p95_drawdown_pct": round(p_worst, 3),
        "median_drawdown_pct": round(p_median, 3),
        "sample_returns": [round(x, 3) for x in matched],
        "source": "nifty_5d_after proxy (not per-position)",
        "data_file": str(source),
    }
