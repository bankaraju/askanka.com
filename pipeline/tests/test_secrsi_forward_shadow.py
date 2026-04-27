"""Tests for pipeline.research.h_2026_04_27_secrsi.forward_shadow.

Pure-logic tests only (P&L math, idempotency check, row building). Live
Kite integration is not unit-tested — it runs against the real session
in scheduled tasks.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline.research.h_2026_04_27_secrsi import forward_shadow as fs


def test_pnl_pct_long_profit():
    assert fs._pnl_pct("LONG", 100.0, 105.0) == pytest.approx(5.0)


def test_pnl_pct_long_loss():
    assert fs._pnl_pct("LONG", 100.0, 95.0) == pytest.approx(-5.0)


def test_pnl_pct_short_profit():
    assert fs._pnl_pct("SHORT", 100.0, 95.0) == pytest.approx(5.0)


def test_pnl_pct_short_loss():
    assert fs._pnl_pct("SHORT", 100.0, 105.0) == pytest.approx(-5.0)


def test_pnl_pct_zero_entry():
    assert fs._pnl_pct("LONG", 0.0, 100.0) == 0.0


def test_basket_id_and_leg_id_format():
    assert fs._basket_id("2026-04-28") == "SECRSI-2026-04-28"
    assert fs._leg_id("2026-04-28", "RELIANCE", "LONG") == "SECRSI-2026-04-28-RELIANCE-LONG"


def test_build_open_row_long():
    leg = {
        "ticker": "RELIANCE", "sector": "ENERGY", "side": "LONG",
        "sector_score": 0.025, "stock_pct_at_snap": 0.030, "weight": 0.125,
    }
    atr_info = {"atr_14": 25.0, "stop_price": 1250.0, "stop_pct": -2.0,
                "stop_source": "atr_14"}
    row = fs._build_open_row(
        leg, entry_px=1300.0, atr_info=atr_info,
        regime="RISK-ON", today="2026-04-28",
        now="2026-04-28T11:00:05+05:30",
    )
    assert row["basket_id"] == "SECRSI-2026-04-28"
    assert row["leg_id"] == "SECRSI-2026-04-28-RELIANCE-LONG"
    assert row["ticker"] == "RELIANCE"
    assert row["side"] == "LONG"
    assert row["sector"] == "ENERGY"
    assert row["regime"] == "RISK-ON"
    assert row["status"] == "OPEN"
    assert row["entry_px"] == "1300.0000"
    assert row["stop_px"] == "1250.0000"
    assert row["atr_14"] == "25.0000"


def test_basket_open_idempotent_when_basket_already_present(tmp_path, monkeypatch):
    """Re-running basket-open on a day that already has rows must be a no-op."""
    recs = tmp_path / "recommendations.csv"
    monkeypatch.setattr(fs, "_RECS_PATH", recs)

    today = "2026-04-28"
    monkeypatch.setattr(fs, "_today_iso", lambda: today)

    seed_row = {
        "basket_id": fs._basket_id(today), "leg_id": "X", "ticker": "RELIANCE",
        "date": today, "sector": "ENERGY", "sector_score": "0.02",
        "side": "LONG", "weight": "0.125", "stock_pct_at_snap": "0.03",
        "regime": "RISK-ON", "entry_time": "2026-04-28T11:00:00+05:30",
        "entry_px": "1300.0", "atr_14": "25.0", "stop_px": "1250.0",
        "exit_time": "", "exit_px": "", "exit_reason": "",
        "pnl_pct": "", "status": "OPEN",
    }
    fs._append_rec(seed_row)

    def _fail_fetch(*a, **kw):
        raise AssertionError("fetch_ltp must not be called when basket already opened")

    monkeypatch.setattr(fs, "_fetch_ltp", _fail_fetch)
    monkeypatch.setattr(fs, "_load_opens", lambda d: {"RELIANCE": 1300.0})

    rc = fs.cmd_basket_open()
    assert rc == 0
    rows = list(csv.DictReader(recs.open("r", encoding="utf-8")))
    assert len(rows) == 1


def test_basket_close_pnl_writeback(tmp_path, monkeypatch):
    recs = tmp_path / "recommendations.csv"
    monkeypatch.setattr(fs, "_RECS_PATH", recs)

    seed = [
        {"basket_id": "SECRSI-2026-04-28", "leg_id": "SECRSI-2026-04-28-A-LONG",
         "ticker": "A", "date": "2026-04-28", "sector": "X", "sector_score": "0.02",
         "side": "LONG", "weight": "0.125", "stock_pct_at_snap": "0.03",
         "regime": "RISK-ON", "entry_time": "2026-04-28T11:00:00+05:30",
         "entry_px": "100.0", "atr_14": "2.0", "stop_px": "96.0",
         "exit_time": "", "exit_px": "", "exit_reason": "", "pnl_pct": "",
         "status": "OPEN"},
        {"basket_id": "SECRSI-2026-04-28", "leg_id": "SECRSI-2026-04-28-B-SHORT",
         "ticker": "B", "date": "2026-04-28", "sector": "Y", "sector_score": "-0.02",
         "side": "SHORT", "weight": "0.125", "stock_pct_at_snap": "-0.03",
         "regime": "RISK-ON", "entry_time": "2026-04-28T11:00:00+05:30",
         "entry_px": "200.0", "atr_14": "4.0", "stop_px": "208.0",
         "exit_time": "", "exit_px": "", "exit_reason": "", "pnl_pct": "",
         "status": "OPEN"},
    ]
    fs._write_recs(seed)

    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: {"A": 102.0, "B": 195.0})
    monkeypatch.setattr(fs, "_now_iso", lambda: "2026-04-28T14:30:00+05:30")

    rc = fs.cmd_basket_close("2026-04-28")
    assert rc == 0

    rows = list(csv.DictReader(recs.open("r", encoding="utf-8")))
    by_ticker = {r["ticker"]: r for r in rows}
    # LONG A: 100 -> 102 = +2%
    assert float(by_ticker["A"]["pnl_pct"]) == pytest.approx(2.0)
    # SHORT B: 200 -> 195 = +2.5% favorable for short
    assert float(by_ticker["B"]["pnl_pct"]) == pytest.approx(2.5)
    assert by_ticker["A"]["status"] == "CLOSED"
    assert by_ticker["B"]["status"] == "CLOSED"
    assert by_ticker["A"]["exit_reason"] == "TIME_STOP"


def test_basket_close_idempotent_skips_already_closed(tmp_path, monkeypatch):
    recs = tmp_path / "recommendations.csv"
    monkeypatch.setattr(fs, "_RECS_PATH", recs)

    closed_row = {
        "basket_id": "SECRSI-2026-04-28", "leg_id": "X", "ticker": "A",
        "date": "2026-04-28", "sector": "X", "sector_score": "0.02",
        "side": "LONG", "weight": "0.125", "stock_pct_at_snap": "0.03",
        "regime": "RISK-ON", "entry_time": "2026-04-28T11:00:00+05:30",
        "entry_px": "100.0", "atr_14": "2.0", "stop_px": "96.0",
        "exit_time": "2026-04-28T14:30:00+05:30", "exit_px": "102.0",
        "exit_reason": "TIME_STOP", "pnl_pct": "2.0", "status": "CLOSED",
    }
    fs._write_recs([closed_row])

    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: pytest.fail("must not fetch"))

    rc = fs.cmd_basket_close("2026-04-28")
    assert rc == 0
    rows = list(csv.DictReader(recs.open("r", encoding="utf-8")))
    assert rows[0]["pnl_pct"] == "2.0"  # unchanged
