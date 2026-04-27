"""Unit tests for the OPEN path of pipeline.phase_c_options_shadow — T4."""
import json
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock
from pathlib import Path
import pandas as pd
import pytest

from pipeline.phase_c_options_shadow import (
    open_options_pair,
    _build_signal_id,
)


IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def signal_row():
    return {
        "date": "2026-04-29",
        "signal_time": "2026-04-29 09:25:00",
        "symbol": "RELIANCE",
        "side": "LONG",
        "z_score": 2.85,
        "stop_pct": 0.02,
        "target_pct": 0.01,
        "entry_px": 2398.0,
    }


@pytest.fixture
def nfo_fixture():
    return pd.DataFrame([
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 2400, "instrument_type": "CE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAY2400CE", "instrument_token": 12345678},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 2400, "instrument_type": "PE", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAY2400PE", "instrument_token": 12345679},
        {"name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
         "strike": 0, "instrument_type": "FUT", "lot_size": 500,
         "tradingsymbol": "RELIANCE26MAYFUT", "instrument_token": 12000000},
    ])


def _good_quote_dict(token: int = 12345678, bid: float = 119.5, ask: float = 122.0):
    return {token: {
        "instrument_token": token, "last_price": 120.5,
        "timestamp": "2026-04-29 09:35:12",
        "depth": {
            "buy":  [{"price": bid, "quantity": 250, "orders": 1}],
            "sell": [{"price": ask, "quantity": 250, "orders": 1}],
        },
        "oi": 12345, "volume": 67890,
    }}


def _wide_quote_dict(token: int = 12345678):
    return {token: {
        "instrument_token": token, "last_price": 120.0,
        "timestamp": "2026-04-29 09:35:12",
        "depth": {
            "buy":  [{"price": 110.0, "quantity": 250, "orders": 1}],
            "sell": [{"price": 130.0, "quantity": 250, "orders": 1}],
        },
        "oi": 1, "volume": 1,
    }}


def test_build_signal_id_format(signal_row):
    assert _build_signal_id(signal_row) == "2026-04-29_RELIANCE_0925"


def test_build_signal_id_uses_existing_if_present():
    sid = "custom_id_xyz"
    row = {"date": "2026-04-29", "symbol": "X", "signal_time": "X", "signal_id": sid}
    assert _build_signal_id(row) == sid


