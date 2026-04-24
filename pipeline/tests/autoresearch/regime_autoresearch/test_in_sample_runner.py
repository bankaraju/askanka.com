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
    result = run_in_sample(p, panel, log_path=tmp_path / "proposal_log.jsonl",
                           incumbent_sharpe=0.0)
    assert "net_sharpe_in_sample" in result
    assert "transaction_cost_bps" in result
    assert result["gap_vs_incumbent"] == result["net_sharpe_in_sample"] - 0.0


def test_append_proposal_log_is_jsonl(tmp_path):
    log = tmp_path / "proposal_log.jsonl"
    entry = {"proposal_id": "P-000001", "net_sharpe_in_sample": 0.1, "result": "rejected_in_sample"}
    append_proposal_log(log, entry)
    append_proposal_log(log, {**entry, "proposal_id": "P-000002"})
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["proposal_id"] == "P-000001"
