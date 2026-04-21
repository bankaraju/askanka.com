# pipeline/tests/research/phase_c_v5/test_intraday_basket_simulator.py
from __future__ import annotations
from unittest.mock import patch
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import intraday_basket_simulator as ibs


def _minute_bars(day, drift=0.0001, start=100.0):
    minutes = pd.date_range(f"{day} 09:15:00", f"{day} 15:30:00", freq="1min")
    rows, price = [], start
    for m in minutes:
        o = price
        c = price * (1 + drift)
        rows.append({"date": m, "open": o, "high": max(o, c) * 1.0005,
                     "low": min(o, c) * 0.9995, "close": c, "volume": 1_000})
        price = c
    return pd.DataFrame(rows)


def test_run_intraday_pair_fetches_minute_bars_per_leg():
    pair = {"date": pd.Timestamp("2026-04-01"), "sector": "TEST",
            "long_symbol": "A", "short_symbol": "B",
            "long_conviction": 0.01, "short_conviction": -0.01}
    a = _minute_bars("2026-04-01", drift=0.0001)
    b = _minute_bars("2026-04-01", drift=-0.00005)

    def _fetch(sym, trade_date):
        return a if sym == "A" else b

    with patch.object(ibs, "_fetch_minute", side_effect=_fetch) as mock:
        ledger = ibs.run([pair])
    assert mock.call_count == 2
    assert len(ledger) == 1
    assert ledger.iloc[0]["long_symbol"] == "A"
    assert ledger.iloc[0]["exit_reason"] == "time_stop"
