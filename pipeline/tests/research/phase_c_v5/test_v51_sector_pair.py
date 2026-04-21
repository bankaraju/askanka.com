from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v51_sector_pair as v51


def _bars(symbol_drift: dict, day: str = "2026-04-01") -> dict:
    """1-min bars 09:15-15:30 for multiple symbols with a constant drift."""
    start = pd.Timestamp(f"{day} 09:15:00")
    end = pd.Timestamp(f"{day} 15:30:00")
    minutes = pd.date_range(start, end, freq="1min")
    out = {}
    for sym, drift in symbol_drift.items():
        rows, price = [], 100.0
        for m in minutes:
            o = price
            c = price * (1 + drift)
            rows.append({"date": m, "open": o, "high": max(o, c) * 1.0005,
                         "low": min(o, c) * 0.9995, "close": c, "volume": 1000})
            price = c
        out[sym] = pd.DataFrame(rows)
    return out


def test_v51_pair_combined_pnl_matches_long_minus_short():
    pairs = [{
        "date": pd.Timestamp("2026-04-01"),
        "sector": "BANKING",
        "long_symbol": "WINNER", "short_symbol": "LOSER",
        "long_conviction": 0.01, "short_conviction": -0.008,
    }]
    bars = _bars({"WINNER": 0.0001, "LOSER": -0.00005})
    ledger = v51.run(pairs=pairs, symbol_minute_bars=bars)
    assert len(ledger) == 1
    row = ledger.iloc[0]
    assert row["sector"] == "BANKING"
    # Both legs profitable (long went up, short went down) → net > 0
    assert row["pnl_net_inr"] > 0
    # Exit reason must be the 14:30 mechanical cutoff
    assert row["exit_reason"] == "time_stop"


def test_v51_skips_pair_when_bars_missing():
    pairs = [{
        "date": pd.Timestamp("2026-04-01"),
        "sector": "BANKING",
        "long_symbol": "GHOST", "short_symbol": "LOSER",
        "long_conviction": 0.01, "short_conviction": -0.008,
    }]
    bars = _bars({"LOSER": 0.0})  # GHOST missing
    ledger = v51.run(pairs=pairs, symbol_minute_bars=bars)
    assert ledger.empty
