"""News provenance writer — Task #23 phase 1.

Spec: docs/superpowers/specs/2026-04-30-news-provenance-protocol-design.md

Writes an immutable, atomic JSON file per trade-id per date capturing the 8
mandatory provenance fields. Designed to be called from run_signals at the
moment a news-triggered trade row is opened, so the headline that fired the
trigger is forensically tied to the trade.

This module does NOT modify any existing call sites. It exposes
`record_event_provenance()` for the integrating commit to call. The
integration is intentionally split into a separate commit because the
existing run_signals._run_once_inner path is mid-flight in live paper
trading and any modification deserves its own dedicated review.

Usage from caller:

    from pipeline.news_provenance import record_event_provenance

    path = record_event_provenance(
        trade_id="basket3_20260501_093125",
        headline_text="Iran fires drones at oil tanker in Strait of Hormuz",
        url="https://reuters.com/...",
        source="Reuters",
        fetched_at=datetime.now(IST),
        published_at=datetime(2026, 5, 1, 6, 14, tzinfo=IST),
        classifier_score=0.85,
        matched_trigger_keyword="hormuz",
    )
    # trade_row["news_provenance_path"] = str(path.relative_to(REPO_ROOT))
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.news_provenance")

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "news_provenance"
IST = timezone(timedelta(hours=5, minutes=30))
STALE_HOURS = 24


@dataclasses.dataclass(frozen=True)
class NewsProvenance:
    """Immutable record of a news event that fired a trade trigger.

    The 8 mandatory fields per spec section 2:
      url, source, fetched_at, published_at, classifier_score,
      matched_trigger_keyword, headline_text_sha256, verified_today.
    Plus operational fields: trade_id, headline_title (truncated), schema_version.
    """

    trade_id: str
    url: str
    source: str
    fetched_at_iso: str
    published_at_iso: str
    classifier_score: float
    matched_trigger_keyword: str
    headline_text_sha256: str
    verified_today: bool
    headline_title_first_120: str
    schema_version: str = "1.0_2026-04-30"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _hash_headline(title: str, body_first_500: str = "") -> str:
    """sha256 of headline_title + first 500 chars of body, per spec.

    Body is optional because much of our news history doesn't store body text.
    For headline-only sources, hash is computed on the title alone (with
    empty body suffix), and downstream auditors can detect that case.
    """
    text = (title or "") + "\n" + (body_first_500 or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_verified_today(fetched_at: datetime, published_at: datetime) -> bool:
    """Per spec section 3: a headline is 'verified_today' if its
    published_at timestamp is within `STALE_HOURS` (24h) of fetched_at.

    Both inputs must be timezone-aware. Naive datetimes are rejected.
    """
    if fetched_at.tzinfo is None or published_at.tzinfo is None:
        raise ValueError("fetched_at and published_at must be timezone-aware")
    delta = abs(fetched_at - published_at)
    return delta <= timedelta(hours=STALE_HOURS)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically: tempfile + os.replace. Never partial writes.

    Refuses to overwrite an existing provenance file (immutability per spec
    section 2: 'persisted at the moment of trade open, immutable').
    """
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing provenance record: {path}. "
            "Provenance records are immutable by design."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def record_event_provenance(
    *,
    trade_id: str,
    headline_text: str,
    url: str,
    source: str,
    fetched_at: datetime,
    published_at: datetime,
    classifier_score: float,
    matched_trigger_keyword: str,
    body_first_500: str = "",
    out_dir: Optional[Path] = None,
) -> Path:
    """Write the 8-field news provenance record for a trade.

    Returns the path to the written record. Caller should persist this path
    in the trade row's `news_provenance_path` field.

    Raises:
      FileExistsError if a record for (date, trade_id) already exists.
      ValueError if any input is missing or invalid.
    """
    if not trade_id:
        raise ValueError("trade_id is required")
    if not url:
        raise ValueError("url is required")
    if not matched_trigger_keyword:
        raise ValueError("matched_trigger_keyword is required")
    if not (0.0 <= classifier_score <= 1.0):
        raise ValueError(f"classifier_score must be in [0,1], got {classifier_score}")

    fetched_at_aware = fetched_at if fetched_at.tzinfo else fetched_at.replace(tzinfo=IST)
    published_at_aware = published_at if published_at.tzinfo else published_at.replace(tzinfo=IST)

    sha = _hash_headline(headline_text, body_first_500)
    verified = _is_verified_today(fetched_at_aware, published_at_aware)

    rec = NewsProvenance(
        trade_id=trade_id,
        url=url,
        source=source,
        fetched_at_iso=fetched_at_aware.isoformat(),
        published_at_iso=published_at_aware.isoformat(),
        classifier_score=float(classifier_score),
        matched_trigger_keyword=matched_trigger_keyword,
        headline_text_sha256=sha,
        verified_today=verified,
        headline_title_first_120=(headline_text or "")[:120],
    )

    base = out_dir if out_dir is not None else PROVENANCE_DIR
    date_str = fetched_at_aware.astimezone(IST).date().isoformat()
    target = base / date_str / f"{trade_id}.json"

    _atomic_write_json(target, rec.to_dict())
    log.info(
        "news_provenance recorded: trade=%s sha=%s verified=%s -> %s",
        trade_id, sha[:12], verified, target,
    )
    return target


def load_event_provenance(trade_id: str, date_str: str, base: Optional[Path] = None) -> dict:
    """Load a provenance record by (date, trade_id). Raises FileNotFoundError if absent."""
    base = base if base is not None else PROVENANCE_DIR
    path = base / date_str / f"{trade_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def headline_text_sha256(title: str, body_first_500: str = "") -> str:
    """Public helper for downstream auditors who need to recompute the hash."""
    return _hash_headline(title, body_first_500)
