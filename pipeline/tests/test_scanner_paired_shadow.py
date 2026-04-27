"""Unit tests for pipeline.scanner_paired_shadow — OPEN + CLOSE paths.

Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §6.5, §8.3, §8.4
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from pathlib import Path

import pandas as pd
import pytest

import pipeline.scanner_paired_shadow as sps
from pipeline.scanner_paired_shadow import open_options_pair, close_options_pair

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def scanner_signal():
    return {
        "signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
        "date": "2026-04-29",
        "scan_date": "2026-04-28",
        "ticker": "RELIANCE",
        "pattern_id": "BULLISH_HAMMER",
        "direction": "LONG",
        "composite_score": 4.27,
        "z_score": 3.0,
        "n_occurrences": 156,
        "win_rate": 0.62,
    }


@pytest.fixture
def nfo_fixture():
    return pd.DataFrame([
        {
            "name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
            "strike": 2400, "instrument_type": "CE", "lot_size": 500,
            "tradingsymbol": "RELIANCE26MAY2400CE", "instrument_token": 12345678,
        },
        {
            "name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
            "strike": 2400, "instrument_type": "PE", "lot_size": 500,
            "tradingsymbol": "RELIANCE26MAY2400PE", "instrument_token": 12345679,
        },
        {
            "name": "RELIANCE", "expiry": pd.Timestamp("2026-05-29"),
            "strike": 0, "instrument_type": "FUT", "lot_size": 500,
            "tradingsymbol": "RELIANCE26MAYFUT", "instrument_token": 12000000,
        },
    ])


def _good_quote(token: int = 12345678, bid: float = 119.5, ask: float = 122.0) -> dict:
    return {token: {
        "instrument_token": token, "last_price": 120.5,
        "timestamp": "2026-04-29 09:35:12",
        "depth": {
            "buy":  [{"price": bid, "quantity": 250, "orders": 1}],
            "sell": [{"price": ask, "quantity": 250, "orders": 1}],
        },
        "oi": 12345, "volume": 67890,
    }}


def _wide_quote(token: int = 12345678) -> dict:
    return {token: {
        "instrument_token": token, "last_price": 120.0,
        "timestamp": "2026-04-29 09:35:12",
        "depth": {
            "buy":  [{"price": 110.0, "quantity": 250, "orders": 1}],
            "sell": [{"price": 130.0, "quantity": 250, "orders": 1}],
        },
        "oi": 1, "volume": 1,
    }}


def _close_quote(token: int = 12345678, bid: float = 104.0, ask: float = 106.0) -> dict:
    return {token: {
        "instrument_token": token,
        "last_price": (bid + ask) / 2,
        "timestamp": "2026-04-29 15:30:00",
        "depth": {
            "buy":  [{"price": bid, "quantity": 250, "orders": 1}],
            "sell": [{"price": ask, "quantity": 250, "orders": 1}],
        },
        "oi": 5000, "volume": 10000,
    }}


def _open_row(
    signal_id: str = "2026-04-28_RELIANCE_BULLISH_HAMMER",
    status: str = "OPEN",
    entry_mid: float = 100.0,
    lot_size: int = 250,
    lots: int = 1,
    notional_at_entry: float = 25000.0,
    instrument_token: int = 12345678,
    is_expiry_day: bool = False,
    option_type: str = "CE",
) -> dict:
    return {
        "signal_id": signal_id,
        "date": "2026-04-29",
        "scan_date": "2026-04-28",
        "ticker": "RELIANCE",
        "pattern_id": "BULLISH_HAMMER",
        "scanner_composite_score_at_entry": 4.27,
        "scanner_z_score_at_entry": 3.0,
        "side": "LONG",
        "option_type": option_type,
        "lot_size": lot_size,
        "lots": lots,
        "notional_at_entry": notional_at_entry,
        "instrument_token": instrument_token,
        "entry_mid": entry_mid,
        "is_expiry_day": is_expiry_day,
        "status": status,
        "exit_time": None, "exit_bid": None, "exit_ask": None, "exit_mid": None,
        "seconds_to_expiry_at_close": None,
        "pnl_gross_pct": None, "pnl_net_pct": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }


# ---------------------------------------------------------------------------
# OPEN path
# ---------------------------------------------------------------------------

def test_open_writes_options_ledger_row(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """Happy path: all entry fields populated, status=OPEN."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _good_quote()

    row = open_options_pair(
        scanner_signal, entry_px=2398.0,
        kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500,
    )

    assert row["status"] == "OPEN"
    assert row["signal_id"] == "2026-04-28_RELIANCE_BULLISH_HAMMER"
    assert row["option_type"] == "CE"
    assert row["strike"] == 2400
    assert row["tradingsymbol"] == "RELIANCE26MAY2400CE"
    assert row["instrument_token"] == 12345678
    assert row["lot_size"] == 500
    assert row["lots"] == 1
    assert abs(row["entry_mid"] - 120.75) < 1e-9
    # Greeks non-null
    assert row["entry_iv"] is not None
    assert 0.45 < row["entry_delta"] < 0.65
    assert row["entry_theta"] < 0
    assert row["entry_vega"] > 0
    # Close fields null
    assert row["exit_time"] is None
    assert row["pnl_net_pct"] is None
    # Persisted
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1


