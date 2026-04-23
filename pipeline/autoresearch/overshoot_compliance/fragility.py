"""Parameter-fragility sweep per §9A of backtesting-specs.txt v1.0.

Evaluates a 3×3×3 neighborhood around the chosen (min_z, roll_window,
cost_pct). Events for each roll_window must be precomputed by the caller
(runner.py) and passed in as `events_by_window`.
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from . import metrics as M


MIN_Z_GRID = (2.5, 3.0, 3.5)
WINDOW_GRID = (15, 20, 25)
COST_GRID = (0.25, 0.30, 0.35)


def neighborhood_grid() -> list[dict]:
    return [
        {"min_z": z, "roll_window": w, "cost_pct": c}
        for z, w, c in product(MIN_Z_GRID, WINDOW_GRID, COST_GRID)
    ]


def _edge_for(events: pd.DataFrame, min_z: float, cost_pct: float) -> dict:
    sel = events.loc[events["z"].abs() >= min_z].copy()
    if sel.empty:
        return {"n_trades": 0, "mean_ret_pct": 0.0, "sharpe": 0.0}
    sign = np.where(sel["direction"].eq("UP"), -1.0, 1.0)
    gross = sign * sel["next_ret"].to_numpy()
    net = gross - cost_pct
    return M.per_bucket_metrics(net)


def evaluate(events_by_window: dict[int, pd.DataFrame], chosen: dict) -> dict:
    rows = []
    chosen_metrics = _edge_for(
        events_by_window[chosen["roll_window"]],
        chosen["min_z"], chosen["cost_pct"],
    )
    chosen_sharpe = chosen_metrics["sharpe"]
    chosen_mean = chosen_metrics["mean_ret_pct"]
    for params in neighborhood_grid():
        m = _edge_for(
            events_by_window[params["roll_window"]],
            params["min_z"], params["cost_pct"],
        )
        rows.append({**params, **m})

    df = pd.DataFrame(rows)
    n = len(df)
    pct_pos = float((df["mean_ret_pct"] > 0).sum()) / n * 100.0
    med_sharpe = float(df["sharpe"].median())
    sharpe_ratio = (med_sharpe / chosen_sharpe * 100.0) if chosen_sharpe else 0.0
    chosen_sign = np.sign(chosen_mean)
    sign_flip_pct = float((np.sign(df["mean_ret_pct"]) == -chosen_sign).sum()) / n * 100.0

    stable_positive = pct_pos >= 60.0
    stable_sharpe = sharpe_ratio >= 70.0
    stable_sign = sign_flip_pct < 50.0

    verdict = "STABLE" if (stable_positive and stable_sharpe and stable_sign) else "PARAMETER-FRAGILE"

    return {
        "chosen": chosen,
        "chosen_sharpe": chosen_sharpe,
        "chosen_mean_ret_pct": chosen_mean,
        "neighbor_rows": rows,
        "pct_positive_pnl": round(pct_pos, 2),
        "median_sharpe_ratio": round(sharpe_ratio, 2),
        "sign_flip_pct": round(sign_flip_pct, 2),
        "stable_positive": stable_positive,
        "stable_sharpe": stable_sharpe,
        "stable_sign": stable_sign,
        "verdict": verdict,
    }
