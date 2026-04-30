"""Unit tests for pipeline/track_record_audit.py."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.track_record_audit import audit_track_record

IST = timezone(timedelta(hours=5, minutes=30))


def _closed(*, n: int, pnl: float = 1.0,
            close_iso: str = "2026-04-29T09:12:17") -> list[dict]:
    """Synthesize n closed-signal rows with the same final P&L."""
    return [
        {
            "signal_id": f"BRK-2026-04-{20 + i}-X",
            "open_timestamp": "2026-04-20T09:30:00+00:00",
            "close_timestamp": close_iso,
            "final_pnl": {"spread_pnl_pct": pnl},
        }
        for i in range(n)
    ]


def _track(*, total_closed: int, avg_pnl: float,
           updated: str = "2026-04-30T16:15:00+05:30") -> dict:
    return {
        "updated_at": updated,
        "total_closed": total_closed,
        "win_rate_pct": 50.0,
        "avg_pnl_pct": avg_pnl,
        "trades": [], "by_engine": [], "metrics": {}, "recent": [],
    }


def _write_pair(tmp_path: Path, closed_rows: list, track: dict
                ) -> tuple[Path, Path]:
    closed_p = tmp_path / "closed_signals.json"
    track_p = tmp_path / "track_record.json"
    closed_p.write_text(json.dumps(closed_rows), encoding="utf-8")
    track_p.write_text(json.dumps(track), encoding="utf-8")
    return closed_p, track_p


# --- Happy path ----------------------------------------------------------

def test_ok_when_count_and_avg_match(tmp_path):
    closed_p, track_p = _write_pair(
        tmp_path, _closed(n=3, pnl=2.0),
        _track(total_closed=3, avg_pnl=2.00),
    )
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is True
    assert r["kind"] == "ok"


def test_ok_with_avg_pnl_within_tolerance(tmp_path):
    # Expected avg = 2.0; actual = 2.04 → delta 0.04pp < 0.05 tolerance.
    closed_p, track_p = _write_pair(
        tmp_path, _closed(n=3, pnl=2.0),
        _track(total_closed=3, avg_pnl=2.04),
    )
    assert audit_track_record(closed_p, track_p)["ok"] is True


# --- Drift detection -----------------------------------------------------

def test_count_drift_detected(tmp_path):
    closed_p, track_p = _write_pair(
        tmp_path, _closed(n=5, pnl=1.0),
        _track(total_closed=4, avg_pnl=1.0),
    )
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is False
    assert r["kind"] == "count_drift"
    assert r["n_expected"] == 5
    assert r["n_actual"] == 4


def test_avg_pnl_drift_beyond_tolerance(tmp_path):
    # Expected avg = 2.0; actual = 1.5 → 0.5pp drift > 0.05 tolerance.
    closed_p, track_p = _write_pair(
        tmp_path, _closed(n=3, pnl=2.0),
        _track(total_closed=3, avg_pnl=1.5),
    )
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is False
    assert r["kind"] == "avg_pnl_drift"
    assert r["avg_expected"] == 2.0


def test_stale_vs_source_when_close_after_updated_at(tmp_path):
    # Close timestamp 2026-04-30T15:00 > updated_at 2026-04-30T14:00.
    closed_p, track_p = _write_pair(
        tmp_path,
        _closed(n=2, pnl=1.0, close_iso="2026-04-30T15:00:00"),
        _track(total_closed=2, avg_pnl=1.0,
               updated="2026-04-30T14:00:00+05:30"),
    )
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is False
    assert r["kind"] == "stale_vs_source"


# --- Edge cases ----------------------------------------------------------

def test_track_missing_is_fault(tmp_path):
    closed_p = tmp_path / "closed_signals.json"
    closed_p.write_text(json.dumps(_closed(n=2)), encoding="utf-8")
    track_p = tmp_path / "track_record.json"  # not created
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is False
    assert r["kind"] == "track_missing"


def test_no_source_when_closed_missing_is_not_fault(tmp_path):
    # Bootstrap state: closed_signals.json doesn't exist yet — not an error.
    closed_p = tmp_path / "closed_signals.json"
    track_p = tmp_path / "track_record.json"
    track_p.write_text(json.dumps(_track(total_closed=0, avg_pnl=0)),
                       encoding="utf-8")
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is True
    assert r["kind"] == "no_source"


def test_track_corrupt_is_fault(tmp_path):
    closed_p, track_p = _write_pair(
        tmp_path, _closed(n=1), _track(total_closed=1, avg_pnl=1.0),
    )
    track_p.write_text("not json", encoding="utf-8")
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is False
    assert r["kind"] == "track_unparseable"


def test_signal_with_missing_final_pnl_not_in_average(tmp_path):
    # Two rows: one with final_pnl=2.0, one with no final_pnl → average over
    # the one with valid pnl = 2.0.
    rows = _closed(n=1, pnl=2.0)
    rows.append({"signal_id": "BRK-X", "close_timestamp": "2026-04-29T10:00:00"})
    closed_p, track_p = _write_pair(
        tmp_path, rows,
        _track(total_closed=2, avg_pnl=2.0),
    )
    r = audit_track_record(closed_p, track_p)
    assert r["ok"] is True


def test_zero_signals_zero_avg(tmp_path):
    closed_p, track_p = _write_pair(
        tmp_path, [],
        _track(total_closed=0, avg_pnl=0),
    )
    assert audit_track_record(closed_p, track_p)["ok"] is True
