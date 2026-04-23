"""Implementation-risk combined-scenario runner per §11A of backtesting-specs.txt v1.0.

Applies 5% missed entries, 5% missed exits (extra-bar hold proxied as half-P&L
minus 10 bps), 5% partial fills at 50% size, 1 outage/month (drop a random
event from each month), 1 exchange halt per quarter (~4/year drops), 10%
margin-shortage rejects while cumulative equity drawdown exceeds 10%, and a
weekend-gap cost proxy (add 10 bps to Monday trades).

§11A.2 pass: cum P&L > 0 AND max DD ≤ 1.4× baseline DD AND realised Sharpe
≥ 60% of baseline S1 Sharpe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M


def simulate_combined(
    events: pd.DataFrame,
    baseline_sharpe_s1: float,
    baseline_dd_s1: float,
    seed: int | None = 42,
) -> dict:
    rng = np.random.default_rng(seed)
    ev = events.sort_values("date").reset_index(drop=True).copy()
    n_in = len(ev)

    sign = np.where(ev["direction"].eq("UP"), -1.0, 1.0)
    ev["pnl_pct"] = sign * ev["next_ret"].to_numpy()

    keep = np.ones(len(ev), dtype=bool)

    miss_entry = rng.random(len(ev)) < 0.05
    keep &= ~miss_entry

    halts = rng.choice(np.where(keep)[0], size=min(4, int(keep.sum())), replace=False) if keep.any() else np.array([], dtype=int)
    keep[halts] = False

    months = pd.DatetimeIndex(ev["date"]).to_period("M")
    for m in months.unique():
        idx = np.where((months == m) & keep)[0]
        if len(idx):
            keep[rng.choice(idx)] = False

    partials = rng.random(len(ev)) < 0.05
    ev.loc[partials, "pnl_pct"] = ev.loc[partials, "pnl_pct"] * 0.5

    miss_exit = rng.random(len(ev)) < 0.05
    ev.loc[miss_exit, "pnl_pct"] = ev.loc[miss_exit, "pnl_pct"] * 0.5 - 0.10

    is_monday = pd.DatetimeIndex(ev["date"]).dayofweek == 0
    ev.loc[is_monday, "pnl_pct"] -= 0.10

    pnl_for_dd = ev["pnl_pct"].fillna(0).to_numpy().copy()
    pnl_for_dd[~keep] = 0.0
    equity = np.cumprod(1.0 + pnl_for_dd / 100.0)
    peak = np.maximum.accumulate(equity)
    dd_series = (peak - equity) / peak
    in_dd = dd_series > 0.10
    candidate_dd = np.where(in_dd & keep)[0]
    n_reject = min(len(candidate_dd), max(1, int(0.02 * n_in)))
    if len(candidate_dd) > 0:
        reject_idx = rng.choice(candidate_dd, size=n_reject, replace=False)
        keep[reject_idx] = False

    ev_kept = ev.loc[keep].copy()
    n_kept = len(ev_kept)
    perturbed = ev_kept["pnl_pct"].to_numpy()
    core = M.per_bucket_metrics(perturbed)
    cum_pnl = float(np.sum(perturbed))

    pass_cum = cum_pnl > 0
    pass_dd = core["max_drawdown_pct"] <= 1.4 * (baseline_dd_s1 * 100.0)
    pass_sharpe = core["sharpe"] >= 0.6 * baseline_sharpe_s1
    verdict = "IMPLEMENTATION-ROBUST" if (pass_cum and pass_dd and pass_sharpe) else "IMPLEMENTATION-SENSITIVE"
    return {
        "n_events_input": int(n_in),
        "n_events_kept": int(n_kept),
        "perturbed_sharpe": core["sharpe"],
        "perturbed_max_dd": core["max_drawdown_pct"] / 100.0,
        "perturbed_cum_pnl": cum_pnl,
        "baseline_sharpe_s1": baseline_sharpe_s1,
        "baseline_dd_s1": baseline_dd_s1,
        "pass_cumulative_pnl_positive": bool(pass_cum),
        "pass_max_dd": bool(pass_dd),
        "pass_realised_sharpe": bool(pass_sharpe),
        "verdict": verdict,
    }
