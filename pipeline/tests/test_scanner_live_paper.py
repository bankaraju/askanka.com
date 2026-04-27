"""Tests for pipeline.research.scanner.live_paper — Scanner futures-side ledger.

Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §7.3, §8.4
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import pipeline.research.scanner.live_paper as live_paper
from pipeline.research.scanner.live_paper import record_opens, close_at_1530


@pytest.fixture(autouse=True)
def _patch_ledger_path(tmp_path, monkeypatch):
    """Redirect ledger writes to a temp dir for every test."""
    ledger = tmp_path / "live_paper_scanner_futures_ledger.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger)
    return ledger


def _make_row(
    signal_id: str = "2026-04-28_RELIANCE_BULLISH_HAMMER",
    ticker: str = "RELIANCE",
    pattern_id: str = "BULLISH_HAMMER",
    direction: str = "LONG",
    composite_score: float = 4.27,
    z_score: float = 3.0,
    n_occurrences: int = 156,
    win_rate: float = 0.62,
    scan_date: str = "2026-04-28",
) -> dict:
    return {
        "signal_id": signal_id,
        "ticker": ticker,
        "pattern_id": pattern_id,
        "direction": direction,
        "composite_score": composite_score,
        "z_score": z_score,
        "n_occurrences": n_occurrences,
        "win_rate": win_rate,
        "scan_date": scan_date,
    }


# ---------------------------------------------------------------------------
# record_opens
# ---------------------------------------------------------------------------

def test_record_opens_idempotent_on_signal_id(tmp_path, monkeypatch):
    """Calling twice with the same top_10 rows is a no-op on the second call."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [_make_row()]
    ltp = {"RELIANCE": 2400.0}

    n1 = record_opens(rows, ltp)
    n2 = record_opens(rows, ltp)

    assert n1 == 1
    assert n2 == 0
    loaded = json.loads(ledger_path.read_text())
    assert len(loaded) == 1


def test_record_opens_writes_signal_provenance(tmp_path, monkeypatch):
    """All scanner provenance fields are persisted to the ledger row."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    row = _make_row(
        composite_score=5.12, z_score=3.8, n_occurrences=200, win_rate=0.70,
        pattern_id="MACD_BULL_CROSS",
    )
    n = record_opens([row], {"RELIANCE": 3000.0})

    assert n == 1
    loaded = json.loads(ledger_path.read_text())
    entry = loaded[0]
    assert entry["pattern_id"] == "MACD_BULL_CROSS"
    assert entry["composite_score"] == 5.12
    assert abs(entry["z_score"] - 3.8) < 1e-9
    assert entry["n_occurrences"] == 200
    assert abs(entry["win_rate"] - 0.70) < 1e-9
    assert entry["ticker"] == "RELIANCE"
    assert entry["entry_px"] == 3000.0
    assert entry["status"] == "OPEN"
    assert entry["notional_inr"] == 50_000


def test_record_opens_skips_tickers_without_ltp(tmp_path, monkeypatch, caplog):
    """Rows whose ticker has no LTP entry are silently skipped."""
    import logging
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [
        _make_row(signal_id="2026-04-28_RELIANCE_BULLISH_HAMMER", ticker="RELIANCE"),
        _make_row(signal_id="2026-04-28_TCS_DOJI", ticker="TCS"),
    ]
    ltp = {"RELIANCE": 2400.0}  # TCS missing

    with caplog.at_level(logging.DEBUG, logger="pipeline.research.scanner.live_paper"):
        n = record_opens(rows, ltp)

    assert n == 1
    loaded = json.loads(ledger_path.read_text())
    assert len(loaded) == 1
    assert loaded[0]["ticker"] == "RELIANCE"


def test_close_at_1530_long_pnl(tmp_path, monkeypatch):
    """LONG row: entry 100, exit 105 -> pnl_gross +5%, pnl_net < +5%."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    # Pre-seed with an OPEN row
    seed = {
        "tag": "SCANNER_VERIFY_2026-04-29_1",
        "signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
        "date": "2026-04-29",
        "scan_date": "2026-04-28",
        "ticker": "RELIANCE",
        "pattern_id": "BULLISH_HAMMER",
        "side": "LONG",
        "composite_score": 4.27,
        "z_score": 3.0,
        "n_occurrences": 156,
        "win_rate": 0.62,
        "entry_px": 100.0,
        "notional_inr": 50_000,
        "status": "OPEN",
        "exit_px": None, "exit_time": None, "exit_reason": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }
    ledger_path.write_text(json.dumps([seed]))

    n = close_at_1530("2026-04-29", {"RELIANCE": 105.0})

    assert n == 1
    row = json.loads(ledger_path.read_text())[0]
    assert row["status"] == "CLOSED"
    assert row["exit_px"] == 105.0
    assert row["exit_reason"] == "TIME_STOP"
    assert row["exit_time"] == "2026-04-29 15:30:00"
    expected_gross = (105.0 - 100.0) / 100.0 * 50_000  # +2500 INR
    assert abs(row["pnl_gross_inr"] - expected_gross) < 1e-6
    # Cost subtracted → net < gross
    assert row["pnl_net_inr"] < row["pnl_gross_inr"]


