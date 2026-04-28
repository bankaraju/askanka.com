"""Tests for ``pipeline.research.intraday_v1.pcr_producer``.

Covers the no-hallucination contract: real archive in, real OI out;
missing archive (in whole or per-symbol) means no file emitted.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict

import pytest

from pipeline.research.intraday_v1 import pcr_producer


def _write_archive(archive_dir: Path, d: date, payload: Dict) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{d.isoformat()}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _symbol_blob(*, near_put: int, near_call: int, next_put: int, next_call: int) -> Dict:
    """Minimal symbol blob mirroring the real ``oi_history_stocks`` schema."""
    return {
        "near": {"put_oi": near_put, "call_oi": near_call, "expiry": "2026-04-28"},
        "next": {"put_oi": next_put, "call_oi": next_call, "expiry": "2026-05-26"},
    }


def test_writes_files_only_when_both_archives_present(tmp_path: Path) -> None:
    archive_dir = tmp_path / "oi"
    out_dir = tmp_path / "out"
    today_d = date(2026, 4, 28)
    two_d_ago_d = date(2026, 4, 24)

    _write_archive(archive_dir, two_d_ago_d, {
        "RELIANCE": _symbol_blob(near_put=100, near_call=200, next_put=1000, next_call=2000),
        "INFY":     _symbol_blob(near_put=300, near_call=400, next_put=3000, next_call=4000),
    })
    _write_archive(archive_dir, date(2026, 4, 27), {
        "RELIANCE": _symbol_blob(near_put=110, near_call=210, next_put=1100, next_call=2100),
        "INFY":     _symbol_blob(near_put=310, near_call=410, next_put=3100, next_call=4100),
    })
    _write_archive(archive_dir, today_d, {
        "RELIANCE": _symbol_blob(near_put=120, near_call=220, next_put=1200, next_call=2200),
        "INFY":     _symbol_blob(near_put=320, near_call=420, next_put=3200, next_call=4200),
    })

    summary = pcr_producer.produce_pcr_snapshots(
        eval_date=today_d, output_dir=out_dir, archive_dir=archive_dir
    )

    assert summary["today_date"] == today_d.isoformat()
    assert summary["two_d_ago_date"] == two_d_ago_d.isoformat()
    assert summary["symbols_written"] == 2

    for sym in ("RELIANCE", "INFY"):
        assert (out_dir / f"{sym}_today.json").exists()
        assert (out_dir / f"{sym}_2d_ago.json").exists()


def test_skips_symbol_missing_from_either_archive(tmp_path: Path) -> None:
    archive_dir = tmp_path / "oi"
    out_dir = tmp_path / "out"
    today_d = date(2026, 4, 28)
    two_d_ago_d = date(2026, 4, 24)

    _write_archive(archive_dir, two_d_ago_d, {
        "RELIANCE": _symbol_blob(near_put=100, near_call=200, next_put=1000, next_call=2000),
        "TCS":      _symbol_blob(near_put=500, near_call=600, next_put=5000, next_call=6000),
    })
    _write_archive(archive_dir, date(2026, 4, 27), {
        "RELIANCE": _symbol_blob(near_put=110, near_call=210, next_put=1100, next_call=2100),
    })
    _write_archive(archive_dir, today_d, {
        "RELIANCE": _symbol_blob(near_put=120, near_call=220, next_put=1200, next_call=2200),
        "INFY":     _symbol_blob(near_put=320, near_call=420, next_put=3200, next_call=4200),
    })

    summary = pcr_producer.produce_pcr_snapshots(
        eval_date=today_d, output_dir=out_dir, archive_dir=archive_dir
    )

    assert summary["symbols_written"] == 1
    assert (out_dir / "RELIANCE_today.json").exists()
    assert (out_dir / "RELIANCE_2d_ago.json").exists()
    # INFY only in today; TCS only in 2-days-ago — neither should produce files
    assert not (out_dir / "INFY_today.json").exists()
    assert not (out_dir / "INFY_2d_ago.json").exists()
    assert not (out_dir / "TCS_today.json").exists()
    assert not (out_dir / "TCS_2d_ago.json").exists()

    skip_reasons = {(s.get("symbol"), s.get("reason")) for s in summary["skipped"]}
    assert ("INFY", "MISSING_FROM_2D_AGO") in skip_reasons
    assert ("TCS", "MISSING_FROM_TODAY") in skip_reasons


def test_skips_symbol_when_two_d_archive_missing_entirely(tmp_path: Path) -> None:
    archive_dir = tmp_path / "oi"
    out_dir = tmp_path / "out"
    today_d = date(2026, 4, 28)

    # Only a single archive day exists — cannot resolve "2 days ago" at all.
    _write_archive(archive_dir, today_d, {
        "RELIANCE": _symbol_blob(near_put=120, near_call=220, next_put=1200, next_call=2200),
    })

    summary = pcr_producer.produce_pcr_snapshots(
        eval_date=today_d, output_dir=out_dir, archive_dir=archive_dir
    )

    assert summary["symbols_written"] == 0
    assert summary["two_d_ago_date"] is None
    # Nothing should have been written.
    if out_dir.exists():
        assert list(out_dir.iterdir()) == []
    assert any(
        s.get("reason") == "INSUFFICIENT_ARCHIVES" for s in summary["skipped"]
    )


def test_resolves_two_d_ago_using_calendar_of_archive_files(tmp_path: Path) -> None:
    """4 archive files spread over 6 calendar days — '2 days ago' uses
    archive-file ordering, not calendar arithmetic."""
    archive_dir = tmp_path / "oi"
    out_dir = tmp_path / "out"

    # Archives on Mon/Tue/Thu/Fri (weekend skipped naturally; missing Wed = holiday)
    d_mon = date(2026, 4, 20)
    d_tue = date(2026, 4, 21)
    # Wed (2026-04-22) absent — simulated holiday
    d_thu = date(2026, 4, 23)
    d_fri = date(2026, 4, 24)

    blob_a = {"RELIANCE": _symbol_blob(near_put=1, near_call=1, next_put=10, next_call=10)}
    blob_b = {"RELIANCE": _symbol_blob(near_put=2, near_call=2, next_put=20, next_call=20)}
    blob_c = {"RELIANCE": _symbol_blob(near_put=3, near_call=3, next_put=30, next_call=30)}
    blob_d = {"RELIANCE": _symbol_blob(near_put=4, near_call=4, next_put=40, next_call=40)}

    _write_archive(archive_dir, d_mon, blob_a)
    _write_archive(archive_dir, d_tue, blob_b)
    _write_archive(archive_dir, d_thu, blob_c)
    _write_archive(archive_dir, d_fri, blob_d)

    summary = pcr_producer.produce_pcr_snapshots(
        eval_date=d_fri, output_dir=out_dir, archive_dir=archive_dir
    )

    # Today = Friday's archive; 2-files-back = Tuesday's archive (NOT Wednesday-by-calendar)
    assert summary["today_date"] == d_fri.isoformat()
    assert summary["two_d_ago_date"] == d_tue.isoformat()
    assert summary["symbols_written"] == 1

    today_payload = json.loads((out_dir / "RELIANCE_today.json").read_text())
    two_d_payload = json.loads((out_dir / "RELIANCE_2d_ago.json").read_text())
    # Friday's blob_d had next_put=40; Tuesday's blob_b had next_put=20.
    assert today_payload["put_oi_total_next_month"] == 40
    assert two_d_payload["put_oi_total_next_month"] == 20


def test_emits_only_next_month_oi_not_near_month(tmp_path: Path) -> None:
    archive_dir = tmp_path / "oi"
    out_dir = tmp_path / "out"
    today_d = date(2026, 4, 28)
    two_d_ago_d = date(2026, 4, 24)

    # Use deliberately distinct values so a near/next swap would be visible.
    _write_archive(archive_dir, two_d_ago_d, {
        "RELIANCE": _symbol_blob(
            near_put=99_999, near_call=88_888,
            next_put=1234, next_call=5678,
        ),
    })
    _write_archive(archive_dir, date(2026, 4, 25), {
        "RELIANCE": _symbol_blob(
            near_put=99_999, near_call=88_888,
            next_put=1235, next_call=5679,
        ),
    })
    _write_archive(archive_dir, today_d, {
        "RELIANCE": _symbol_blob(
            near_put=77_777, near_call=66_666,
            next_put=4321, next_call=8765,
        ),
    })

    pcr_producer.produce_pcr_snapshots(
        eval_date=today_d, output_dir=out_dir, archive_dir=archive_dir
    )

    today_payload = json.loads((out_dir / "RELIANCE_today.json").read_text())
    two_d_payload = json.loads((out_dir / "RELIANCE_2d_ago.json").read_text())

    # Must come from .next, NOT .near.
    assert today_payload == {"put_oi_total_next_month": 4321, "call_oi_total_next_month": 8765}
    assert two_d_payload == {"put_oi_total_next_month": 1234, "call_oi_total_next_month": 5678}
    # And explicitly: must NOT match .near values.
    assert today_payload["put_oi_total_next_month"] != 77_777
    assert two_d_payload["put_oi_total_next_month"] != 99_999
