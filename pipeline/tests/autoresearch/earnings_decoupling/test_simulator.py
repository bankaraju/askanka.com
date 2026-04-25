import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.simulator import simulate_trades


@pytest.fixture
def fixtures():
    dates = pd.bdate_range("2024-01-01", periods=20)
    prices = pd.DataFrame({
        "RELIANCE": [1000.0 + i for i in range(20)],
    }, index=dates)
    ledger = pd.DataFrame([
        {"ticker": "RELIANCE", "event_date": dates[10].strftime("%Y-%m-%d"),
         "status": "CANDIDATE", "direction": "LONG", "trigger_z": 2.0,
         "sector_index": "BANKNIFTY"},
    ])
    return dict(ledger=ledger, prices=prices)


def test_simulate_trades_filters_to_candidates(fixtures):
    fixtures["ledger"] = pd.concat([
        fixtures["ledger"],
        pd.DataFrame([{"ticker": "TCS", "event_date": "2024-01-15",
                        "status": "DROPPED_NO_TRIGGER"}]),
    ], ignore_index=True)
    out = simulate_trades(**fixtures)
    assert len(out) == 1
    assert out.iloc[0]["ticker"] == "RELIANCE"


def test_simulate_trades_long_pnl_uses_t_minus_3_to_t_minus_1_close(fixtures):
    out = simulate_trades(**fixtures)
    row = out.iloc[0]
    expected = (1009 - 1007) / 1007 * 100
    assert abs(row["trade_ret_pct"] - expected) < 1e-6
    assert row["next_ret"] > 0


def test_simulate_trades_short_pnl_inverts_sign(fixtures):
    fixtures["ledger"].loc[0, "direction"] = "SHORT"
    fixtures["ledger"].loc[0, "trigger_z"] = -2.0
    out = simulate_trades(**fixtures)
    row = out.iloc[0]
    expected = -(1009 - 1007) / 1007 * 100
    assert abs(row["trade_ret_pct"] - expected) < 1e-6


def test_simulate_trades_drops_when_entry_or_exit_price_missing(fixtures):
    fixtures["prices"] = fixtures["prices"].copy()
    entry_date = pd.bdate_range("2024-01-01", periods=20)[7]
    fixtures["prices"].loc[entry_date, "RELIANCE"] = None
    out = simulate_trades(**fixtures)
    assert len(out) == 0
