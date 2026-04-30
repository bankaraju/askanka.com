"""Smoke tests for H-2026-04-26-001 paper-trade module.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md

These tests use synthetic correlation_breaks.json + monkeypatched fetch_ltp /
compute_atr_stop. They must NOT touch live Kite or yfinance.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline import h_2026_04_26_001_paper as paper


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _breaks_doc(rows: list[dict], date: str = "2026-04-27") -> dict:
    return {
        "date": date,
        "scan_time": f"{date} 09:30:00",
        "breaks": rows,
    }


def _row(symbol: str, z: float, *, sectoral_index: str = "NIFTYIT",
         classification: str = "OPPORTUNITY_OVERSHOOT") -> dict:
    return {
        "symbol": symbol,
        "z_score": z,
        "classification": classification,
        "sectoral_index": sectoral_index,
        "expected_return": -z * 0.5,  # arbitrary but deterministic
        "actual_return": -z * 1.0,
    }


@pytest.fixture
def stub_env(tmp_path, monkeypatch):
    """Set up: temp recommendations.csv, stub LTP, stub ATR, stub regime, stub today."""
    rec_path = tmp_path / "recommendations.csv"
    monkeypatch.setattr(paper, "_RECS_PATH", rec_path)

    # Default stubs — tests can override
    monkeypatch.setattr(paper, "_fetch_ltp",
                        lambda syms: {s: 100.0 for s in syms})
    monkeypatch.setattr(
        paper, "_compute_atr_stop",
        lambda symbol, direction: {
            "stop_pct": -2.0, "stop_price": 98.0 if direction == "LONG" else 102.0,
            "atr_14": 1.0, "stop_source": "atr_14",
        },
    )
    monkeypatch.setattr(paper, "_load_today_regime_zone", lambda: "CAUTION")
    monkeypatch.setattr(paper, "_today_iso", lambda: "2026-04-27")
    monkeypatch.setattr(paper, "_now_iso", lambda: "2026-04-27T09:30:00+05:30")
    return {"rec_path": rec_path, "tmp": tmp_path}


def _write_breaks(tmp_path, monkeypatch, rows, date="2026-04-27"):
    breaks_path = tmp_path / "correlation_breaks.json"
    breaks_path.write_text(json.dumps(_breaks_doc(rows, date=date)), encoding="utf-8")
    monkeypatch.setattr(paper, "_BREAKS_PATH", breaks_path)
    return breaks_path


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 1. Filter: |z| >= 2.0
# ---------------------------------------------------------------------------

def test_open_filters_below_2_sigma(stub_env, tmp_path, monkeypatch):
    rows = [
        _row("AAA", 1.5),   # below threshold — drop
        _row("BBB", 2.0),   # exactly at threshold — keep
        _row("CCC", 3.0),   # above — keep
        _row("DDD", -1.5),  # below threshold (abs) — drop
        _row("EEE", -2.5),  # above threshold (abs, negative) — keep
    ]
    _write_breaks(tmp_path, monkeypatch, rows)
    rc = paper.cmd_open()
    assert rc == 0
    written = _read_csv(stub_env["rec_path"])
    assert sorted(r["ticker"] for r in written) == ["BBB", "CCC", "EEE"]


# ---------------------------------------------------------------------------
# 2. Side direction: FADE the divergence
# ---------------------------------------------------------------------------

def test_open_assigns_correct_side(stub_env, tmp_path, monkeypatch):
    rows = [
        _row("LEADER", 2.5),    # z>0 → SHORT (fade outperformance)
        _row("LAGGARD", -2.5),  # z<0 → LONG (fade underperformance)
    ]
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()
    written = {r["ticker"]: r for r in _read_csv(stub_env["rec_path"])}
    assert written["LEADER"]["side"] == "SHORT"
    assert written["LAGGARD"]["side"] == "LONG"


# ---------------------------------------------------------------------------
# 3. Idempotent open
# ---------------------------------------------------------------------------

def test_open_idempotent(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", 2.5)]
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()
    paper.cmd_open()  # second invocation should be no-op
    written = _read_csv(stub_env["rec_path"])
    assert len(written) == 1
    assert written[0]["ticker"] == "ACME"


# ---------------------------------------------------------------------------
# 4. Close: marks status=CLOSED + populates exit_px + pnl_pct
# ---------------------------------------------------------------------------

def test_close_marks_status_closed_with_pnl(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", -2.5)]  # LONG @ 100
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()

    # Now stub LTP at 102 for the close
    monkeypatch.setattr(paper, "_fetch_ltp", lambda syms: {s: 102.0 for s in syms})
    monkeypatch.setattr(paper, "_now_iso", lambda: "2026-04-27T14:30:00+05:30")
    rc = paper.cmd_close()
    assert rc == 0

    written = _read_csv(stub_env["rec_path"])
    row = written[0]
    assert row["status"] == "CLOSED"
    assert float(row["exit_px"]) == pytest.approx(102.0)
    # LONG, +2% → pnl_pct = +2.0
    assert float(row["pnl_pct"]) == pytest.approx(2.0)
    assert row["exit_reason"] == "TIME_STOP"
    assert row["exit_time"] == "2026-04-27T14:30:00+05:30"


def test_close_short_pnl_sign(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", 2.5)]  # SHORT @ 100
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()

    # SHORT closing at 98 → +2% pnl
    monkeypatch.setattr(paper, "_fetch_ltp", lambda syms: {s: 98.0 for s in syms})
    paper.cmd_close()
    row = _read_csv(stub_env["rec_path"])[0]
    assert row["side"] == "SHORT"
    assert float(row["pnl_pct"]) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 5. Close idempotent
# ---------------------------------------------------------------------------

def test_close_idempotent(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", -2.5)]
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()
    monkeypatch.setattr(paper, "_fetch_ltp", lambda syms: {s: 105.0 for s in syms})
    paper.cmd_close()
    first = _read_csv(stub_env["rec_path"])[0]

    # Second close should not double-write or re-update the row
    monkeypatch.setattr(paper, "_fetch_ltp", lambda syms: {s: 999.0 for s in syms})
    paper.cmd_close()
    second = _read_csv(stub_env["rec_path"])
    assert len(second) == 1
    assert second[0]["exit_px"] == first["exit_px"]
    assert second[0]["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# 6. regime_gate_pass column
# ---------------------------------------------------------------------------

def test_regime_gate_pass_column(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", -2.5)]
    _write_breaks(tmp_path, monkeypatch, rows)

    # NEUTRAL regime → gate FAILS (False)
    monkeypatch.setattr(paper, "_load_today_regime_zone", lambda: "NEUTRAL")
    paper.cmd_open()
    written = _read_csv(stub_env["rec_path"])
    assert written[0]["regime"] == "NEUTRAL"
    assert written[0]["regime_gate_pass"] == "False"


def test_regime_gate_pass_caution_passes(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", -2.5)]
    _write_breaks(tmp_path, monkeypatch, rows)
    monkeypatch.setattr(paper, "_load_today_regime_zone", lambda: "CAUTION")
    paper.cmd_open()
    written = _read_csv(stub_env["rec_path"])
    assert written[0]["regime"] == "CAUTION"
    assert written[0]["regime_gate_pass"] == "True"


# ---------------------------------------------------------------------------
# 7. Spec-mandated columns (§14)
# ---------------------------------------------------------------------------

def test_csv_has_all_spec_columns(stub_env, tmp_path, monkeypatch):
    rows = [_row("ACME", -2.5, sectoral_index="NIFTYIT")]
    _write_breaks(tmp_path, monkeypatch, rows)
    paper.cmd_open()
    written = _read_csv(stub_env["rec_path"])[0]
    for col in (
        "signal_id", "ticker", "date", "sigma_bucket", "regime",
        "sectoral_index", "side", "classification", "regime_gate_pass",
        "entry_time", "entry_px", "atr_14", "stop_px",
        "trail_arm_px", "trail_dist_pct", "exit_time", "exit_px",
        "exit_reason", "pnl_pct", "status",
    ):
        assert col in written, f"missing CSV column: {col}"
    assert written["status"] == "OPEN"
    assert written["sectoral_index"] == "NIFTYIT"
    assert written["signal_id"] == "BRK-2026-04-27-ACME"


# ---------------------------------------------------------------------------
# 7b. _load_today_regime_zone reads today_regime.json (canonical live source)
# ---------------------------------------------------------------------------

def test_load_today_regime_zone_reads_live_source(tmp_path, monkeypatch):
    """Canonical zone is read from today_regime.json, not regime_history.csv."""
    p = tmp_path / "today_regime.json"
    p.write_text(json.dumps({"zone": "NEUTRAL", "regime": "NEUTRAL"}),
                 encoding="utf-8")
    monkeypatch.setattr(paper, "_TODAY_REGIME_PATH", p)
    assert paper._load_today_regime_zone() == "NEUTRAL"


def test_load_today_regime_zone_missing_file_returns_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(paper, "_TODAY_REGIME_PATH", tmp_path / "nope.json")
    assert paper._load_today_regime_zone() == "UNKNOWN"


def test_load_today_regime_zone_invalid_json_returns_unknown(tmp_path, monkeypatch):
    p = tmp_path / "today_regime.json"
    p.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(paper, "_TODAY_REGIME_PATH", p)
    assert paper._load_today_regime_zone() == "UNKNOWN"


# ---------------------------------------------------------------------------
# 8. CLI parser exposes open / close / close --date
# ---------------------------------------------------------------------------

def test_cli_help_runs():
    """`python -m pipeline.h_2026_04_26_001_paper --help` must build a parser."""
    import argparse
    parser = paper._build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    # open subcommand
    args = parser.parse_args(["open"])
    assert args.cmd == "open"
    # close subcommand
    args = parser.parse_args(["close"])
    assert args.cmd == "close"
    assert args.date is None
    # close --date YYYY-MM-DD
    args = parser.parse_args(["close", "--date", "2026-05-01"])
    assert args.cmd == "close"
    assert args.date == "2026-05-01"
