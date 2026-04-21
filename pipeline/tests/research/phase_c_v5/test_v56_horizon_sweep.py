from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v56_horizon_sweep as v56


def test_v56_emits_five_horizons_per_signal():
    signals = pd.DataFrame([{
        "date": "2026-04-01", "symbol": "ABC",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-03-01", periods=60)
    stock = pd.DataFrame({"date": dates, "open": 100.0, "high": 101.0,
                           "low": 99.0, "close": 100.5, "volume": 100_000})
    ledger = v56.run(signals=signals, symbol_bars={"ABC": stock})
    # 5 horizons: 14:30 (intraday, uses open of next bar as proxy), T+1, T+2, T+3, T+5
    assert set(ledger["exit_horizon"].unique()) == {"intraday_1430", "T+1", "T+2", "T+3", "T+5"}
    assert len(ledger) == 5
