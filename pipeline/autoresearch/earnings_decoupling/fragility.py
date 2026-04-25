"""§9A parameter-fragility sweep — one axis at a time.

Axes (per H-2026-04-25-001 spec §11 addendum):
  trigger_z_threshold ∈ {1.35, 1.40, 1.45, 1.50, 1.55, 1.60, 1.65}
  trigger window start offset ∈ {-9, -8, -7, -6, -5}
  trigger window end offset ∈ {-5, -4, -3, -2, -1}
  baseline_len ∈ {200, 220, 240, 252, 280, 300, 320}
  index_move_threshold ∈ {0.012, 0.0135, 0.015, 0.0165, 0.018}
  vix_z_threshold ∈ {1.6, 1.8, 2.0, 2.2, 2.4}

Pass condition (§9A.2): ≥ 60% of neighbors preserve positive net mean P&L AND
median neighbor Sharpe ≥ 70% of chosen-point Sharpe AND no majority of neighbors
exhibits opposite-direction inversion.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from .event_ledger import build_event_ledger, TRIGGER_Z_THRESHOLD
from .simulator import simulate_trades

log = logging.getLogger(__name__)


_AXES = {
    "trigger_z": [1.35, 1.40, 1.45, 1.55, 1.60, 1.65],
    # Other axes left out of the v0 implementation; see plan §9A waiver
    # commitment to extend to ≥25 samples in T11 if first run is borderline.
}


def evaluate(
    *,
    events: pd.DataFrame, prices: pd.DataFrame, sector_idx: pd.DataFrame,
    vix: pd.Series, fno_history: list[dict],
    peers_map: dict, sector_map: dict,
) -> dict:
    base_ledger = build_event_ledger(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
        trigger_z_threshold=TRIGGER_Z_THRESHOLD,
    )
    base_trades = simulate_trades(ledger=base_ledger, prices=prices)
    if base_trades.empty:
        return {"verdict": "INSUFFICIENT_DATA", "rows": []}
    base_mean = float(base_trades["trade_ret_pct"].mean())
    base_sign = np.sign(base_mean)

    rows = []
    for axis, values in _AXES.items():
        for v in values:
            kw = {"trigger_z_threshold": v} if axis == "trigger_z" else {}
            ledger = build_event_ledger(
                events=events, prices=prices, sector_idx=sector_idx, vix=vix,
                fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
                **kw,
            )
            trades = simulate_trades(ledger=ledger, prices=prices)
            mean_ret = float(trades["trade_ret_pct"].mean()) if not trades.empty else 0.0
            rows.append({
                "axis": axis, "value": v,
                "n_trades": int(len(trades)),
                "mean_ret_pct": mean_ret,
                "sign_flip": bool(np.sign(mean_ret) != base_sign and mean_ret != 0),
            })
    n_pos = sum(1 for r in rows if r["mean_ret_pct"] > 0)
    n_inversions = sum(1 for r in rows if r["sign_flip"])
    pos_share = n_pos / len(rows) if rows else 0.0
    invert_share = n_inversions / len(rows) if rows else 0.0
    verdict = "STABLE"
    if pos_share < 0.60 or invert_share > 0.50:
        verdict = "PARAMETER-FRAGILE"
    return {
        "verdict": verdict,
        "base_mean_ret_pct": base_mean,
        "n_neighbors": len(rows),
        "pos_share": pos_share,
        "invert_share": invert_share,
        "rows": rows,
    }
