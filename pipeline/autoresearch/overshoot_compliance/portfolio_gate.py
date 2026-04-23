"""Portfolio-correlation + concentration gate per §11C of backtesting-specs.txt v1.0.

Pass conditions:
- Max absolute pairwise daily-P&L correlation across surviving (ticker, direction)
  strategies must be ≤ 0.60.
- No single sector may account for ≥ 40% of surviving strategies.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd


def evaluate(
    pnl: pd.DataFrame,
    sectors: dict[str, str],
    corr_threshold: float = 0.60,
    concentration_cap: float = 0.40,
) -> dict:
    """pnl: columns are strategy IDs (e.g. "RELIANCE-UP"), rows are dates."""
    if pnl.shape[1] < 2:
        max_corr = 0.0
        top_pair = None
    else:
        C = pnl.corr()
        arr = C.to_numpy().copy()
        np.fill_diagonal(arr, 0.0)
        if arr.size == 0:
            max_corr = 0.0
            top_pair = None
        else:
            i, j = np.unravel_index(np.argmax(np.abs(arr)), arr.shape)
            max_corr = float(arr[i, j])
            top_pair = [C.columns[i], C.columns[j]]

    total = len(pnl.columns)
    sector_counts = Counter(sectors.get(c, "Unmapped") for c in pnl.columns)
    max_sector_share = (max(sector_counts.values()) / total) if total else 0.0
    max_sector = sector_counts.most_common(1)[0][0] if total else None

    corr_verdict = "PASS" if max_corr <= corr_threshold else "FAIL"
    conc_verdict = "PASS" if max_sector_share < concentration_cap else "FAIL"
    overall = "PASS" if (corr_verdict == "PASS" and conc_verdict == "PASS") else "FAIL"
    return {
        "max_pairwise_correlation": round(max_corr, 4),
        "top_correlated_pair": top_pair,
        "max_sector_share": round(max_sector_share, 4),
        "max_sector": max_sector,
        "corr_verdict": corr_verdict,
        "concentration_verdict": conc_verdict,
        "overall_verdict": overall,
        "n_strategies": total,
    }
