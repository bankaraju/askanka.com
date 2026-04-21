from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v54_banknifty_dispersion as v54


def _constant_drift(dates, drift, start=100.0):
    rows, price = [], start
    for d in dates:
        o = price
        c = price * (1 + drift)
        rows.append({"date": d, "open": o, "high": o * 1.005,
                     "low": o * 0.995, "close": c, "volume": 10_000})
        price = c
    return pd.DataFrame(rows)


def test_v54_fires_when_top_constituent_outperforms_index():
    signals = pd.DataFrame([{
        "date": "2026-04-10", "symbol": "HDFCBANK",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-04-01", periods=15)
    stock = _constant_drift(dates, drift=0.01, start=1500.0)
    index = _constant_drift(dates, drift=0.001, start=50_000.0)  # flat index
    ledger = v54.run(signals=signals,
                     symbol_bars={"HDFCBANK": stock, "BANKNIFTY": index},
                     hold_days=1)
    assert len(ledger) == 1
    assert ledger.iloc[0]["stock_symbol"] == "HDFCBANK"
    assert ledger.iloc[0]["index_symbol"] == "BANKNIFTY"
    # stock long, index short
    assert ledger.iloc[0]["stock_side"] == "LONG"
    assert ledger.iloc[0]["index_side"] == "SHORT"


def test_v54_skips_non_top_constituent():
    signals = pd.DataFrame([{
        "date": "2026-04-10", "symbol": "AXISBANK",  # not in top-3
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-04-01", periods=15)
    ledger = v54.run(signals=signals,
                     symbol_bars={"AXISBANK": _constant_drift(dates, 0.01),
                                   "BANKNIFTY": _constant_drift(dates, 0.001, 50000)},
                     hold_days=1)
    assert ledger.empty


def test_v54_skips_when_index_not_lagging():
    signals = pd.DataFrame([{
        "date": "2026-04-10", "symbol": "HDFCBANK",
        "classification": "OPPORTUNITY", "direction": "LONG",
        "expected_return": 0.01, "confidence": 0.7,
    }])
    dates = pd.bdate_range("2026-04-01", periods=15)
    # Index rises FASTER than stock → not lagging → no trade
    stock = _constant_drift(dates, 0.001, 1500)
    index = _constant_drift(dates, 0.01, 50_000)
    ledger = v54.run(signals=signals,
                     symbol_bars={"HDFCBANK": stock, "BANKNIFTY": index},
                     hold_days=1)
    assert ledger.empty
