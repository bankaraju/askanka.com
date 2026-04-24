"""Smoke test for reanalyze_log — stubs panel+run_in_sample and confirms
main() prints something and doesn't error on a 1-row mocked log.
"""
from __future__ import annotations

import json

import pandas as pd

from pipeline.autoresearch.regime_autoresearch.scripts import (
    reanalyze_log,
    run_pilot,
)
from pipeline.autoresearch.regime_autoresearch import in_sample_runner as isr


def test_reanalyze_smoke(monkeypatch, tmp_path, capsys):
    log = tmp_path / "proposal_log.jsonl"
    log.write_text(
        json.dumps({
            "proposal_id": "P-smoke",
            "regime": "NEUTRAL",
            "approval_status": "APPROVED",
            "construction_type": "long_short_basket",
            "feature": "ret_5d",
            "threshold_op": "top_k",
            "threshold_value": 10,
            "hold_horizon": 5,
            "pair_id": None,
            "passes_delta_in": False,
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reanalyze_log, "LOG_PATH", log)
    monkeypatch.setattr(
        run_pilot, "_build_panel",
        lambda: pd.DataFrame([{
            "date": pd.Timestamp("2022-01-03"), "ticker": "X",
            "close": 100.0, "volume": 1_000_000, "regime_zone": "NEUTRAL",
        }]),
    )
    monkeypatch.setattr(
        run_pilot, "_get_event_dates",
        lambda panel, regime: pd.DatetimeIndex([pd.Timestamp("2022-01-03")]),
    )
    monkeypatch.setattr(
        run_pilot, "_compute_hurdle",
        lambda regime, panel=None, event_dates=None, hold_horizon=1: (
            0.0, "scarcity_fallback:buy_and_hold"
        ),
    )
    monkeypatch.setattr(
        isr, "run_in_sample",
        lambda p, panel, log_path, incumbent_sharpe,
               event_dates=None, tickers=None, n_folds=4: {
            "net_sharpe_in_sample": 0.42,
            "n_events_in_sample": 48,
            "fold_sharpes": [0.4, 0.44, 0.42, 0.43],
            "fold_n_events": [12, 12, 12, 12],
            "insufficient_for_folds": False,
        },
    )
    monkeypatch.setattr(
        reanalyze_log, "run_in_sample",
        lambda p, panel, log_path, incumbent_sharpe,
               event_dates=None, tickers=None, n_folds=4: {
            "net_sharpe_in_sample": 0.42,
            "n_events_in_sample": 48,
            "fold_sharpes": [0.4, 0.44, 0.42, 0.43],
            "fold_n_events": [12, 12, 12, 12],
            "insufficient_for_folds": False,
        },
    )
    rc = reanalyze_log.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Evaluating 1 historical APPROVED proposals" in out
    assert "Summary:" in out
