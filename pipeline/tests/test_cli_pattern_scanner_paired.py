"""Tests for cli_pattern_scanner paired-open / paired-close subcommands — T8c.

Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §6.5
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

import pipeline.cli_pattern_scanner as cli
from pipeline.cli_pattern_scanner import cmd_paired_open, cmd_paired_close


def _signals_doc(top_10: list[dict]) -> dict:
    return {"date": "2026-04-28", "top_10": top_10}


def _make_signal(
    signal_id: str = "2026-04-28_RELIANCE_BULLISH_HAMMER",
    ticker: str = "RELIANCE",
    pattern_id: str = "BULLISH_HAMMER",
    direction: str = "LONG",
) -> dict:
    return {
        "signal_id": signal_id,
        "ticker": ticker,
        "pattern_id": pattern_id,
        "direction": direction,
        "composite_score": 4.27,
        "z_score": 3.0,
        "n_occurrences": 156,
        "win_rate": 0.62,
        "scan_date": "2026-04-28",
    }


@pytest.fixture
def signals_file(tmp_path):
    """Write a minimal pattern_signals_today.json to tmp_path."""
    p = tmp_path / "pattern_signals_today.json"
    p.write_text(json.dumps(_signals_doc([
        _make_signal(),
        _make_signal(
            signal_id="2026-04-28_TCS_DOJI",
            ticker="TCS", pattern_id="DOJI",
        ),
    ])), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# cmd_paired_open
# ---------------------------------------------------------------------------

def test_cmd_paired_open_calls_sidecar_for_each_top10_row(tmp_path, signals_file, monkeypatch):
    """record_opens returns N; open_options_pair should be called N times."""
    fake_ltp = {"RELIANCE": 2400.0, "TCS": 3500.0}

    with patch.object(cli, "_fetch_ltp", return_value=fake_ltp) as mock_ltp, \
         patch("pipeline.research.scanner.live_paper.record_opens", return_value=2) as mock_open, \
         patch("pipeline.research.scanner.live_paper._load", return_value=[]), \
         patch("pipeline.scanner_paired_shadow.open_options_pair") as mock_sidecar:

        rc = cmd_paired_open(signals_path=signals_file)

    assert rc == 0
    assert mock_open.call_count == 1
    assert mock_sidecar.call_count == 2


def test_cmd_paired_open_continues_when_sidecar_raises(tmp_path, signals_file, monkeypatch):
    """If sidecar raises, cmd_paired_open still returns 0 (spec §5 blanket catch)."""
    fake_ltp = {"RELIANCE": 2400.0, "TCS": 3500.0}

    with patch.object(cli, "_fetch_ltp", return_value=fake_ltp), \
         patch("pipeline.research.scanner.live_paper.record_opens", return_value=2), \
         patch("pipeline.research.scanner.live_paper._load", return_value=[]), \
         patch("pipeline.scanner_paired_shadow.open_options_pair",
               side_effect=RuntimeError("Kite down")):

        rc = cmd_paired_open(signals_path=signals_file)

    assert rc == 0  # must not propagate


def test_cmd_paired_open_no_top10_returns_zero(tmp_path, tmp_path_factory, monkeypatch):
    """Empty top_10 -> returns 0, no Kite call."""
    signals_path = tmp_path / "pattern_signals_today.json"
    signals_path.write_text(json.dumps({"date": "2026-04-28", "top_10": []}))

    with patch.object(cli, "_fetch_ltp") as mock_ltp:
        rc = cmd_paired_open(signals_path=signals_path)

    assert rc == 0
    mock_ltp.assert_not_called()


def test_cmd_paired_close_calls_sidecar_for_each_closed_row(tmp_path, monkeypatch):
    """After close_at_1530, sidecar close_options_pair called once per closed row."""
    date_str = "2026-04-29"
    open_rows = [
        {
            "signal_id": "2026-04-28_RELIANCE_BULLISH_HAMMER",
            "date": date_str, "scan_date": "2026-04-28",
            "ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER",
            "side": "LONG", "composite_score": 4.27, "z_score": 3.0,
            "n_occurrences": 156, "win_rate": 0.62,
            "entry_px": 2400.0, "notional_inr": 50000, "status": "OPEN",
            "exit_px": None, "exit_time": None, "exit_reason": None,
            "pnl_gross_inr": None, "pnl_net_inr": None,
        },
    ]
    closed_rows = [dict(r, status="CLOSED", exit_px=2450.0,
                        exit_time=f"{date_str} 15:30:00",
                        exit_reason="TIME_STOP",
                        pnl_gross_inr=2500.0, pnl_net_inr=2200.0)
                   for r in open_rows]

    with patch("pipeline.research.scanner.live_paper._load", return_value=open_rows), \
         patch.object(cli, "_fetch_ltp", return_value={"RELIANCE": 2450.0}), \
         patch("pipeline.research.scanner.live_paper.close_at_1530", return_value=1), \
         patch("pipeline.research.scanner.live_paper._load",
               side_effect=[open_rows, closed_rows]), \
         patch("pipeline.scanner_paired_shadow.close_options_pair") as mock_close:

        rc = cmd_paired_close(date_override=date_str)

    assert rc == 0
    assert mock_close.call_count == 1
    mock_close.assert_called_once_with("2026-04-28_RELIANCE_BULLISH_HAMMER")
