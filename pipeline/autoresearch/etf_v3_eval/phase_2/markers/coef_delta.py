"""§6.3 marker: week-over-week |Δweight| > P75 ⇒ "regime in transition" flag.

Rationale (Phase 0 catalog): 51.8 std-units rotation on 2025-12-30 and 37.2 on
2026-04-16 aligned with v3 zone shifts. Big ETF coefficient rotation is itself
a regime-change marker.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def compute_weekly_delta_magnitude(
    prev: Mapping[str, float],
    curr: Mapping[str, float],
) -> float:
    """L2 norm of (curr − prev) over the union of keys; missing keys default to 0."""
    keys = set(prev) | set(curr)
    sq = sum((curr.get(k, 0.0) - prev.get(k, 0.0)) ** 2 for k in keys)
    return float(np.sqrt(sq))


def flag_high_rotation_dates(
    rotation_df: pd.DataFrame,
    percentile: float = 75.0,
) -> tuple[pd.DataFrame, float]:
    """Add ``high_rotation`` bool column flagging rows whose ``delta_mag`` > Pₚ.

    Returns ``(out, threshold)``. The threshold is also written to
    ``out.attrs["threshold"]`` for direct callers, but ``attrs`` is not preserved
    across most pandas operations (merge/groupby/copy), so the explicit return
    value is the contract — callers must capture it from the tuple.
    """
    threshold = float(np.percentile(rotation_df["delta_mag"], percentile))
    out = rotation_df.copy()
    out["high_rotation"] = out["delta_mag"] > threshold
    out.attrs["threshold"] = threshold
    return out, threshold
