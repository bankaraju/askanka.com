"""Tests for fingerprint card generator."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


SAMPLE_BACKTEST = {
    "BB_SQUEEZE": {
        "occurrences": 18, "direction": "LONG",
        "win_rate_5d": 0.72, "avg_return_5d": 2.8, "avg_return_10d": 4.1,
        "min_return_5d": -3.1, "last_occurrence": "2026-03-12",
    },
    "DMA200_CROSS_UP": {
        "occurrences": 4, "direction": "LONG",
        "win_rate_5d": 0.50, "avg_return_5d": 1.2, "avg_return_10d": 1.8,
        "min_return_5d": -2.0, "last_occurrence": "2025-11-03",
    },
    "RSI_OVERSOLD_BOUNCE": {
        "occurrences": 12, "direction": "LONG",
        "win_rate_5d": 0.58, "avg_return_5d": 1.5, "avg_return_10d": 2.2,
        "min_return_5d": -1.8, "last_occurrence": "2026-02-10",
    },
    "MACD_CROSS_UP": {
        "occurrences": 3, "direction": "LONG",
        "win_rate_5d": 0.33, "avg_return_5d": -0.5, "avg_return_10d": 0.1,
        "min_return_5d": -4.0, "last_occurrence": "2025-06-01",
    },
}


def test_generate_fingerprint_filters_significant():
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    patterns = {p["pattern"] for p in card["fingerprint"]}
    assert "BB_SQUEEZE" in patterns
    assert "RSI_OVERSOLD_BOUNCE" in patterns
    assert "DMA200_CROSS_UP" not in patterns  # 4 occ → below threshold
    assert "MACD_CROSS_UP" not in patterns    # 3 occ, 33%


def test_significance_levels():
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    by_pattern = {p["pattern"]: p for p in card["fingerprint"]}
    assert by_pattern["BB_SQUEEZE"]["significance"] == "STRONG"
    assert by_pattern["RSI_OVERSOLD_BOUNCE"]["significance"] == "MODERATE"


def test_personality_classification():
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    assert card["personality"] == "momentum_breakout"
    assert card["best_pattern"] == "BB_SQUEEZE"


def test_empty_backtest_returns_agnostic():
    from ta_fingerprint import generate_fingerprint
    card = generate_fingerprint("UNKNOWN", {}, data_points=1247)
    assert card["personality"] == "pattern_agnostic"
    assert card["significant_patterns"] == 0


def test_fingerprint_writes_json(tmp_path: Path):
    from ta_fingerprint import generate_fingerprint, save_fingerprint
    card = generate_fingerprint("HAL", SAMPLE_BACKTEST, data_points=1247)
    save_fingerprint(card, output_dir=tmp_path)
    path = tmp_path / "HAL.json"
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["symbol"] == "HAL"
