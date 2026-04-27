"""Unit tests for pipeline.options_atm_helpers — Phase C paired-shadow T1."""
from datetime import date
from pathlib import Path
import pandas as pd
import pytest

from pipeline.options_atm_helpers import (
    load_nfo_master,
    resolve_nearest_monthly_expiry,
    resolve_atm_strike,
    compose_tradingsymbol,
    get_lot_size_for_ticker,
)


@pytest.fixture
def nfo_fixture():
    """Synthetic NFO master with RELIANCE futures + 2 expiries x 3 strikes."""
    return pd.DataFrame([
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 0, "instrument_type": "FUT", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAYFUT", "instrument_token": 100},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-04-24"),
         "strike": 1390, "instrument_type": "CE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26APR1390CE", "instrument_token": 101},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-04-24"),
         "strike": 1400, "instrument_type": "CE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26APR1400CE", "instrument_token": 102},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-04-24"),
         "strike": 1410, "instrument_type": "CE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26APR1410CE", "instrument_token": 103},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 1390, "instrument_type": "PE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAY1390PE", "instrument_token": 104},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 1400, "instrument_type": "CE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAY1400CE", "instrument_token": 105},
        {"name": "INFY", "expiry": pd.Timestamp("2026-04-24"),
         "strike": 1500, "instrument_type": "CE", "lot_size": 400,
         "tradingsymbol": "INFY26APR1500CE", "instrument_token": 200},
        {"name": "INFY", "expiry": pd.Timestamp("2026-04-24"),
         "strike": 0, "instrument_type": "FUT", "lot_size": 400,
         "tradingsymbol": "INFY26APRFUT", "instrument_token": 201},
    ])


def test_resolve_nearest_monthly_expiry_returns_earliest_forward(nfo_fixture):
    today = date(2026, 4, 23)
    out = resolve_nearest_monthly_expiry(today, "RELIANCE", nfo_fixture)
    assert out == date(2026, 4, 24)


def test_resolve_nearest_monthly_expiry_skips_past_expiries(nfo_fixture):
    today = date(2026, 4, 25)  # past Apr 24
    out = resolve_nearest_monthly_expiry(today, "RELIANCE", nfo_fixture)
    assert out == date(2026, 5, 29)


def test_resolve_nearest_monthly_expiry_raises_on_unknown_ticker(nfo_fixture):
    with pytest.raises(ValueError, match="no monthly contracts"):
        resolve_nearest_monthly_expiry(date(2026, 4, 23), "UNKNOWN", nfo_fixture)


def test_resolve_nearest_monthly_expiry_raises_when_all_expired(nfo_fixture):
    with pytest.raises(ValueError, match="no monthly contracts"):
        resolve_nearest_monthly_expiry(date(2027, 1, 1), "RELIANCE", nfo_fixture)


def test_resolve_atm_strike_picks_closest(nfo_fixture):
    out = resolve_atm_strike(spot=1402.0, ticker="RELIANCE",
                              expiry=date(2026, 4, 24), nfo_master_df=nfo_fixture)
    assert out == 1400


def test_resolve_atm_strike_exact_match(nfo_fixture):
    out = resolve_atm_strike(spot=1400.0, ticker="RELIANCE",
                              expiry=date(2026, 4, 24), nfo_master_df=nfo_fixture)
    assert out == 1400


def test_resolve_atm_strike_outside_range_picks_endpoint(nfo_fixture):
    out = resolve_atm_strike(spot=2000.0, ticker="RELIANCE",
                              expiry=date(2026, 4, 24), nfo_master_df=nfo_fixture)
    assert out == 1410


def test_resolve_atm_strike_tie_breaks_lower(nfo_fixture):
    """Spot exactly midway between 1390 and 1400 -> argmin returns first match
    (the lower strike, since the fixture lists them in ascending order)."""
    out = resolve_atm_strike(spot=1395.0, ticker="RELIANCE",
                              expiry=date(2026, 4, 24), nfo_master_df=nfo_fixture)
    assert out == 1390


def test_resolve_atm_strike_raises_on_empty(nfo_fixture):
    with pytest.raises(ValueError, match="no strikes listed"):
        resolve_atm_strike(spot=1000.0, ticker="UNKNOWN",
                            expiry=date(2026, 4, 24), nfo_master_df=nfo_fixture)


def test_compose_tradingsymbol_reliance_may_ce():
    out = compose_tradingsymbol("RELIANCE", date(2026, 5, 29), 2400, "CE")
    assert out == "RELIANCE26MAY2400CE"


def test_compose_tradingsymbol_infy_apr_pe():
    out = compose_tradingsymbol("INFY", date(2026, 4, 24), 1500, "PE")
    assert out == "INFY26APR1500PE"


def test_get_lot_size_for_ticker(nfo_fixture):
    assert get_lot_size_for_ticker("RELIANCE", nfo_fixture) == 500
    assert get_lot_size_for_ticker("INFY", nfo_fixture) == 400


def test_get_lot_size_for_ticker_raises_on_unknown(nfo_fixture):
    with pytest.raises(ValueError, match="no futures contracts"):
        get_lot_size_for_ticker("UNKNOWN", nfo_fixture)


def test_load_nfo_master_round_trip(tmp_path):
    csv = tmp_path / "nfo.csv"
    csv.write_text(
        "instrument_token,exchange_token,tradingsymbol,name,last_price,"
        "expiry,strike,tick_size,lot_size,instrument_type,segment,exchange\n"
        "100,1,RELIANCE26MAYFUT,RELIANCE,0,2026-05-29,0,0.1,500,FUT,NFO-FUT,NFO\n"
        "101,2,RELIANCE26APR1400CE,RELIANCE,0,2026-04-24,1400,0.05,500,CE,NFO-OPT,NFO\n"
    )
    df = load_nfo_master(csv)
    assert len(df) == 2
    assert df.iloc[0]["name"] == "RELIANCE"
    assert df.iloc[0]["expiry"] == pd.Timestamp("2026-05-29")
