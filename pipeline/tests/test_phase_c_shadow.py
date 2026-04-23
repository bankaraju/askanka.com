"""Tests for the Phase C F3 live shadow driver."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline import phase_c_shadow
from pipeline.research.phase_c_backtest import live_paper


def _breaks_doc(rows: list[dict], date: str = "2026-04-22") -> dict:
    return {
        "date": date,
        "scan_time": f"{date} 09:25:00",
        "breaks": rows,
    }


def test_filter_opportunity_drops_non_opportunity():
    rows = [
        {"symbol": "A", "classification": "OPPORTUNITY_LAG"},
        {"symbol": "B", "classification": "POSSIBLE_OPPORTUNITY"},
        {"symbol": "C", "classification": "UNCERTAIN"},
        {"symbol": "D", "classification": "WARNING"},
    ]
    kept = phase_c_shadow._filter_opportunity(rows)
    assert [b["symbol"] for b in kept] == ["A"]


def test_side_from_expected_long_positive():
    assert phase_c_shadow._side_from_expected(0.5) == "LONG"
    assert phase_c_shadow._side_from_expected(0.0) == "LONG"


def test_side_from_expected_short_negative():
    assert phase_c_shadow._side_from_expected(-0.2) == "SHORT"


def test_build_open_signals_happy_path():
    doc = _breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY",
         "expected_return": 0.8, "z_score": 2.4},
        {"symbol": "FOO", "classification": "OPPORTUNITY",
         "expected_return": -0.6, "z_score": -1.9},
    ])
    ltp = {"ACME": 100.0, "FOO": 200.0}
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert len(df) == 2
    assert set(df["symbol"]) == {"ACME", "FOO"}
    acme = df[df["symbol"] == "ACME"].iloc[0]
    assert acme["side"] == "LONG"
    assert acme["entry_px"] == pytest.approx(100.0)
    assert acme["date"] == "2026-04-22"
    assert acme["signal_time"] == "2026-04-22 09:25:00"
    assert acme["stop_pct"] == pytest.approx(0.02)
    assert acme["target_pct"] == pytest.approx(0.01)
    foo = df[df["symbol"] == "FOO"].iloc[0]
    assert foo["side"] == "SHORT"


def test_build_open_signals_skips_symbols_missing_ltp():
    doc = _breaks_doc([
        {"symbol": "A", "classification": "OPPORTUNITY", "expected_return": 0.5, "z_score": 2.0},
        {"symbol": "B", "classification": "OPPORTUNITY", "expected_return": 0.5, "z_score": 2.0},
    ])
    ltp = {"A": 100.0}  # B is missing
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert list(df["symbol"]) == ["A"]


def test_build_open_signals_skips_rows_with_missing_expected_return():
    doc = _breaks_doc([
        {"symbol": "A", "classification": "OPPORTUNITY", "expected_return": None, "z_score": 2.0},
        {"symbol": "B", "classification": "OPPORTUNITY", "expected_return": 0.5, "z_score": 2.0},
    ])
    ltp = {"A": 100.0, "B": 200.0}
    df = phase_c_shadow.build_open_signals(doc, ltp)
    assert list(df["symbol"]) == ["B"]


def test_build_open_signals_empty_breaks_returns_empty_df():
    df = phase_c_shadow.build_open_signals(_breaks_doc([]), {})
    assert df.empty


def test_cmd_open_with_no_breaks_file(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", tmp_path / "missing.json")
    with caplog.at_level("INFO"):
        rc = phase_c_shadow.cmd_open()
    assert rc == 0
    assert any("no breaks doc" in r.message for r in caplog.records)


def test_cmd_open_happy_path(tmp_path, monkeypatch):
    # Stub the breaks file
    breaks_path = tmp_path / "correlation_breaks.json"
    breaks_path.write_text(json.dumps(_breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY",
         "expected_return": 0.5, "z_score": 2.0},
    ])), encoding="utf-8")
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)

    # Stub Kite
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 123.0})

    # Stub ledger path
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rc = phase_c_shadow.cmd_open()
    assert rc == 0
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["symbol"] == "ACME"
    assert data[0]["status"] == "OPEN"
    assert data[0]["entry_px"] == 123.0
    assert data[0]["side"] == "LONG"


def test_cmd_open_idempotent_on_second_run(tmp_path, monkeypatch):
    breaks_path = tmp_path / "correlation_breaks.json"
    breaks_path.write_text(json.dumps(_breaks_doc([
        {"symbol": "ACME", "classification": "OPPORTUNITY",
         "expected_return": 0.5, "z_score": 2.0},
    ])), encoding="utf-8")
    monkeypatch.setattr(phase_c_shadow, "_BREAKS_PATH", breaks_path)
    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 100.0})
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    phase_c_shadow.cmd_open()
    phase_c_shadow.cmd_open()  # second call same session

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_cmd_close_happy_path(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    # Seed ledger with one OPEN entry
    signals = pd.DataFrame([{
        "date": "2026-04-22", "signal_time": "2026-04-22 09:25:00",
        "symbol": "ACME", "side": "LONG", "z_score": 2.0,
        "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0,
    }])
    live_paper.record_opens(signals)

    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {"ACME": 102.0})

    rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 0

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data[0]["status"] == "CLOSED"
    assert data[0]["exit_px"] == 102.0
    # LONG, +2% on ₹50k notional = ₹1000 gross
    assert data[0]["pnl_gross_inr"] == pytest.approx(1000.0)


def test_cmd_close_no_open_positions_returns_zero(tmp_path, monkeypatch, caplog):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)
    # No signals yet — ledger is empty
    with caplog.at_level("INFO"):
        rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 0
    assert any("no OPEN entries" in r.message for r in caplog.records)


def test_cmd_close_ltp_failure_leaves_ledger_untouched(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)
    signals = pd.DataFrame([{
        "date": "2026-04-22", "signal_time": "2026-04-22 09:25:00",
        "symbol": "ACME", "side": "LONG", "z_score": 2.0,
        "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0,
    }])
    live_paper.record_opens(signals)

    monkeypatch.setattr(phase_c_shadow, "_fetch_ltp", lambda syms: {})
    rc = phase_c_shadow.cmd_close(date_override="2026-04-22")
    assert rc == 1

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data[0]["status"] == "OPEN"  # unchanged
