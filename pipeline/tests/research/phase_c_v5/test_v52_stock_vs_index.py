from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v52_stock_vs_index as v52


def test_v52_produces_two_leg_ledger_row():
    signals = pd.DataFrame([{
        "date": "2026-04-01", "symbol": "HDFCBANK", "sector_index": "BANKNIFTY",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-01-01", periods=100)
    stock_bars = pd.DataFrame({
        "date": dates, "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 1_000_000,
    })
    index_bars = pd.DataFrame({
        "date": dates, "open": 50000.0, "high": 50500.0, "low": 49500.0,
        "close": 50250.0, "volume": 100_000,
    })
    ledger = v52.run(signals=signals,
                     symbol_bars={"HDFCBANK": stock_bars, "BANKNIFTY": index_bars},
                     hold_days=1)
    assert len(ledger) == 1
    assert ledger.iloc[0]["stock_symbol"] == "HDFCBANK"
    assert ledger.iloc[0]["index_symbol"] == "BANKNIFTY"
    assert "hedge_ratio" in ledger.columns
    # Hedge ratio must be clamped to [0.5, 1.5]
    assert 0.5 <= ledger.iloc[0]["hedge_ratio"] <= 1.5
