"""Tests for the F3 live shadow paper-trade ledger."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import live_paper


def test_record_opens_appends_to_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    signals = pd.DataFrame([
        {"date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
         "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0},
    ])
    live_paper.record_opens(signals)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert len(data) == 1
    assert data[0]["tag"].startswith("PHASE_C_VERIFY_2026-04-20_")
    assert data[0]["status"] == "OPEN"


def test_record_opens_idempotent_for_same_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([
        {"date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
         "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0},
    ])
    live_paper.record_opens(sig)
    live_paper.record_opens(sig)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert len(data) == 1


def test_close_at_1430_marks_status_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([
        {"date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
         "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0},
    ])
    live_paper.record_opens(sig)
    live_paper.close_at_1430("2026-04-20", exit_prices={"A": 102.0})
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert data[0]["status"] == "CLOSED"
    assert data[0]["exit_px"] == 102.0
    assert data[0]["pnl_gross_inr"] == pytest.approx((102.0 - 100.0) / 100.0 * 50000, abs=0.01)
