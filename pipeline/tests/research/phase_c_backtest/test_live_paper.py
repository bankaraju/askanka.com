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


def test_close_at_1430_short_position_correct_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([{
        "date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "B",
        "side": "SHORT", "z_score": -2.5, "stop_pct": 0.02, "target_pct": 0.01,
        "entry_px": 100.0,
    }])
    live_paper.record_opens(sig)
    live_paper.close_at_1430("2026-04-20", exit_prices={"B": 95.0})
    data = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    # SHORT entered at 100, exited at 95 → +5% gain → +₹2,500 gross
    assert data[0]["status"] == "CLOSED"
    assert data[0]["pnl_gross_inr"] == pytest.approx(2500.0, abs=0.5)


def test_record_opens_with_empty_dataframe_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    n = live_paper.record_opens(pd.DataFrame(columns=["date", "symbol"]))
    assert n == 0
    assert not (tmp_path / "ledger.json").exists()


def test_close_at_1430_no_matching_dates_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([{
        "date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
        "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01,
        "entry_px": 100.0,
    }])
    live_paper.record_opens(sig)
    n = live_paper.close_at_1430("2026-04-21", exit_prices={"A": 102.0})
    assert n == 0


def test_close_at_1430_symbol_missing_from_exit_prices_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([
        {"date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
         "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0},
        {"date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "B",
         "side": "LONG", "z_score": 2.0, "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 200.0},
    ])
    live_paper.record_opens(sig)
    n = live_paper.close_at_1430("2026-04-20", exit_prices={"A": 102.0})
    assert n == 1
    data = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    closed = [e for e in data if e["status"] == "CLOSED"]
    open_ = [e for e in data if e["status"] == "OPEN"]
    assert len(closed) == 1 and closed[0]["symbol"] == "A"
    assert len(open_) == 1 and open_[0]["symbol"] == "B"


def test_record_opens_handles_pd_timestamp_signal_time(tmp_path, monkeypatch):
    """Signals from simulator_intraday may carry pd.Timestamp; must serialize."""
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    sig = pd.DataFrame([{
        "date": "2026-04-20",
        "signal_time": pd.Timestamp("2026-04-20 09:30:00"),
        "symbol": "A", "side": "LONG", "z_score": 2.5,
        "stop_pct": 0.02, "target_pct": 0.01, "entry_px": 100.0,
    }])
    live_paper.record_opens(sig)
    data = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert isinstance(data[0]["signal_time"], str)


def test_load_recovers_from_corrupt_ledger(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", tmp_path / "ledger.json")
    (tmp_path / "ledger.json").write_text("{ this is not valid json", encoding="utf-8")
    with caplog.at_level("WARNING", logger="pipeline.research.phase_c_backtest.live_paper"):
        sig = pd.DataFrame([{
            "date": "2026-04-20", "signal_time": "2026-04-20 09:30:00", "symbol": "A",
            "side": "LONG", "z_score": 2.5, "stop_pct": 0.02, "target_pct": 0.01,
            "entry_px": 100.0,
        }])
        n = live_paper.record_opens(sig)
    assert n == 1
    assert any("corrupt live_paper ledger" in r.message for r in caplog.records)