def test_open_idempotent_on_signal_id(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """Second call with same signal_id returns existing row, no Kite call."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _good_quote()

    row1 = open_options_pair(scanner_signal, entry_px=2398.0,
                              kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)
    row2 = open_options_pair(scanner_signal, entry_px=2398.0,
                              kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)

    assert row1["signal_id"] == row2["signal_id"]
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1
    assert kite.quote.call_count == 1


def test_open_wide_spread_writes_skipped_liquidity(
    tmp_path, scanner_signal, nfo_fixture, monkeypatch
):
    """Wide spread -> status=SKIPPED_LIQUIDITY."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _wide_quote()

    row = open_options_pair(scanner_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)

    assert row["status"] == "SKIPPED_LIQUIDITY"
    assert row["skip_reason"] == "WIDE_SPREAD"
    assert row["entry_iv"] is None


def test_open_kite_failure_writes_error_row(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """Kite raises -> status=ERROR, no propagation."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.side_effect = RuntimeError("Kite session expired")

    row = open_options_pair(scanner_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)

    assert row["status"] == "ERROR"
    assert "RuntimeError" in row["skip_reason"]
    rows = json.loads(ledger.read_text())
    assert len(rows) == 1
    assert rows[0]["status"] == "ERROR"


def test_open_iv_solver_failure_non_blocking(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """backsolve_iv raises -> row written with status=OPEN, Greeks null."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _good_quote()

    monkeypatch.setattr(sps.options_greeks, "backsolve_iv",
                        MagicMock(side_effect=ValueError("solver diverged")))

    row = open_options_pair(scanner_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)

    assert row["status"] == "OPEN"
    assert row["entry_iv"] is None
    assert row["entry_delta"] is None


def test_open_long_uses_ce(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """direction=LONG -> option_type=CE."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.return_value = _good_quote()

    row = open_options_pair(scanner_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)
    assert row["option_type"] == "CE"


def test_open_short_uses_pe(tmp_path, nfo_fixture, monkeypatch):
    """direction=SHORT -> option_type=PE."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    short_signal = {
        "signal_id": "2026-04-28_RELIANCE_BEAR_ENG",
        "date": "2026-04-29", "scan_date": "2026-04-28",
        "ticker": "RELIANCE", "pattern_id": "BEAR_ENGULFING",
        "direction": "SHORT", "composite_score": 3.5, "z_score": 2.5,
    }
    kite = MagicMock()
    kite.quote.return_value = _good_quote(token=12345679, bid=119.5, ask=122.0)

    row = open_options_pair(short_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)
    assert row["option_type"] == "PE"
    assert row["entry_delta"] < 0


def test_open_persists_scanner_provenance(tmp_path, scanner_signal, nfo_fixture, monkeypatch):
    """pattern_id, scanner_composite_score_at_entry, scanner_z_score_at_entry on row."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)
    kite = MagicMock()
    kite.quote.return_value = _good_quote()

    row = open_options_pair(scanner_signal, entry_px=2398.0,
                             kite_client=kite, nfo_master_df=nfo_fixture, lot_size=500)

    assert row["pattern_id"] == "BULLISH_HAMMER"
    assert abs(row["scanner_composite_score_at_entry"] - 4.27) < 1e-9
    assert abs(row["scanner_z_score_at_entry"] - 3.0) < 1e-9
    # Confirm no drift_vs_rent fields
    assert "drift_vs_rent_tier" not in row
    assert "drift_vs_rent_matrix" not in row


# ---------------------------------------------------------------------------
# CLOSE path
# ---------------------------------------------------------------------------

def test_close_no_match_returns_none(tmp_path, monkeypatch):
    """signal_id not in ledger -> None."""
    ledger = tmp_path / "opts.json"
    ledger.write_text("[]")
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    result = close_options_pair("nope")
    assert result is None


def test_close_skips_terminal_status(tmp_path, monkeypatch):
    """Already CLOSED row -> returned unchanged, no Kite call."""
    ledger = tmp_path / "opts.json"
    row = _open_row(status="CLOSED")
    ledger.write_text(json.dumps([row]))
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    result = close_options_pair("2026-04-28_RELIANCE_BULLISH_HAMMER", kite_client=kite)

    assert result["status"] == "CLOSED"
    kite.quote.assert_not_called()


def test_close_happy_path_long_ce(tmp_path, monkeypatch):
    """entry_mid=100, exit_mid=110 -> pnl_gross_pct ~0.10, status=CLOSED."""
    ledger = tmp_path / "opts.json"
    row = _open_row(entry_mid=100.0, lot_size=250, lots=1, notional_at_entry=25000.0)
    ledger.write_text(json.dumps([row]))
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _close_quote(bid=109.0, ask=111.0)  # mid=110

    result = close_options_pair("2026-04-28_RELIANCE_BULLISH_HAMMER", kite_client=kite)

    assert result["status"] == "CLOSED"
    assert abs(result["exit_mid"] - 110.0) < 1e-9
    assert abs(result["pnl_gross_pct"] - 0.10) < 1e-9
    assert abs(result["pnl_gross_inr"] - 2500.0) < 1e-6  # (110-100)*250*1
    assert result["pnl_net_pct"] < result["pnl_gross_pct"]
    assert result["exit_bid"] == 109.0
    assert result["exit_ask"] == 111.0


def test_close_quote_failure_writes_time_stop_fail_fetch(tmp_path, monkeypatch):
    """Kite raises at close -> status=TIME_STOP_FAIL_FETCH, exit fields null."""
    ledger = tmp_path / "opts.json"
    row = _open_row()
    ledger.write_text(json.dumps([row]))
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.side_effect = RuntimeError("kite down")

    result = close_options_pair("2026-04-28_RELIANCE_BULLISH_HAMMER", kite_client=kite)

    assert result["status"] == "TIME_STOP_FAIL_FETCH"
    assert result["exit_mid"] is None
    assert result["pnl_gross_pct"] is None
    rows = json.loads(ledger.read_text())
    assert rows[0]["status"] == "TIME_STOP_FAIL_FETCH"


def test_close_wide_spread_still_closes(tmp_path, monkeypatch):
    """Wide spread at close is informational; row transitions to CLOSED."""
    ledger = tmp_path / "opts.json"
    row = _open_row(entry_mid=100.0, lot_size=250, lots=1, notional_at_entry=25000.0)
    ledger.write_text(json.dumps([row]))
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _close_quote(bid=90.0, ask=120.0)  # wide

    result = close_options_pair("2026-04-28_RELIANCE_BULLISH_HAMMER", kite_client=kite)

    assert result["status"] == "CLOSED"
    assert result["exit_mid"] == 105.0  # (90+120)/2


def test_close_persists_to_ledger(tmp_path, monkeypatch):
    """Re-load ledger after close; row updated in-place, not appended."""
    ledger = tmp_path / "opts.json"
    row = _open_row()
    other = _open_row(signal_id="other_signal")
    ledger.write_text(json.dumps([other, row]))
    monkeypatch.setattr(sps, "LEDGER_PATH", ledger)

    kite = MagicMock()
    kite.quote.return_value = _close_quote(bid=104.0, ask=106.0)

    close_options_pair("2026-04-28_RELIANCE_BULLISH_HAMMER", kite_client=kite)

    rows = json.loads(ledger.read_text())
    assert len(rows) == 2  # no append
    updated = next(r for r in rows if r["signal_id"] == "2026-04-28_RELIANCE_BULLISH_HAMMER")
    assert updated["status"] == "CLOSED"
    other_row = next(r for r in rows if r["signal_id"] == "other_signal")
    assert other_row["status"] == "OPEN"
