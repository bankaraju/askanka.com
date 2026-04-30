"""Tests for pipeline.news_provenance — Task #23 phase 1."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.news_provenance import (
    IST,
    headline_text_sha256,
    load_event_provenance,
    record_event_provenance,
)


def _now() -> datetime:
    return datetime.now(tz=IST)


def test_record_writes_atomic_file_with_8_fields(tmp_path: Path) -> None:
    now = _now()
    target = record_event_provenance(
        trade_id="t1",
        headline_text="Iran fires drones at oil tanker",
        url="https://example.com/x",
        source="Reuters",
        fetched_at=now,
        published_at=now - timedelta(hours=2),
        classifier_score=0.85,
        matched_trigger_keyword="hormuz",
        out_dir=tmp_path,
    )

    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    for field in (
        "trade_id",
        "url",
        "source",
        "fetched_at_iso",
        "published_at_iso",
        "classifier_score",
        "matched_trigger_keyword",
        "headline_text_sha256",
        "verified_today",
    ):
        assert field in data, f"missing required field {field}"

    assert data["trade_id"] == "t1"
    assert data["matched_trigger_keyword"] == "hormuz"
    assert data["verified_today"] is True
    assert len(data["headline_text_sha256"]) == 64  # sha256 hex


def test_stale_published_at_marks_verified_today_false(tmp_path: Path) -> None:
    now = _now()
    target = record_event_provenance(
        trade_id="t2",
        headline_text="Day-old headline",
        url="https://example.com/y",
        source="GoogleNews",
        fetched_at=now,
        published_at=now - timedelta(hours=48),
        classifier_score=0.6,
        matched_trigger_keyword="escalation",
        out_dir=tmp_path,
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["verified_today"] is False, "48h-old headline must NOT be verified_today"


def test_immutability_refuses_overwrite(tmp_path: Path) -> None:
    now = _now()
    record_event_provenance(
        trade_id="t3",
        headline_text="First write",
        url="https://example.com/z",
        source="Reuters",
        fetched_at=now,
        published_at=now,
        classifier_score=0.7,
        matched_trigger_keyword="oil_up",
        out_dir=tmp_path,
    )
    with pytest.raises(FileExistsError):
        record_event_provenance(
            trade_id="t3",
            headline_text="Second write — different content",
            url="https://example.com/z",
            source="Reuters",
            fetched_at=now,
            published_at=now,
            classifier_score=0.7,
            matched_trigger_keyword="oil_up",
            out_dir=tmp_path,
        )


def test_hash_is_reproducible() -> None:
    h1 = headline_text_sha256("Headline A", "body")
    h2 = headline_text_sha256("Headline A", "body")
    h3 = headline_text_sha256("Headline B", "body")
    assert h1 == h2
    assert h1 != h3


def test_invalid_classifier_score_rejected(tmp_path: Path) -> None:
    now = _now()
    with pytest.raises(ValueError):
        record_event_provenance(
            trade_id="t4",
            headline_text="Bad score",
            url="https://example.com/a",
            source="X",
            fetched_at=now,
            published_at=now,
            classifier_score=1.5,
            matched_trigger_keyword="x",
            out_dir=tmp_path,
        )


def test_naive_published_at_localized_to_ist(tmp_path: Path) -> None:
    fetched = datetime.now(tz=IST)
    naive_published = fetched.replace(tzinfo=None)  # strip tz
    target = record_event_provenance(
        trade_id="t5",
        headline_text="Naive ts",
        url="https://example.com/b",
        source="X",
        fetched_at=fetched,
        published_at=naive_published,
        classifier_score=0.5,
        matched_trigger_keyword="x",
        out_dir=tmp_path,
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "+05:30" in data["published_at_iso"], "naive ts must be localized to IST"


def test_load_round_trip(tmp_path: Path) -> None:
    now = _now()
    target = record_event_provenance(
        trade_id="t6",
        headline_text="Round-trip",
        url="https://example.com/c",
        source="Reuters",
        fetched_at=now,
        published_at=now,
        classifier_score=0.9,
        matched_trigger_keyword="hormuz",
        out_dir=tmp_path,
    )
    date_str = now.astimezone(IST).date().isoformat()
    rec = load_event_provenance("t6", date_str, base=tmp_path)
    assert rec["trade_id"] == "t6"
    assert rec["matched_trigger_keyword"] == "hormuz"
