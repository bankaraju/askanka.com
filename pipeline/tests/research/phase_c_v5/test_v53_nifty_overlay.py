from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v53_nifty_overlay as v53


def test_v53_always_uses_nifty_as_hedge():
    signals = pd.DataFrame([{
        "date": "2026-04-01", "symbol": "TCS", "sector_index": "NIFTYIT",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-01-01", periods=100)
    stock = pd.DataFrame({"date": dates, "open": 3500.0, "high": 3510.0,
                           "low": 3490.0, "close": 3505.0, "volume": 1_000_000})
    nifty = pd.DataFrame({"date": dates, "open": 22000.0, "high": 22100.0,
                           "low": 21900.0, "close": 22050.0, "volume": 0})
    ledger = v53.run(signals=signals,
                     symbol_bars={"TCS": stock, "NIFTY": nifty}, hold_days=1)
    assert len(ledger) == 1
    assert ledger.iloc[0]["index_symbol"] == "NIFTY"
