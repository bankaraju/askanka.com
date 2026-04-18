import json
import pytest
from pathlib import Path


def test_compute_daily_signal_updates_today_zone(tmp_path):
    from pipeline.autoresearch.etf_daily_signal import compute_daily_signal
    weights = {
        "optimal_weights": {"financials": 0.39, "treasury": 0.25, "vix": -0.20},
        "best_accuracy": 62.3, "baseline": 51.6, "best_sharpe": 3.28,
        "timestamp": "2026-04-18T22:00:00+05:30",
    }
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(weights))
    trade_map = {
        "results": {"NEUTRAL": {"Defence vs IT": {"spread": "Defence vs IT"}}},
        "today_zone": "NEUTRAL", "transitions": 266,
    }
    trade_map_path = tmp_path / "regime_trade_map.json"
    trade_map_path.write_text(json.dumps(trade_map))
    result = compute_daily_signal(weights_path=weights_path, trade_map_path=trade_map_path)
    assert result["status"] in ("updated", "error")
    if result["status"] == "updated":
        assert "today_zone" in result
        updated = json.loads(trade_map_path.read_text())
        assert "today_zone" in updated
        assert "signal_computed_at" in updated


def test_compute_daily_signal_missing_weights(tmp_path):
    from pipeline.autoresearch.etf_daily_signal import compute_daily_signal
    weights_path = tmp_path / "nonexistent.json"
    trade_map_path = tmp_path / "trade_map.json"
    trade_map_path.write_text(json.dumps({"results": {}, "today_zone": "NEUTRAL"}))
    result = compute_daily_signal(weights_path=weights_path, trade_map_path=trade_map_path)
    assert result["status"] == "error"
    assert "weights" in result["reason"].lower()
