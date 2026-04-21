from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import basket_builder as bb


@pytest.fixture
def phase_c_signals():
    return pd.DataFrame([
        {"date": "2026-04-01", "symbol": "HDFCBANK",  "sector": "BANKING",
         "classification": "OPPORTUNITY", "z_score": 2.5, "expected_return": 0.012, "confidence": 0.8},
        {"date": "2026-04-01", "symbol": "ICICIBANK", "sector": "BANKING",
         "classification": "OPPORTUNITY", "z_score": -2.1, "expected_return": -0.010, "confidence": 0.7},
        {"date": "2026-04-01", "symbol": "TCS",       "sector": "IT",
         "classification": "OPPORTUNITY", "z_score": 2.0, "expected_return": 0.010, "confidence": 0.6},
        {"date": "2026-04-01", "symbol": "SBIN",      "sector": "BANKING",
         "classification": "WARNING", "z_score": -2.3, "expected_return": -0.012, "confidence": 0.7},
        {"date": "2026-04-02", "symbol": "HDFCBANK",  "sector": "BANKING",
         "classification": "OPPORTUNITY", "z_score": 1.8, "expected_return": 0.008, "confidence": 0.6},
    ])


def test_sector_pair_forms_high_vs_low_conviction(phase_c_signals):
    """Apr 1 BANKING has 2 OPPORTUNITY signals → pair the highest-conviction long
    with the lowest-conviction short. Pick by expected_return * confidence."""
    pairs = bb.build_sector_pairs(phase_c_signals)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["date"] == pd.Timestamp("2026-04-01")
    assert pair["sector"] == "BANKING"
    assert pair["long_symbol"] == "HDFCBANK"
    assert pair["short_symbol"] == "ICICIBANK"


def test_sector_pair_skips_when_fewer_than_two_signals(phase_c_signals):
    """Apr 1 IT has only 1 OPPORTUNITY signal → no pair formed.
    Apr 2 BANKING has only 1 OPPORTUNITY signal → no pair."""
    pairs = bb.build_sector_pairs(phase_c_signals)
    # Only one pair (Apr 1 BANKING)
    assert len(pairs) == 1


def test_sector_pair_excludes_non_opportunity():
    signals = pd.DataFrame([
        {"date": "2026-04-01", "symbol": "A", "sector": "X",
         "classification": "WARNING", "z_score": 2, "expected_return": 0.01, "confidence": 0.6},
        {"date": "2026-04-01", "symbol": "B", "sector": "X",
         "classification": "UNCERTAIN", "z_score": -2, "expected_return": -0.01, "confidence": 0.5},
    ])
    assert bb.build_sector_pairs(signals) == []
