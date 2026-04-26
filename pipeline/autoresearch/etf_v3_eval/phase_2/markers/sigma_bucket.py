"""§6.3 marker: extreme/rare/mild σ-bucket conditional.

Phase 0 catalog: σ buckets couple with regime — must NOT be evaluated as
regime-independent. This module assigns the bucket; downstream code stratifies
by regime × bucket.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class SigmaBucket(str, Enum):
    SUB_THRESHOLD = "sub_threshold"   # |z| < 2.0
    MILD = "mild"                     # 2.0 ≤ |z| < 2.5
    RARE = "rare"                     # 2.5 ≤ |z| < 3.5
    EXTREME = "extreme"               # |z| ≥ 3.5


def bucket_event_sigma(events: pd.DataFrame, z_col: str = "break_z") -> pd.DataFrame:
    """Assign each event a SigmaBucket based on |z| of ``z_col``.

    Raises ValueError if ``z_col`` is missing from ``events.columns``.
    """
    if z_col not in events.columns:
        raise ValueError(
            f"bucket_event_sigma: column '{z_col}' not found; "
            f"available: {list(events.columns)}"
        )
    abs_z = events[z_col].abs()
    out = events.copy()
    out["bucket"] = SigmaBucket.SUB_THRESHOLD
    out.loc[(abs_z >= 2.0) & (abs_z < 2.5), "bucket"] = SigmaBucket.MILD
    out.loc[(abs_z >= 2.5) & (abs_z < 3.5), "bucket"] = SigmaBucket.RARE
    out.loc[abs_z >= 3.5, "bucket"] = SigmaBucket.EXTREME
    return out
