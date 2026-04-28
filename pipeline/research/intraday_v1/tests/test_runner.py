"""Tests runner.py — CLI driver for V1 paper-trade lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.research.intraday_v1 import runner

IST = timezone(timedelta(hours=5, minutes=30))


def test_subcommands_registered():
    parser = runner.build_parser()
    subs = parser._subparsers._group_actions[0].choices.keys() if parser._subparsers else []
    expected = {"loader-refresh", "live-open", "shadow-eval", "live-close", "recalibrate", "verdict"}
    assert expected.issubset(set(subs)), f"missing subcommands: {expected - set(subs)}"


def test_live_open_writes_recommendations_row(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "_resolve_universe", lambda: {"stocks": ["RELIANCE"], "indices": []})
    monkeypatch.setattr(runner, "_compute_signals_at", lambda eval_t, universe: [
        {"instrument": "RELIANCE", "instrument_class": "stocks", "score": 1.5,
         "decision": "LONG", "entry_price": 2500.0, "atr14": 50.0,
         "weights_used": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4]},
    ])
    runner.live_open(eval_t=datetime(2026, 4, 29, 9, 30, tzinfo=IST))
    csv_path = tmp_path / "recommendations.csv"
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert len(df) == 1
    assert df.iloc[0]["instrument"] == "RELIANCE"
    assert df.iloc[0]["status"] == "OPEN"


def test_shadow_eval_writes_separate_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "_resolve_universe", lambda: {"stocks": ["RELIANCE"], "indices": []})
    monkeypatch.setattr(runner, "_compute_signals_at", lambda eval_t, universe: [
        {"instrument": "RELIANCE", "instrument_class": "stocks", "score": 1.4,
         "decision": "LONG", "entry_price": 2510.0, "atr14": 50.0,
         "weights_used": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4]},
    ])
    runner.shadow_eval(eval_t=datetime(2026, 4, 29, 11, 0, tzinfo=IST))
    shadow_path = tmp_path / "shadow_recs.csv"
    rec_path = tmp_path / "recommendations.csv"
    assert shadow_path.exists()
    assert not rec_path.exists()


def test_live_close_at_1430_updates_status(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    rec_path = tmp_path / "recommendations.csv"
    pd.DataFrame([{
        "instrument": "RELIANCE", "instrument_class": "stocks",
        "direction": "LONG", "entry_price": 2500.0, "atr14": 50.0,
        "score": 1.5, "status": "OPEN", "exit_price": "", "pnl_pct": "",
        "exit_reason": "", "open_date": "2026-04-29",
    }]).to_csv(rec_path, index=False)
    monkeypatch.setattr(runner, "_fetch_ltp", lambda sym: 2530.0)
    runner.live_close(eval_t=datetime(2026, 4, 29, 14, 30, tzinfo=IST))
    df = pd.read_csv(rec_path)
    assert df.iloc[0]["status"] == "CLOSED"
    assert df.iloc[0]["exit_reason"] in ("TIME_STOP", "ATR_STOP")
    assert float(df.iloc[0]["pnl_pct"]) > 0


def test_no_kite_session_writes_status_row(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "_resolve_universe", lambda: {"stocks": ["RELIANCE"], "indices": []})
    def raise_no_session(*args, **kwargs):
        raise runner.KiteSessionError("no session")
    monkeypatch.setattr(runner, "_compute_signals_at", raise_no_session)
    runner.live_open(eval_t=datetime(2026, 4, 29, 9, 30, tzinfo=IST))
    csv_path = tmp_path / "recommendations.csv"
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert (df["status"] == "NO_KITE_SESSION").any()


def test_live_open_idempotent_on_retry(tmp_path, monkeypatch):
    """Fix #8: scheduler retries (timeout, network blip) of the 09:30 task
    must NOT duplicate rows in recommendations.csv. The (open_date, instrument)
    pair is the dedup key; NO_KITE_SESSION is also deduped by (open_date, _GLOBAL_).
    """
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "_resolve_universe", lambda: {"stocks": ["RELIANCE", "INFY"], "indices": []})
    monkeypatch.setattr(runner, "_compute_signals_at", lambda eval_t, universe: [
        {"instrument": "RELIANCE", "instrument_class": "stocks", "score": 1.5,
         "decision": "LONG", "entry_price": 2500.0, "atr14": 50.0,
         "weights_used": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4]},
        {"instrument": "INFY", "instrument_class": "stocks", "score": -1.2,
         "decision": "SHORT", "entry_price": 1800.0, "atr14": 30.0,
         "weights_used": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4]},
    ])
    eval_t = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
    runner.live_open(eval_t=eval_t)
    runner.live_open(eval_t=eval_t)  # retry — must be a no-op
    csv_path = tmp_path / "recommendations.csv"
    df = pd.read_csv(csv_path)
    # Exactly one row per instrument, not two.
    assert len(df) == 2
    assert sorted(df["instrument"].tolist()) == ["INFY", "RELIANCE"]
    # Dedup key: (open_date, instrument)
    assert df.groupby(["open_date", "instrument"]).size().max() == 1


def test_live_open_idempotent_no_kite_session(tmp_path, monkeypatch):
    """Fix #8 corollary: NO_KITE_SESSION sentinel is also deduped on retry."""
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "_resolve_universe", lambda: {"stocks": ["RELIANCE"], "indices": []})
    def raise_no_session(*args, **kwargs):
        raise runner.KiteSessionError("no session")
    monkeypatch.setattr(runner, "_compute_signals_at", raise_no_session)
    eval_t = datetime(2026, 4, 29, 9, 30, tzinfo=IST)
    runner.live_open(eval_t=eval_t)
    runner.live_open(eval_t=eval_t)
    df = pd.read_csv(tmp_path / "recommendations.csv")
    # Only one NO_KITE_SESSION row for today's open_date.
    today = eval_t.date().isoformat()
    mask = (df["status"] == "NO_KITE_SESSION") & (df["open_date"].astype(str) == today)
    assert int(mask.sum()) == 1
