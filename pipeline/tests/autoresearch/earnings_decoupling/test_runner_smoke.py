"""Synthetic end-to-end smoke test for runner.run."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling import runner


def test_run_smoke_writes_all_artifacts(tmp_path, monkeypatch):
    out = tmp_path / "run"
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=400)
    prices = pd.DataFrame({
        sym: np.cumprod(1 + rng.normal(0.0005, 0.01, 400)) * 1000
        for sym in ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    }, index=dates)
    sector_idx = pd.DataFrame({
        sym: np.cumprod(1 + rng.normal(0, 0.005, 400)) * 50000
        for sym in ["BANKNIFTY", "NIFTYIT"]
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + rng.normal(0, 0.3, 400), index=dates)
    fno_history = [{"date": "2024-01-01",
                    "symbols": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]}]
    peers_map = {
        "RELIANCE": ["HDFCBANK", "ICICIBANK"],
        "TCS": ["INFY"],
        "INFY": ["TCS"],
        "HDFCBANK": ["RELIANCE", "ICICIBANK"],
        "ICICIBANK": ["RELIANCE", "HDFCBANK"],
    }
    sector_map = {
        "RELIANCE": "BANKNIFTY", "HDFCBANK": "BANKNIFTY", "ICICIBANK": "BANKNIFTY",
        "TCS": "NIFTYIT", "INFY": "NIFTYIT",
    }
    events = pd.DataFrame([
        {"symbol": "RELIANCE", "event_date": dates[300].strftime("%Y-%m-%d")},
        {"symbol": "TCS", "event_date": dates[310].strftime("%Y-%m-%d")},
        {"symbol": "INFY", "event_date": dates[320].strftime("%Y-%m-%d")},
    ])
    runner.run(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
        out_dir=out, hypothesis_id="H-2026-04-25-001-TEST",
        n_permutations=500, smoke=True, fragility=False,
    )
    assert (out / "manifest.json").exists()
    assert (out / "trade_ledger.csv").exists()
    assert (out / "events_ledger.csv").exists()
    assert (out / "metrics_grid.json").exists()
    assert (out / "comparators.json").exists()
    assert (out / "gate_checklist.json").exists()
    assert (out / "verdict.md").exists()
    gc = json.loads((out / "gate_checklist.json").read_text())
    assert gc["decision"] in {"PASS", "PARTIAL", "FAIL"}
