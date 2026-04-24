"""In-sample runner exercises slippage-grid + proposal log."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    run_in_sample, append_proposal_log,
)


def _synthetic_setup(tmp_path):
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2022-01-01", periods=500)
    tickers = [f"T{i}" for i in range(8)]
    rows = [{"date": d, "ticker": t, "close": 100 + rng.standard_normal() * 5,
             "volume": 1e6, "regime_zone": "NEUTRAL"}
            for d in dates for t in tickers]
    return pd.DataFrame(rows)


def test_run_in_sample_returns_net_sharpe(tmp_path):
    panel = _synthetic_setup(tmp_path)
    p = Proposal("single_long", "ret_5d", ">", 0.5, 5, "NEUTRAL", None)
    log_path = tmp_path / "proposal_log.jsonl"
    result = run_in_sample(p, panel, log_path=log_path, incumbent_sharpe=0.0)
    assert "net_sharpe_in_sample" in result
    assert "transaction_cost_bps" in result
    assert result["gap_vs_incumbent"] == result["net_sharpe_in_sample"] - 0.0
    # Issue 1 fix: log_path is now honoured
    assert log_path.exists(), "run_in_sample must persist to log_path"
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["feature"] == "ret_5d"
    assert row["regime"] == "NEUTRAL"
    assert row["hold_horizon"] == 5


def test_net_sharpe_annualization_scales_with_hold_horizon():
    # Same event-level returns, different hold horizons → different annualized Sharpe
    from pipeline.autoresearch.regime_autoresearch.in_sample_runner import _net_sharpe
    rng = np.random.default_rng(1)
    rets = pd.Series(rng.normal(0.02, 1.0, 100))  # non-zero mean, non-zero std
    s_1d = _net_sharpe(rets, level="S1", hold_horizon=1)
    s_5d = _net_sharpe(rets, level="S1", hold_horizon=5)
    s_20d = _net_sharpe(rets, level="S1", hold_horizon=20)
    # 5d Sharpe should be ~sqrt(5) smaller than 1d; 20d ~sqrt(20) smaller
    assert abs(s_1d / s_5d - np.sqrt(5)) < 0.01, f"ratio 1d/5d was {s_1d/s_5d}, expected ~sqrt(5)"
    assert abs(s_1d / s_20d - np.sqrt(20)) < 0.01, f"ratio 1d/20d was {s_1d/s_20d}, expected ~sqrt(20)"


def test_append_proposal_log_is_jsonl(tmp_path):
    log = tmp_path / "proposal_log.jsonl"
    entry = {"proposal_id": "P-000001", "net_sharpe_in_sample": 0.1, "result": "rejected_in_sample"}
    append_proposal_log(log, entry)
    append_proposal_log(log, {**entry, "proposal_id": "P-000002"})
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["proposal_id"] == "P-000001"
