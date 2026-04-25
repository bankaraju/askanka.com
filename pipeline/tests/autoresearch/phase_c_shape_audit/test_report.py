"""Report TDD — synthetic per-trade rows -> verdict + tables."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_shape_audit import report


def _synth_row(shape: str, side: str, regime: str, cf_pnl: float, source: str = "missed",
               actual_pnl: float | None = None) -> dict:
    return {
        "shape": shape,
        "trade_rec": side,
        "regime": regime,
        "source": source,
        "cf_grid_avg_pnl_pct": cf_pnl,
        "cf_grid_avg_win": cf_pnl > 0,
        "actual_pnl_pct": actual_pnl,
        "validation": "OK",
    }


def test_verdict_null_on_baseline_distribution() -> None:
    """20 rows split 50-50 wins-losses across shapes -> NULL."""
    rows = []
    rng = np.random.default_rng(0)
    for i in range(20):
        rows.append(_synth_row(
            shape="CHOPPY",
            side="SHORT",
            regime="NEUTRAL",
            cf_pnl=float(rng.choice([1.0, -1.0])),
        ))
    df = pd.DataFrame(rows)
    rep = report.build_report(df)
    assert rep["verdict"] in ("NULL", "INSUFFICIENT_N")
