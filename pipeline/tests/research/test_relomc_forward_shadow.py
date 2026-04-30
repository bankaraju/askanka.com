"""Tests for pipeline.research.h_2026_04_30_relomc.forward_shadow.

Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.research.h_2026_04_30_relomc import forward_shadow as fs


@pytest.fixture
def tmp_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rec = tmp_path / "recommendations.csv"
    monkeypatch.setattr(fs, "_RECS_PATH", rec)
    monkeypatch.setattr(fs, "_RESEARCH_DIR", tmp_path)
    return rec


@pytest.fixture
def regime_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "today_regime.json"
    monkeypatch.setattr(fs, "_TODAY_REGIME_PATH", p)
    return p


def _set_regime(path: Path, zone: str) -> None:
    path.write_text(json.dumps({"zone": zone}), encoding="utf-8")


def _today_in_holdout() -> str:
    """Pick a date inside HOLDOUT_START..HOLDOUT_END that is also a trading day."""
    from pipeline.trading_calendar import is_trading_day
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    d = fs.HOLDOUT_START
    while not is_trading_day(datetime.combine(d, datetime.min.time(), tzinfo=IST)):
        d = d + timedelta(days=1)
    return d.isoformat()


def test_basket_open_skips_when_regime_not_euphoria(tmp_ledger, regime_path, monkeypatch):
    _set_regime(regime_path, "RISK-ON")
    today = _today_in_holdout()
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    rc = fs.cmd_basket_open()
    assert rc == 0
    assert not tmp_ledger.exists()


def test_basket_open_skips_outside_holdout(tmp_ledger, regime_path, monkeypatch):
    _set_regime(regime_path, "EUPHORIA")
    monkeypatch.setattr(fs, "_today_iso", lambda: "2026-04-30")  # before HOLDOUT_START
    rc = fs.cmd_basket_open()
    assert rc == 0
    assert not tmp_ledger.exists()


def test_basket_open_writes_3_legs_when_euphoria(tmp_ledger, regime_path, monkeypatch):
    _set_regime(regime_path, "EUPHORIA")
    today = _today_in_holdout()
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda symbols: {"RELIANCE": 2950.0, "BPCL": 320.0, "IOC": 145.0},
    )
    rc = fs.cmd_basket_open()
    assert rc == 0

    rows = list(csv.DictReader(open(tmp_ledger, encoding="utf-8")))
    assert len(rows) == 3
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["RELIANCE"]["side"] == "LONG"
    assert by_ticker["BPCL"]["side"] == "SHORT"
    assert by_ticker["IOC"]["side"] == "SHORT"
    assert all(r["status"] == "OPEN" for r in rows)
    assert all(r["regime_at_entry"] == "EUPHORIA" for r in rows)
    # weights: LONG = 1/1 = 1.0; SHORT = -1/2 = -0.5
    assert float(by_ticker["RELIANCE"]["weight"]) == pytest.approx(1.0)
    assert float(by_ticker["BPCL"]["weight"]) == pytest.approx(-0.5)
    # target_close_date is 5 trading days ahead
    target = by_ticker["RELIANCE"]["target_close_date"]
    assert target > today


def test_basket_open_idempotent(tmp_ledger, regime_path, monkeypatch):
    _set_regime(regime_path, "EUPHORIA")
    today = _today_in_holdout()
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda symbols: {"RELIANCE": 2950.0, "BPCL": 320.0, "IOC": 145.0},
    )
    fs.cmd_basket_open()
    fs.cmd_basket_open()  # second call is a no-op
    rows = list(csv.DictReader(open(tmp_ledger, encoding="utf-8")))
    assert len(rows) == 3


def test_basket_open_aborts_if_missing_ltp(tmp_ledger, regime_path, monkeypatch):
    _set_regime(regime_path, "EUPHORIA")
    today = _today_in_holdout()
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda symbols: {"RELIANCE": 2950.0},  # BPCL/IOC missing
    )
    rc = fs.cmd_basket_open()
    assert rc == 1
    assert not tmp_ledger.exists()


def test_basket_pnl_bps_long_only_up(tmp_ledger):
    rows = [
        {"ticker": "RELIANCE", "side": "LONG", "weight": "1.0", "entry_px": "2900.0"},
        {"ticker": "BPCL", "side": "SHORT", "weight": "-0.5", "entry_px": "320.0"},
        {"ticker": "IOC", "side": "SHORT", "weight": "-0.5", "entry_px": "145.0"},
    ]
    # all three move favorably: RELIANCE +1%, BPCL -1%, IOC -1%
    ltp = {"RELIANCE": 2929.0, "BPCL": 316.8, "IOC": 143.55}
    pnl = fs._basket_pnl_bps(rows, ltp)
    # weighted return = (1.0 * +0.01 + (-0.5) * -0.01 + (-0.5) * -0.01) / 2.0
    #                 = (0.01 + 0.005 + 0.005) / 2.0 = 0.01 -> 100 bps
    assert pnl == pytest.approx(100.0, abs=0.5)


def test_basket_monitor_fires_stop_when_pnl_breaches(tmp_ledger, monkeypatch):
    today = _today_in_holdout()
    target_close = fs._add_trading_days(date.fromisoformat(today), fs.HOLD_TRADING_DAYS).isoformat()
    rows = [
        {
            "basket_id": "RELOMC-X", "leg_id": "RELOMC-X-RELIANCE-LONG",
            "ticker": "RELIANCE", "side": "LONG", "weight": "1.0",
            "entry_date": today, "entry_time": "T",
            "entry_px": "2900.0", "regime_at_entry": "EUPHORIA",
            "target_close_date": target_close,
            "exit_date": "", "exit_time": "", "exit_px": "",
            "exit_reason": "", "pnl_pct": "", "status": "OPEN",
            "regime_pit_corrected": "", "regime_correction_reason": "",
        },
        {
            "basket_id": "RELOMC-X", "leg_id": "RELOMC-X-BPCL-SHORT",
            "ticker": "BPCL", "side": "SHORT", "weight": "-0.5",
            "entry_date": today, "entry_time": "T",
            "entry_px": "320.0", "regime_at_entry": "EUPHORIA",
            "target_close_date": target_close,
            "exit_date": "", "exit_time": "", "exit_px": "",
            "exit_reason": "", "pnl_pct": "", "status": "OPEN",
            "regime_pit_corrected": "", "regime_correction_reason": "",
        },
        {
            "basket_id": "RELOMC-X", "leg_id": "RELOMC-X-IOC-SHORT",
            "ticker": "IOC", "side": "SHORT", "weight": "-0.5",
            "entry_date": today, "entry_time": "T",
            "entry_px": "145.0", "regime_at_entry": "EUPHORIA",
            "target_close_date": target_close,
            "exit_date": "", "exit_time": "", "exit_px": "",
            "exit_reason": "", "pnl_pct": "", "status": "OPEN",
            "regime_pit_corrected": "", "regime_correction_reason": "",
        },
    ]
    fs._write_recs(rows)
    # RELIANCE -10% (catastrophic for LONG); BPCL +5% (bad for SHORT); IOC +5% (bad for SHORT)
    # weighted return = (1.0 * -0.10 + (-0.5)*0.05 + (-0.5)*0.05) / 2.0 = -0.0625 -> -625bp
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda syms: {"RELIANCE": 2610.0, "BPCL": 336.0, "IOC": 152.25},
    )
    monkeypatch.setattr(fs, "_today_iso", lambda: today)

    rc = fs.cmd_basket_monitor()
    assert rc == 0
    rows_after = fs._read_recs()
    assert all(r["status"] == "CLOSED" for r in rows_after)
    assert all(r["exit_reason"] == "BASKET_STOP" for r in rows_after)


def test_basket_close_only_fires_at_target_date(tmp_ledger, monkeypatch):
    today = _today_in_holdout()
    rows = [
        {
            "basket_id": "RELOMC-Y", "leg_id": "RELOMC-Y-RELIANCE-LONG",
            "ticker": "RELIANCE", "side": "LONG", "weight": "1.0",
            "entry_date": today, "entry_time": "T", "entry_px": "2900.0",
            "regime_at_entry": "EUPHORIA",
            # target_close in the FUTURE
            "target_close_date": "2099-01-01",
            "exit_date": "", "exit_time": "", "exit_px": "",
            "exit_reason": "", "pnl_pct": "", "status": "OPEN",
            "regime_pit_corrected": "", "regime_correction_reason": "",
        },
    ]
    fs._write_recs(rows)
    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: {"RELIANCE": 2950.0})
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    rc = fs.cmd_basket_close()
    assert rc == 0
    rows_after = fs._read_recs()
    assert rows_after[0]["status"] == "OPEN"


def test_basket_close_fires_when_target_reached(tmp_ledger, monkeypatch):
    rows = [
        {
            "basket_id": "RELOMC-Z", "leg_id": "RELOMC-Z-RELIANCE-LONG",
            "ticker": "RELIANCE", "side": "LONG", "weight": "1.0",
            "entry_date": "2026-05-04", "entry_time": "T", "entry_px": "2900.0",
            "regime_at_entry": "EUPHORIA",
            "target_close_date": "2026-05-11",
            "exit_date": "", "exit_time": "", "exit_px": "",
            "exit_reason": "", "pnl_pct": "", "status": "OPEN",
            "regime_pit_corrected": "", "regime_correction_reason": "",
        },
    ]
    fs._write_recs(rows)
    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: {"RELIANCE": 3000.0})
    rc = fs.cmd_basket_close(target_date_iso="2026-05-11")
    assert rc == 0
    rows_after = fs._read_recs()
    assert rows_after[0]["status"] == "CLOSED"
    assert rows_after[0]["exit_reason"] == "TIME_STOP"
    # +100/2900 = +3.448%
    assert float(rows_after[0]["pnl_pct"]) == pytest.approx(3.448, abs=0.01)
