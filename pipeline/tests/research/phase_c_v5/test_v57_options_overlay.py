from __future__ import annotations
from unittest.mock import patch
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v57_options_overlay as v57


def test_v57_long_signal_buys_call(monkeypatch):
    signals = pd.DataFrame([{
        "date": "2026-04-01", "symbol": "ABC",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-03-01", periods=30)
    bars = pd.DataFrame({"date": dates, "open": 100.0, "high": 102.0,
                          "low": 98.0, "close": 101.0, "volume": 100_000})
    with patch.object(v57, "_price_option", side_effect=[5.0, 7.0]) as mock_price:
        ledger = v57.run(signals=signals, symbol_bars={"ABC": bars})
    assert len(ledger) == 1
    assert ledger.iloc[0]["option_type"] == "CALL"
    assert ledger.iloc[0]["option_entry_premium"] == 5.0
    assert ledger.iloc[0]["option_exit_premium"] == 7.0
    # Profit = (7 - 5) * notional / entry_px; net = gross - cost
    assert ledger.iloc[0]["pnl_net_inr"] < ledger.iloc[0]["pnl_gross_inr"]


def test_v57_short_signal_buys_put():
    signals = pd.DataFrame([{
        "date": "2026-04-01", "symbol": "ABC",
        "classification": "OPPORTUNITY", "direction": "SHORT",
        "expected_return": -0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-03-01", periods=30)
    bars = pd.DataFrame({"date": dates, "open": 100.0, "high": 102.0,
                          "low": 98.0, "close": 99.0, "volume": 100_000})
    with patch.object(v57, "_price_option", side_effect=[5.0, 8.0]):
        ledger = v57.run(signals=signals, symbol_bars={"ABC": bars})
    assert ledger.iloc[0]["option_type"] == "PUT"
