"""Tests for etf_reoptimize.load_indian_data() — Indian market data loader."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure pipeline/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_indian_data_returns_dict(tmp_path):
    """load_indian_data() returns a dict with fii_net, india_vix, nifty_close
    populated from minimal daily + flows JSON fixtures."""
    from autoresearch.etf_reoptimize import load_indian_data

    # --- build daily fixture ---
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    daily_payload = {
        "date": "2026-04-17",
        "indices": {
            "Nifty 50": {"close": 24353.55},
            "INDIA VIX": {"close": 17.205},
        },
        "volatility": {},
        "stocks": {},
        "fx": {},
        "commodities": {},
        "sector_etfs": {},
    }
    (daily_dir / "2026-04-17.json").write_text(json.dumps(daily_payload))

    # --- build flows fixture ---
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    flows_payload = {
        "date": "17-Apr-2026",
        "fii_equity_net": 683.2,
        "dii_equity_net": -4721.48,
        "source": "nse_fiidiiTradeReact",
    }
    (flows_dir / "2026-04-17.json").write_text(json.dumps(flows_payload))

    result = load_indian_data(daily_dir=daily_dir, flows_dir=flows_dir)

    assert isinstance(result, dict), "load_indian_data() must return a dict"
    assert "fii_net" in result, "Result must contain 'fii_net'"
    assert "india_vix" in result, "Result must contain 'india_vix'"
    assert "nifty_close" in result, "Result must contain 'nifty_close'"

    assert result["fii_net"] == 683.2
    assert result["india_vix"] == 17.205
    assert result["nifty_close"] == 24353.55
    assert result["dii_net"] == -4721.48


def test_load_indian_data_handles_missing_files(tmp_path):
    """load_indian_data() returns a dict with None values when dirs are empty."""
    from autoresearch.etf_reoptimize import load_indian_data

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    positioning_path = tmp_path / "positioning.json"
    # positioning.json intentionally absent

    result = load_indian_data(
        daily_dir=daily_dir,
        flows_dir=flows_dir,
        positioning_path=positioning_path,
    )

    assert isinstance(result, dict), "load_indian_data() must return a dict"
    for key in ("fii_net", "india_vix", "nifty_close"):
        assert key in result, f"Result must contain '{key}'"
        assert result[key] is None, f"'{key}' should be None when files are missing"


def test_optimize_weights_returns_valid_structure():
    from autoresearch.etf_reoptimize import optimize_weights
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=100, freq="B")
    features = pd.DataFrame(
        np.random.randn(100, 5),
        index=dates,
        columns=["etf_a", "etf_b", "etf_c", "fii_net", "india_vix"],
    )
    target = pd.Series(np.random.choice([1, -1], size=100), index=dates)
    result = optimize_weights(features, target, n_iterations=50)
    assert "optimal_weights" in result
    assert "best_accuracy" in result
    assert "best_sharpe" in result
    assert isinstance(result["optimal_weights"], dict)
    assert len(result["optimal_weights"]) > 0
    assert result["best_accuracy"] >= 0
    assert result["best_accuracy"] <= 100


def test_optimize_weights_beats_baseline():
    from autoresearch.etf_reoptimize import optimize_weights
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=200, freq="B")
    target = pd.Series(np.random.choice([1, -1], size=200), index=dates)
    signal = target.astype(float) + np.random.randn(200) * 0.5
    features = pd.DataFrame({"signal": signal, "noise": np.random.randn(200)}, index=dates)
    result = optimize_weights(features, target, n_iterations=100)
    assert result["best_accuracy"] > result["baseline"]


def test_run_reoptimize_saves_files(tmp_path):
    from pipeline.autoresearch.etf_reoptimize import run_reoptimize
    weights_path = tmp_path / "etf_optimal_weights.json"
    trade_map_path = tmp_path / "regime_trade_map.json"
    existing_map = {
        "results": {"NEUTRAL": {"Defence vs IT": {"spread": "Defence vs IT", "1d_win": 57.0, "1d_avg": 0.24, "3d_win": 58.0, "3d_avg": 0.66, "5d_win": 59.0, "5d_avg": 1.03, "best_period": 5, "best_win": 59.0}}},
        "today_zone": "NEUTRAL",
        "transitions": 266,
    }
    trade_map_path.write_text(json.dumps(existing_map))
    result = run_reoptimize(weights_path=weights_path, trade_map_path=trade_map_path, n_iterations=50, dry_run=False)
    assert result["status"] == "saved"
    assert weights_path.exists()
    saved = json.loads(weights_path.read_text())
    assert "optimal_weights" in saved
    assert "timestamp" in saved
    assert "indian_inputs" in saved


def test_run_reoptimize_dry_run_does_not_save(tmp_path):
    from pipeline.autoresearch.etf_reoptimize import run_reoptimize
    weights_path = tmp_path / "etf_optimal_weights.json"
    trade_map_path = tmp_path / "regime_trade_map.json"
    trade_map_path.write_text(json.dumps({"results": {}, "today_zone": "NEUTRAL"}))
    result = run_reoptimize(weights_path=weights_path, trade_map_path=trade_map_path, n_iterations=50, dry_run=True)
    assert result["status"] == "dry_run"
    assert not weights_path.exists()
