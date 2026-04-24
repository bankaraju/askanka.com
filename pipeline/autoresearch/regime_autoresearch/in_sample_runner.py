"""In-sample backtest per proposal. Writes proposal_log.jsonl rows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance.slippage_grid import apply_level, LEVELS
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal


def _backtest_returns_stub(p: Proposal, panel: pd.DataFrame) -> pd.Series:
    """Plumbing stub — returns empty series.

    Exercises the slippage_grid + proposal_log write path without depending on
    the full grammar-to-backtest compiler. The compiler is implemented in
    Task 8 step 2 (after the pilot smoke run confirms plumbing is live).
    This stub keeps Task 2 testable without a 500-line compiler block.
    """
    dates = panel[panel["regime_zone"] == p.regime]["date"].unique()
    return pd.Series([0.0] * len(dates))


def _net_sharpe(event_rets_pct: pd.Series, level: str = "S1",
                 hold_horizon: int = 1) -> float:
    """Net Sharpe after applying the slippage_grid level, annualized by
    hold_horizon.

    A 5-day hold produces ~sqrt(252/5) × per-event-Sharpe, not sqrt(252).
    For the Task 2 stub (all returns = 0) this has no effect; matters when
    Task 8's compiler swaps in real returns.
    """
    if event_rets_pct.empty:
        return 0.0
    if hold_horizon < 1:
        raise ValueError(f"hold_horizon must be >= 1; got {hold_horizon}")
    ledger = pd.DataFrame({"trade_ret_pct": event_rets_pct.values,
                            "ticker": "NA", "direction": 1})
    net = apply_level(ledger, level)["net_ret_pct"].astype(float)
    if net.std() == 0:
        return 0.0
    periods_per_year = 252 / hold_horizon
    return float(net.mean() / net.std() * np.sqrt(periods_per_year))


def run_in_sample(p: Proposal, panel: pd.DataFrame, log_path: Path,
                  incumbent_sharpe: float) -> dict[str, Any]:
    """Run one proposal end-to-end in-sample and persist the row.

    The result dict is appended to log_path as a single JSONL row before being
    returned. Orchestrators that want the result without persistence should call
    _backtest_returns_stub / _net_sharpe directly.
    """
    event_rets = _backtest_returns_stub(p, panel)
    net_sharpe = _net_sharpe(event_rets, "S1", hold_horizon=p.hold_horizon)
    gap = net_sharpe - incumbent_sharpe
    result = {
        "net_sharpe_in_sample": round(net_sharpe, 4),
        "n_events_in_sample": int(len(event_rets)),
        "transaction_cost_bps": int(LEVELS["S1"] * 100),
        "incumbent_sharpe": round(incumbent_sharpe, 4),
        "gap_vs_incumbent": round(gap, 4),
        "regime": p.regime,
        "feature": p.feature,
        "threshold_op": p.threshold_op,
        "threshold_value": p.threshold_value,
        "hold_horizon": p.hold_horizon,
        "construction_type": p.construction_type,
        "pair_id": p.pair_id,
    }
    append_proposal_log(log_path, result)
    return result


def append_proposal_log(log_path: Path, entry: dict) -> None:
    """Append a single row to proposal_log.jsonl (append-only)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("timestamp_iso", datetime.now(timezone.utc).isoformat())
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