def test_open_writes_open_row_with_all_fields(tmp_path, signal_row, nfo_fixture, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.return_value = _good_quote_dict()

    row = open_options_pair(
        signal_row, kite_client=kite,
        nfo_master_df=nfo_fixture, lot_size=500,
    )

    assert row["status"] == "OPEN"
    assert row["signal_id"] == "2026-04-29_RELIANCE_0925"
    assert row["option_type"] == "CE"  # LONG → CE
    assert row["strike"] == 2400
    assert row["expiry_date"] == "2026-05-29"
    assert row["instrument_token"] == 12345678
    assert row["tradingsymbol"] == "RELIANCE26MAY2400CE"
    assert row["lot_size"] == 500
    assert row["lots"] == 1
    assert abs(row["entry_mid"] - 120.75) < 1e-9
    assert abs(row["notional_at_entry"] - 120.75 * 500 * 1) < 1e-6
    # Greeks computed
    assert row["entry_iv"] is not None
    assert 0.45 < row["entry_delta"] < 0.65  # ATM-ish
    assert row["entry_theta"] < 0
    assert row["entry_vega"] > 0
    # Tier deferred
    assert row["drift_vs_rent_tier"] == "UNKNOWN"
    assert row["drift_vs_rent_matrix"] is None
    # Close-side fields are null until T6
    assert row["pnl_net_pct"] is None
    assert row["exit_time"] is None
    # Persisted
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1
    assert rows[0]["signal_id"] == row["signal_id"]


def test_short_signal_uses_pe(tmp_path, signal_row, nfo_fixture, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    signal_row["side"] = "SHORT"
    kite = MagicMock()
    kite.quote.return_value = _good_quote_dict(token=12345679, bid=119.5, ask=122.0)

    row = open_options_pair(signal_row, kite_client=kite,
                              nfo_master_df=nfo_fixture, lot_size=500)
    assert row["option_type"] == "PE"
    assert row["strike"] == 2400
    assert row["tradingsymbol"] == "RELIANCE26MAY2400PE"
    assert row["entry_delta"] < 0  # PE delta is negative


def test_wide_spread_writes_skipped_row(tmp_path, signal_row, nfo_fixture, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.return_value = _wide_quote_dict()

    row = open_options_pair(signal_row, kite_client=kite,
                              nfo_master_df=nfo_fixture, lot_size=500)

    assert row["status"] == "SKIPPED_LIQUIDITY"
    assert row["skip_reason"] == "WIDE_SPREAD"
    # Strike + expiry resolved (we got that far)
    assert row["strike"] == 2400
    # Greeks NOT computed for skipped rows
    assert row["entry_iv"] is None
    assert row["entry_delta"] is None


def test_kite_exception_writes_error_row(tmp_path, signal_row, nfo_fixture, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.side_effect = RuntimeError("Kite session expired")

    row = open_options_pair(signal_row, kite_client=kite,
                              nfo_master_df=nfo_fixture, lot_size=500)

    assert row["status"] == "ERROR"
    assert "RuntimeError" in row["skip_reason"]
    assert "Kite session expired" in row["skip_reason"]
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1
    assert rows[0]["status"] == "ERROR"


def test_nfo_lookup_miss_writes_error_row(tmp_path, signal_row, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    empty_nfo = pd.DataFrame(columns=[
        "name", "expiry", "strike", "instrument_type", "lot_size",
        "tradingsymbol", "instrument_token",
    ])
    kite = MagicMock()  # never called

    row = open_options_pair(signal_row, kite_client=kite,
                              nfo_master_df=empty_nfo, lot_size=500)
    assert row["status"] == "ERROR"
    assert "ValueError" in row["skip_reason"]


def test_idempotent_on_signal_id(tmp_path, signal_row, nfo_fixture, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.return_value = _good_quote_dict()

    row1 = open_options_pair(signal_row, kite_client=kite,
                                nfo_master_df=nfo_fixture, lot_size=500)
    row2 = open_options_pair(signal_row, kite_client=kite,
                                nfo_master_df=nfo_fixture, lot_size=500)

    assert row1["signal_id"] == row2["signal_id"]
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1  # Only one row despite two calls
    # kite.quote called only once
    assert kite.quote.call_count == 1


def test_is_expiry_day_true_when_dte_zero(tmp_path, monkeypatch, nfo_fixture):
    """Spot signal_row's date matches the expiry_date → is_expiry_day=True."""
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    monkeypatch.setattr("pipeline.phase_c_options_shadow.LEDGER_PATH", ledger)
    # Add a current-day expiry option to the NFO fixture
    nfo_with_today = pd.concat([nfo_fixture, pd.DataFrame([{
        "name": "RELIANCE", "expiry": pd.Timestamp("2026-04-29"),
        "strike": 2400, "instrument_type": "CE", "lot_size": 500,
        "tradingsymbol": "RELIANCE26APR2400CE", "instrument_token": 99999999,
    }])], ignore_index=True)

    signal_row = {
        "date": "2026-04-29",
        "signal_time": "2026-04-29 09:25:00",
        "symbol": "RELIANCE", "side": "LONG", "entry_px": 2398.0,
    }

    # Patch _ist_now so today resolves to 2026-04-29
    monkeypatch.setattr("pipeline.phase_c_options_shadow._ist_now",
                        lambda: datetime(2026, 4, 29, 9, 35, 12, tzinfo=IST))

    kite = MagicMock()
    kite.quote.return_value = _good_quote_dict(token=99999999)

    row = open_options_pair(signal_row, kite_client=kite,
                              nfo_master_df=nfo_with_today, lot_size=500)

    assert row["is_expiry_day"] is True
    assert row["days_to_expiry"] == 0
    assert row["expiry_date"] == "2026-04-29"
