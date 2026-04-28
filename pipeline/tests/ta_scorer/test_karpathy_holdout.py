"""Smoke tests for H-2026-04-29-ta-karpathy-v1 holdout paper-trade module.

Spec: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md sections 10/14/15.

These tests use synthetic today_predictions.json + manifest.json plus
monkeypatched fetch_ltp / compute_atr_stop. They must NOT touch live Kite
or yfinance.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline.ta_scorer import karpathy_holdout as kh


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _predictions_doc(rows: list[dict]) -> dict:
    return {
        "hypothesis_id": "H-2026-04-29-ta-karpathy-v1",
        "generated_at": "2026-04-29T04:30:00+05:30",
        "n_predictions": len(rows),
        "predictions": rows,
    }


def _pred(ticker: str, *, p_long: float | None = None, p_short: float | None = None,
          signal_long: bool = False, signal_short: bool = False) -> dict:
    return {
        "ticker": ticker,
        "asof_date": "2026-04-28",
        "predicted_for_open": "T+1 09:15 IST",
        "p_long": p_long,
        "p_short": p_short,
        "signal_long": signal_long,
        "signal_short": signal_short,
    }


def _manifest_doc(qualifying_cells: list[tuple[str, str]]) -> dict:
    cells = []
    seen = {(t, d) for t, d in qualifying_cells}
    for ticker in {t for t, _ in qualifying_cells} | {"NONQUALIFIER"}:
        for direction in ("long", "short"):
            cells.append({
                "ticker": ticker,
                "direction": direction,
                "qualifier_pass": (ticker, direction) in seen,
            })
    return {
        "hypothesis_id": "H-2026-04-29-ta-karpathy-v1",
        "qualifier_summary_per_cell": cells,
    }


@pytest.fixture
def stub_env(tmp_path, monkeypatch):
    rec_path = tmp_path / "recommendations.csv"
    pred_path = tmp_path / "today_predictions.json"
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(kh, "_RECS_PATH", rec_path)
    monkeypatch.setattr(kh, "_PREDICTIONS_PATH", pred_path)
    monkeypatch.setattr(kh, "_MANIFEST_PATH", manifest_path)

    monkeypatch.setattr(kh, "_fetch_ltp",
                        lambda syms: {s: 100.0 for s in syms})
    monkeypatch.setattr(
        kh, "_compute_atr_stop",
        lambda symbol, direction: {
            "stop_pct": -2.0, "stop_price": 98.0 if direction == "LONG" else 102.0,
            "atr_14": 1.0, "stop_source": "atr_14",
        },
    )
    monkeypatch.setattr(kh, "_load_today_regime_zone", lambda: "NEUTRAL")
    monkeypatch.setattr(kh, "_today_iso", lambda: "2026-04-29")
    monkeypatch.setattr(kh, "_now_iso", lambda: "2026-04-29T09:15:00+05:30")
    return {"rec_path": rec_path, "pred_path": pred_path, "manifest_path": manifest_path}


def _write_predictions(stub_env, rows: list[dict]) -> None:
    stub_env["pred_path"].write_text(json.dumps(_predictions_doc(rows)), encoding="utf-8")


def _write_manifest(stub_env, qualifying_cells: list[tuple[str, str]]) -> None:
    stub_env["manifest_path"].write_text(
        json.dumps(_manifest_doc(qualifying_cells)), encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 1. Holdout window guard
# ---------------------------------------------------------------------------

def test_open_blocked_before_holdout_window(stub_env, monkeypatch):
    monkeypatch.setattr(kh, "_today_iso", lambda: "2026-04-28")
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    assert _read_csv(stub_env["rec_path"]) == []


def test_open_blocked_after_holdout_window(stub_env, monkeypatch):
    monkeypatch.setattr(kh, "_today_iso", lambda: "2026-05-29")
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    assert _read_csv(stub_env["rec_path"]) == []


def test_open_allowed_on_first_day(stub_env, monkeypatch):
    monkeypatch.setattr(kh, "_today_iso", lambda: "2026-04-29")
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    assert len(_read_csv(stub_env["rec_path"])) == 1


def test_open_allowed_on_last_day(stub_env, monkeypatch):
    monkeypatch.setattr(kh, "_today_iso", lambda: "2026-05-28")
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    assert len(_read_csv(stub_env["rec_path"])) == 1


# ---------------------------------------------------------------------------
# 2. Qualifier_pass gate
# ---------------------------------------------------------------------------

def test_open_filters_non_qualifying_cells(stub_env):
    _write_predictions(stub_env, [
        _pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True),
        _pred("INFY", p_long=0.65, p_short=0.3, signal_long=True),
    ])
    _write_manifest(stub_env, [("RELIANCE", "long")])  # only RELIANCE long qualifies
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert [r["ticker"] for r in rows] == ["RELIANCE"]


def test_open_skips_when_no_cells_qualify(stub_env):
    _write_predictions(stub_env, [
        _pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True),
    ])
    _write_manifest(stub_env, [])  # no qualifiers
    assert kh.cmd_open() == 0
    assert _read_csv(stub_env["rec_path"]) == []


def test_open_skips_when_manifest_missing(stub_env):
    _write_predictions(stub_env, [
        _pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True),
    ])
    # do NOT write manifest
    assert kh.cmd_open() == 0
    assert _read_csv(stub_env["rec_path"]) == []


# ---------------------------------------------------------------------------
# 3. Direction handling (signal -> side)
# ---------------------------------------------------------------------------

def test_open_long_signal_writes_long_side(stub_env):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 1
    assert rows[0]["side"] == "LONG"
    assert rows[0]["direction"] == "long"


def test_open_short_signal_writes_short_side(stub_env):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.3, p_short=0.7, signal_short=True)])
    _write_manifest(stub_env, [("RELIANCE", "short")])
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 1
    assert rows[0]["side"] == "SHORT"
    assert rows[0]["direction"] == "short"


def test_open_no_signal_writes_nothing(stub_env):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.5, p_short=0.5)])
    _write_manifest(stub_env, [("RELIANCE", "long"), ("RELIANCE", "short")])
    assert kh.cmd_open() == 0
    assert _read_csv(stub_env["rec_path"]) == []


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------

def test_open_idempotent_on_rerun(stub_env):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 1


def test_open_long_and_short_same_ticker_writes_two_rows(stub_env):
    """Edge case: spec section 10 says (LONG entry rule) AND (SHORT entry rule)
    can both fire on rare days. Both rows should be written.
    """
    _write_predictions(stub_env, [
        _pred("RELIANCE", p_long=0.7, p_short=0.7, signal_long=True, signal_short=True),
    ])
    _write_manifest(stub_env, [("RELIANCE", "long"), ("RELIANCE", "short")])
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 2
    sides = sorted(r["side"] for r in rows)
    assert sides == ["LONG", "SHORT"]


# ---------------------------------------------------------------------------
# 5. CLOSE behavior
# ---------------------------------------------------------------------------

def test_close_marks_open_rows_closed(stub_env, monkeypatch):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0

    monkeypatch.setattr(kh, "_fetch_ltp", lambda syms: {s: 101.5 for s in syms})
    monkeypatch.setattr(kh, "_now_iso", lambda: "2026-04-29T15:25:00+05:30")
    assert kh.cmd_close() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "CLOSED"
    assert r["exit_reason"] == "TIME_STOP"
    assert float(r["exit_px"]) == pytest.approx(101.5, abs=1e-3)
    # LONG entry 100.0 -> exit 101.5 = +1.5%
    assert float(r["pnl_pct"]) == pytest.approx(1.5, abs=1e-3)


def test_close_pnl_sign_for_short(stub_env, monkeypatch):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.3, p_short=0.7, signal_short=True)])
    _write_manifest(stub_env, [("RELIANCE", "short")])
    assert kh.cmd_open() == 0

    # SHORT @ 100, exit @ 98 -> +2% (favourable)
    monkeypatch.setattr(kh, "_fetch_ltp", lambda syms: {s: 98.0 for s in syms})
    assert kh.cmd_close() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert float(rows[0]["pnl_pct"]) == pytest.approx(2.0, abs=1e-3)


def test_close_idempotent_on_rerun(stub_env, monkeypatch):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    monkeypatch.setattr(kh, "_fetch_ltp", lambda syms: {s: 101.5 for s in syms})
    assert kh.cmd_close() == 0
    assert kh.cmd_close() == 0  # second close: no OPEN rows -> noop
    rows = _read_csv(stub_env["rec_path"])
    assert len(rows) == 1
    assert rows[0]["status"] == "CLOSED"


def test_close_does_nothing_when_no_open_rows(stub_env):
    assert kh.cmd_close() == 0


# ---------------------------------------------------------------------------
# 6. ATR stop is recorded
# ---------------------------------------------------------------------------

def test_open_records_atr_and_stop_price(stub_env):
    _write_predictions(stub_env, [_pred("RELIANCE", p_long=0.7, p_short=0.3, signal_long=True)])
    _write_manifest(stub_env, [("RELIANCE", "long")])
    assert kh.cmd_open() == 0
    rows = _read_csv(stub_env["rec_path"])
    assert float(rows[0]["atr_14"]) == pytest.approx(1.0)
    assert float(rows[0]["stop_px"]) == pytest.approx(98.0)
