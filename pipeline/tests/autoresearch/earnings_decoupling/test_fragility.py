import numpy as np
import pandas as pd

from pipeline.autoresearch.earnings_decoupling.fragility import evaluate


def test_evaluate_returns_verdict_one_of_three(tmp_path):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=400)
    prices = pd.DataFrame({
        s: np.cumprod(1 + rng.normal(0.0005, 0.01, 400)) * 1000
        for s in ["RELIANCE", "HDFCBANK", "ICICIBANK"]
    }, index=dates)
    sector_idx = pd.DataFrame({
        "BANKNIFTY": np.cumprod(1 + rng.normal(0, 0.005, 400)) * 50000,
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + rng.normal(0, 0.3, 400), index=dates)
    fno_history = [{"date": "2024-01-01", "symbols": ["RELIANCE", "HDFCBANK", "ICICIBANK"]}]
    peers_map = {"RELIANCE": ["HDFCBANK", "ICICIBANK"]}
    sector_map = {"RELIANCE": "BANKNIFTY"}
    events = pd.DataFrame([{"symbol": "RELIANCE", "event_date": dates[300].strftime("%Y-%m-%d")}])
    out = evaluate(events=events, prices=prices, sector_idx=sector_idx, vix=vix,
                    fno_history=fno_history, peers_map=peers_map, sector_map=sector_map)
    assert out["verdict"] in {"PARAMETER-FRAGILE", "STABLE", "INSUFFICIENT_DATA"}
    assert "rows" in out
