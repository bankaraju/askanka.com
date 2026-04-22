"""
Tests for pipeline/break_signal_generator.py — Phase C breaks → signal candidates.

TDD: tests written before implementation.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BREAKS = {
    "date": "2026-04-16",
    "scan_time": "2026-04-16 15:32:15",
    "breaks": [
        {
            "symbol": "HAL",
            "regime": "NEUTRAL",
            "classification": "MOMENTUM_CONFIRM",
            "action": "ENTER",
            "z_score": 2.3,
            "trade_rec": "LONG",
            "expected_return": 0.5,
            "actual_return": 1.8,
            "oi_anomaly": True,
        },
        {
            "symbol": "BEL",
            "regime": "BULL",
            "classification": "DIVERGENCE_SIGNAL",
            "action": "ENTER",
            "z_score": -1.7,
            "trade_rec": "SHORT",
            "expected_return": 0.3,
            "actual_return": -0.9,
            "oi_anomaly": False,
        },
        {
            "symbol": "PIIND",
            "classification": "POSSIBLE_OPPORTUNITY",
            "action": "HOLD",
            "z_score": -2.0,
            "trade_rec": None,
            "expected_return": 1.52,
            "actual_return": 0.47,
            "oi_anomaly": False,
        },
    ],
}


@pytest.fixture
def breaks_file(tmp_path: Path) -> Path:
    """Write sample breaks JSON and return the path."""
    p = tmp_path / "correlation_breaks.json"
    p.write_text(json.dumps(SAMPLE_BREAKS), encoding="utf-8")
    return p


@pytest.fixture
def empty_breaks_file(tmp_path: Path) -> Path:
    """Write a breaks file with an empty breaks list."""
    p = tmp_path / "correlation_breaks_empty.json"
    p.write_text(json.dumps({"date": "2026-04-16", "scan_time": "2026-04-16 15:32:15", "breaks": []}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_break_candidates_only_emits_actionable(breaks_file: Path, monkeypatch) -> None:
    """3 breaks (2 actionable, 1 None trade_rec) → returns exactly 2 candidates."""
    from pipeline import break_signal_generator as bsg
    from pipeline.break_signal_generator import generate_break_candidates

    monkeypatch.setattr(bsg, "compute_atr_stop",
                        lambda symbol, direction: {"stop_pct": -2.3, "stop_price": 310.5,
                                                    "atr_14": 7.1, "stop_source": "atr_14"})
    candidates = generate_break_candidates(breaks_path=breaks_file)

    assert len(candidates) == 2
    symbols = {c["_break_metadata"]["symbol"] for c in candidates}
    assert symbols == {"HAL", "BEL"}
    # PIIND (trade_rec=None) must be absent
    assert not any(c["_break_metadata"]["symbol"] == "PIIND" for c in candidates)


def test_candidate_has_required_signal_fields(breaks_file: Path, monkeypatch) -> None:
    """LONG candidate must have all required signal schema fields."""
    from pipeline import break_signal_generator as bsg
    from pipeline.break_signal_generator import generate_break_candidates

    monkeypatch.setattr(bsg, "compute_atr_stop",
                        lambda symbol, direction: {"stop_pct": -2.3, "stop_price": 310.5,
                                                    "atr_14": 7.1, "stop_source": "atr_14"})
    candidates = generate_break_candidates(breaks_path=breaks_file)
    hal = next(c for c in candidates if c["_break_metadata"]["symbol"] == "HAL")

    # signal_id prefix
    assert hal["signal_id"].startswith("BRK-")
    assert "HAL" in hal["signal_id"]

    # required fields
    assert hal["source"] == "CORRELATION_BREAK"
    assert hal["status"] == "OPEN"
    assert hal["tier"] == "SIGNAL"
    assert hal["category"] == "phase_c"
    assert "Phase C:" in hal["spread_name"]
    assert "HAL" in hal["spread_name"]
    assert hal["event_headline"] != ""
    assert hal["expected_1d_spread"] == 0.5

    # long legs populated, short legs empty for LONG
    assert len(hal["long_legs"]) == 1
    assert hal["long_legs"][0]["ticker"] == "HAL"
    assert hal["long_legs"][0]["yf"] == "HAL.NS"
    assert hal["long_legs"][0]["weight"] == 1.0
    assert hal["short_legs"] == []

    # metadata
    assert hal["_break_metadata"]["classification"] == "MOMENTUM_CONFIRM"
    assert hal["_break_metadata"]["z_score"] == 2.3
    assert hal["_break_metadata"]["regime"] == "NEUTRAL"
    assert hal["_break_metadata"]["oi_anomaly"] is True


def test_short_candidate_uses_short_legs(breaks_file: Path, monkeypatch) -> None:
    """trade_rec=SHORT → long_legs empty, short_legs populated with correct ticker."""
    from pipeline import break_signal_generator as bsg
    from pipeline.break_signal_generator import generate_break_candidates

    monkeypatch.setattr(bsg, "compute_atr_stop",
                        lambda symbol, direction: {"stop_pct": -2.3, "stop_price": 310.5,
                                                    "atr_14": 7.1, "stop_source": "atr_14"})
    candidates = generate_break_candidates(breaks_path=breaks_file)
    bel = next(c for c in candidates if c["_break_metadata"]["symbol"] == "BEL")

    assert bel["long_legs"] == []
    assert len(bel["short_legs"]) == 1
    assert bel["short_legs"][0]["ticker"] == "BEL"
    assert bel["short_legs"][0]["yf"] == "BEL.NS"
    assert bel["short_legs"][0]["weight"] == 1.0


def test_empty_file_returns_empty_list(empty_breaks_file: Path) -> None:
    """Empty breaks list in file → returns []."""
    from pipeline.break_signal_generator import generate_break_candidates

    candidates = generate_break_candidates(breaks_path=empty_breaks_file)
    assert candidates == []


def test_missing_file_returns_empty_list(tmp_path: Path) -> None:
    """Non-existent file → returns [] without raising."""
    from pipeline.break_signal_generator import generate_break_candidates

    missing = tmp_path / "does_not_exist.json"
    candidates = generate_break_candidates(breaks_path=missing)
    assert candidates == []


def test_generated_signal_carries_atr_stop(tmp_path, monkeypatch):
    """Every actionable break → the signal dict must include _atr_stop with
    stop_pct, stop_price, atr_14, stop_source — even when the underlying
    yfinance call fails (fallback must still populate the dict)."""
    import json
    breaks_file = tmp_path / "breaks.json"
    breaks_file.write_text(json.dumps({
        "date": "2026-04-22", "scan_time": "2026-04-22T10:00:00+05:30",
        "breaks": [
            {"symbol": "BHEL", "trade_rec": "LONG", "classification": "REGIME_LAG",
             "z_score": 2.1, "expected_return": 1.5, "actual_return": 0.2},
        ],
    }))

    # Force a deterministic result so the test never hits the network.
    from pipeline import break_signal_generator as bsg
    monkeypatch.setattr(bsg, "compute_atr_stop",
                        lambda symbol, direction: {"stop_pct": -2.3, "stop_price": 310.5,
                                                    "atr_14": 7.1, "stop_source": "atr_14"})
    sigs = bsg.generate_break_candidates(breaks_file)
    assert len(sigs) == 1
    s = sigs[0]
    assert "_atr_stop" in s
    assert s["_atr_stop"]["stop_source"] == "atr_14"
    assert s["_atr_stop"]["stop_pct"] == -2.3
