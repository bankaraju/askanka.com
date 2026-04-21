from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v55_leader_routing as v55


def _bar_frame(dates, start=50000.0, drift=0.001):
    rows, price = [], start
    for d in dates:
        o = price
        c = price * (1 + drift)
        rows.append({"date": d, "open": o, "high": o * 1.005, "low": o * 0.995,
                     "close": c, "volume": 10_000})
        price = c
    return pd.DataFrame(rows)


def test_v55_fires_when_two_top3_aligned():
    signals = pd.DataFrame([
        {"date": "2026-04-10", "symbol": "HDFCBANK",  "classification": "OPPORTUNITY",
         "direction": "LONG", "expected_return": 0.01, "confidence": 0.7},
        {"date": "2026-04-10", "symbol": "ICICIBANK", "classification": "OPPORTUNITY",
         "direction": "LONG", "expected_return": 0.01, "confidence": 0.7},
        {"date": "2026-04-10", "symbol": "SBIN",      "classification": "UNCERTAIN",
         "direction": "LONG", "expected_return": 0.01, "confidence": 0.5},
    ])
    dates = pd.bdate_range("2026-04-01", periods=15)
    ledger = v55.run(signals=signals,
                     symbol_bars={"BANKNIFTY": _bar_frame(dates)},
                     hold_days=1)
    assert len(ledger) == 1
    assert ledger.iloc[0]["index_symbol"] == "BANKNIFTY"
    assert ledger.iloc[0]["n_constituents_aligned"] == 2
    assert ledger.iloc[0]["direction"] == "LONG"


def test_v55_skips_when_only_one_top3():
    signals = pd.DataFrame([
        {"date": "2026-04-10", "symbol": "HDFCBANK", "classification": "OPPORTUNITY",
         "direction": "LONG", "expected_return": 0.01, "confidence": 0.7},
    ])
    ledger = v55.run(signals=signals, symbol_bars={}, hold_days=1)
    assert ledger.empty


def test_v55_skips_opposing_directions():
    signals = pd.DataFrame([
        {"date": "2026-04-10", "symbol": "HDFCBANK",  "classification": "OPPORTUNITY",
         "direction": "LONG",  "expected_return": 0.01, "confidence": 0.7},
        {"date": "2026-04-10", "symbol": "ICICIBANK", "classification": "OPPORTUNITY",
         "direction": "SHORT", "expected_return": -0.01, "confidence": 0.7},
    ])
    ledger = v55.run(signals=signals, symbol_bars={}, hold_days=1)
    assert ledger.empty
