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


def _synthetic_panel(n_days: int = 30, n_inst: int = 10, seed: int = 0) -> pd.DataFrame:
    """Pick a fixed-shape panel for recalibrate tests."""
    import numpy as np
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(n_inst):
            f = rng.normal(0, 1, 6)
            label = float(np.dot(f, [0.5, -0.3, 0.2, 0.1, 0.0, 0.4])) + rng.normal(0, 0.5)
            rows.append({
                "date": f"2026-03-{1+d:02d}",
                "instrument": f"INST{i}",
                "f1": f[0], "f2": f[1], "f3": f[2],
                "f4": f[3], "f5": f[4], "f6": f[5],
                "next_return_pct": label,
            })
    return pd.DataFrame(rows)


def test_recalibrate_writes_weights_file_for_each_pool(tmp_path, monkeypatch):
    """End-to-end: synthetic in-sample panel -> recalibrate -> weights JSON
    + latest_<pool>.json on disk with valid weights and thresholds.
    """
    import json as _json
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "WEIGHTS_DIR", tmp_path / "weights")
    from pipeline.research.intraday_v1 import in_sample_panel as isp
    monkeypatch.setattr(isp, "assemble_for_pool", lambda pool: _synthetic_panel())
    runner.recalibrate(pool="stocks")
    weights_dir = tmp_path / "weights"
    latest = weights_dir / "latest_stocks.json"
    assert latest.exists()
    payload = _json.loads(latest.read_text(encoding="utf-8"))
    assert "weights" in payload
    assert len(payload["weights"]) == 6
    assert "long_threshold" in payload
    assert "short_threshold" in payload
    assert payload["long_threshold"] > payload["short_threshold"]
    assert payload["pool"] == "stocks"
    assert payload["seed"] == 42
    # The dated file is also present.
    dated_files = [p for p in weights_dir.iterdir() if p.name.endswith("_stocks.json") and p.name != "latest_stocks.json"]
    assert len(dated_files) == 1


def test_recalibrate_raises_on_empty_panel(tmp_path, monkeypatch):
    """Per feedback_no_hallucination_mandate.md: empty panel must fail loud."""
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "WEIGHTS_DIR", tmp_path / "weights")
    from pipeline.research.intraday_v1 import in_sample_panel as isp
    monkeypatch.setattr(isp, "assemble_for_pool", lambda pool: pd.DataFrame())
    with pytest.raises(RuntimeError, match="empty"):
        runner.recalibrate(pool="stocks")


def test_recalibrate_uses_smaller_rolling_window_when_insufficient_days(
    tmp_path, monkeypatch, caplog,
):
    """Kickoff scenario: 8-day in-sample panel triggers a window shrink.

    The fit must complete and emit a weights file whose
    ``rolling_window_days`` is < 10 (the spec default).
    """
    import json as _json
    import logging as _logging
    caplog.set_level(_logging.WARNING)

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    monkeypatch.setattr(runner, "WEIGHTS_DIR", tmp_path / "weights")
    from pipeline.research.intraday_v1 import in_sample_panel as isp
    monkeypatch.setattr(isp, "assemble_for_pool", lambda pool: _synthetic_panel(n_days=8))
    runner.recalibrate(pool="stocks")
    payload = _json.loads(
        (tmp_path / "weights" / "latest_stocks.json").read_text(encoding="utf-8")
    )
    assert payload["rolling_window_days"] < 10
    assert payload["rolling_window_days"] >= 3
    assert payload["n_in_sample_days"] == 8
    # Caller logged the warning.
    assert any("reducing ROLLING_WINDOW_DAYS" in r.message for r in caplog.records)


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


def test_runner_sector_map_matches_in_sample_panel():
    """The live engine and the in-sample panel must use the SAME sector mapping
    convention. Drift between the two was a kickoff blocker: runner used the
    no-space form ("NIFTYBANK") while the on-disk cache files use the Kite
    space-separated form ("NIFTY BANK.parquet"), so every stock would silently
    skip RS-vs-sector at 09:30 live-open. Single source of truth is
    ``in_sample_panel.SECTOR_INDEX_MAP_KITE``.
    """
    from pipeline.research.intraday_v1 import in_sample_panel as isp
    # The two maps must be the same object (DRY): runner imports from isp.
    # If a future refactor accidentally re-defines a local SECTOR_INDEX_MAP in
    # runner with stale values, this test fires.
    src = (Path(runner.__file__)).read_text(encoding="utf-8")
    assert "SECTOR_INDEX_MAP = in_sample_panel.SECTOR_INDEX_MAP_KITE" in src, (
        "runner._compute_signals_at must source SECTOR_INDEX_MAP from "
        "in_sample_panel.SECTOR_INDEX_MAP_KITE — drift here causes silent "
        "skip of every stock at 09:30 live-open."
    )
    # And the Kite map must use space-separated names (matches on-disk cache).
    sample_values = set(isp.SECTOR_INDEX_MAP_KITE.values())
    assert "NIFTY BANK" in sample_values, "expected Kite naming with spaces"
    assert "NIFTYBANK" not in sample_values, "no-space form would not match cache"


def test_runner_sector_fallback_matches_real_cache_filename():
    """The fallback sector ('NIFTY 50') must match an actual on-disk cache file
    (or be the documented production-time absent default). At kickoff the cache
    file is ``NIFTY 50.parquet``; the earlier bug used 'NIFTY' which mapped to
    no file. This test fixes the contract.
    """
    from pipeline.research.intraday_v1 import in_sample_panel as isp
    assert isp.DEFAULT_SECTOR_FALLBACK == "NIFTY 50", (
        f"DEFAULT_SECTOR_FALLBACK is {isp.DEFAULT_SECTOR_FALLBACK!r}; "
        f"the cache file is 'NIFTY 50.parquet' so the fallback must match."
    )
