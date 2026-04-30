"""Track-record content-audit.

The freshness watchdog catches "file is stale" by mtime; this catches the
class of bugs where ``data/track_record.json`` mtime is fresh but the content
no longer reflects the latest closes in ``pipeline/data/signals/closed_signals.json``.
That bug pattern hits when:
  - ``website_exporter.py`` runs but the export crashes before reaching the
    track-record write (older mtime preserved by os.replace fallback).
  - A closed signal lands in ``closed_signals.json`` after the last EOD
    track-record write and no intraday cycle has refreshed the export.
  - Schema drift in ``closed_signals.json`` (e.g., final_pnl key rename) causes
    silent zero-fills in the export.

The audit reads both files, recomputes what ``export_track_record`` would have
produced now, and reports a structured discrepancy when the two diverge.
Fast (<10ms on 60 closed trades) — safe to call once per watchdog cycle.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CLOSED_PATH = REPO / "pipeline" / "data" / "signals" / "closed_signals.json"
TRACK_PATH = REPO / "data" / "track_record.json"
IST = timezone(timedelta(hours=5, minutes=30))

# Sum of N rounded floats can drift from the rounded sum by up to N × half-ULP.
# 60 trades × round-to-2dp → max drift ~0.005pp; pad to 0.05 to absorb future
# growth and the round-to-2dp on track_record's avg_pnl_pct field.
_PNL_TOLERANCE = 0.05


def _final_pnl(sig: dict) -> float | None:
    """Extract final P&L (percent) from a closed-signal dict.

    Schema: ``sig["final_pnl"]["spread_pnl_pct"]`` is the canonical path used
    by ``website_exporter.export_track_record``. Return None when the field
    is missing — the caller decides whether a missing P&L is a soft-skip or
    a hard mismatch.
    """
    fp = sig.get("final_pnl")
    if not isinstance(fp, dict):
        return None
    v = fp.get("spread_pnl_pct")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def audit_track_record(
    closed_path: Path = CLOSED_PATH,
    track_path: Path = TRACK_PATH,
) -> dict[str, Any]:
    """Compare ``track_record.json`` against the live ``closed_signals.json``.

    Returns a dict with at minimum ``ok: bool``, ``kind: str``, ``detail: str``.
    On mismatch, additional fields surface the numeric drift for the alert.

    ``kind`` taxonomy:
      - ``ok``                — everything matches
      - ``no_source``         — closed_signals.json missing (early bootstrap;
                                not a fault)
      - ``track_missing``     — track_record.json missing (real fault)
      - ``track_unparseable`` — track_record.json is corrupt
      - ``count_drift``       — total_closed disagrees
      - ``avg_pnl_drift``     — avg_pnl_pct disagrees beyond tolerance
      - ``stale_vs_source``   — latest close in closed_signals.json is more
                                recent than track_record.updated_at
    """
    if not closed_path.exists():
        return {"ok": True, "kind": "no_source",
                "detail": f"{closed_path.name} missing — nothing to audit"}

    if not track_path.exists():
        return {"ok": False, "kind": "track_missing",
                "detail": f"{track_path} does not exist"}

    try:
        closed = json.loads(closed_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Corrupt source — surface but don't fault track_record.
        return {"ok": True, "kind": "no_source",
                "detail": f"{closed_path.name} unparseable: {exc}"}

    try:
        track = json.loads(track_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "kind": "track_unparseable",
                "detail": f"{track_path} unparseable: {exc}"}

    n_expected = len(closed)
    n_actual = int(track.get("total_closed", 0) or 0)

    if n_expected != n_actual:
        return {
            "ok": False, "kind": "count_drift",
            "detail": (
                f"closed_signals has {n_expected} closed signals; "
                f"track_record reports {n_actual}"
            ),
            "n_expected": n_expected, "n_actual": n_actual,
        }

    pnls = [p for p in (_final_pnl(s) for s in closed) if p is not None]
    avg_expected = (sum(pnls) / len(pnls)) if pnls else 0.0
    avg_actual = float(track.get("avg_pnl_pct", 0) or 0)

    if abs(avg_expected - avg_actual) > _PNL_TOLERANCE:
        return {
            "ok": False, "kind": "avg_pnl_drift",
            "detail": (
                f"avg_pnl divergence > {_PNL_TOLERANCE}pp: "
                f"expected {avg_expected:.3f}, actual {avg_actual:.3f}"
            ),
            "avg_expected": round(avg_expected, 3),
            "avg_actual": round(avg_actual, 3),
        }

    # Latest close timestamp in closed_signals vs track_record's updated_at.
    # Both are ISO strings; lexicographic comparison is correct iff timezone
    # offsets are aligned. closed_signals close_timestamp can be naive
    # (fallback to "" if missing); track_record updated_at carries the IST
    # offset. Strip the offset/+05:30 suffix on track_updated for comparison
    # consistency — we only care that an event happened AFTER the writer ran.
    close_times = [s.get("close_timestamp", "") for s in closed
                   if s.get("close_timestamp")]
    last_close = max(close_times) if close_times else ""
    track_updated = track.get("updated_at", "") or ""
    track_updated_naive = track_updated[:19]  # YYYY-MM-DDTHH:MM:SS
    if last_close and track_updated_naive and last_close[:19] > track_updated_naive:
        return {
            "ok": False, "kind": "stale_vs_source",
            "detail": (
                f"latest close {last_close[:19]} is after "
                f"track_record updated_at {track_updated_naive}"
            ),
            "last_close": last_close, "track_updated": track_updated,
        }

    return {"ok": True, "kind": "ok",
            "detail": f"{n_expected} closed, avg {avg_actual:.2f}%"}


if __name__ == "__main__":
    import sys
    result = audit_track_record()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