def test_close_at_1530_short_pnl(tmp_path, monkeypatch):
    """SHORT row: entry 100, exit 95 -> pnl_gross +5%, pnl_net < +5%."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    seed = {
        "tag": "SCANNER_VERIFY_2026-04-29_1",
        "signal_id": "2026-04-28_RELIANCE_BEAR_ENG",
        "date": "2026-04-29",
        "scan_date": "2026-04-28",
        "ticker": "RELIANCE",
        "pattern_id": "BEAR_ENGULFING",
        "side": "SHORT",
        "composite_score": 3.5,
        "z_score": 2.5,
        "n_occurrences": 100,
        "win_rate": 0.60,
        "entry_px": 100.0,
        "notional_inr": 50_000,
        "status": "OPEN",
        "exit_px": None, "exit_time": None, "exit_reason": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }
    ledger_path.write_text(json.dumps([seed]))

    n = close_at_1530("2026-04-29", {"RELIANCE": 95.0})

    assert n == 1
    row = json.loads(ledger_path.read_text())[0]
    assert row["status"] == "CLOSED"
    expected_gross = (100.0 - 95.0) / 100.0 * 50_000  # +2500 INR SHORT
    assert abs(row["pnl_gross_inr"] - expected_gross) < 1e-6
    assert row["pnl_net_inr"] < row["pnl_gross_inr"]


def test_close_at_1530_skips_no_exit_price(tmp_path, monkeypatch, caplog):
    """Rows with no exit price in the dict are silently skipped; row stays OPEN."""
    import logging
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    seed = {
        "tag": "T1", "signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
        "date": "2026-04-29", "scan_date": "2026-04-28",
        "ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER",
        "side": "LONG", "composite_score": 4.0, "z_score": 3.0,
        "n_occurrences": 100, "win_rate": 0.60,
        "entry_px": 100.0, "notional_inr": 50_000, "status": "OPEN",
        "exit_px": None, "exit_time": None, "exit_reason": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }
    ledger_path.write_text(json.dumps([seed]))

    with caplog.at_level(logging.DEBUG, logger="pipeline.research.scanner.live_paper"):
        n = close_at_1530("2026-04-29", {})  # no prices at all

    assert n == 0
    row = json.loads(ledger_path.read_text())[0]
    assert row["status"] == "OPEN"


def test_close_at_1530_idempotent(tmp_path, monkeypatch):
    """Calling close twice does not double-mutate the P&L."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    seed = {
        "tag": "T1", "signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
        "date": "2026-04-29", "scan_date": "2026-04-28",
        "ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER",
        "side": "LONG", "composite_score": 4.0, "z_score": 3.0,
        "n_occurrences": 100, "win_rate": 0.60,
        "entry_px": 100.0, "notional_inr": 50_000, "status": "OPEN",
        "exit_px": None, "exit_time": None, "exit_reason": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }
    ledger_path.write_text(json.dumps([seed]))

    n1 = close_at_1530("2026-04-29", {"RELIANCE": 105.0})
    n2 = close_at_1530("2026-04-29", {"RELIANCE": 999.0})  # second call with diff price

    assert n1 == 1
    assert n2 == 0  # already CLOSED, skipped
    row = json.loads(ledger_path.read_text())[0]
    assert row["exit_px"] == 105.0  # not overwritten


def test_two_patterns_same_ticker_same_day_distinct_rows(tmp_path, monkeypatch):
    """RELIANCE fires BULLISH_HAMMER and MACD_BULL_CROSS -> 2 distinct rows by signal_id."""
    ledger_path = tmp_path / "led.json"
    monkeypatch.setattr(live_paper, "_LEDGER_PATH", ledger_path)

    rows = [
        _make_row(
            signal_id="2026-04-28_RELIANCE_BULLISH_HAMMER",
            ticker="RELIANCE", pattern_id="BULLISH_HAMMER",
        ),
        _make_row(
            signal_id="2026-04-28_RELIANCE_MACD_BULL_CROSS",
            ticker="RELIANCE", pattern_id="MACD_BULL_CROSS",
        ),
    ]
    n = record_opens(rows, {"RELIANCE": 2400.0})

    assert n == 2
    loaded = json.loads(ledger_path.read_text())
    assert len(loaded) == 2
    ids = {r["signal_id"] for r in loaded}
    assert "2026-04-28_RELIANCE_BULLISH_HAMMER" in ids
    assert "2026-04-28_RELIANCE_MACD_BULL_CROSS" in ids
