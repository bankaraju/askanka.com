"""GET /api/live_monitor — open Phase C shadow positions with stops + provenance.

Reads:
  - pipeline/data/research/phase_c/live_paper_ledger.json (canonical, open rows)
  - pipeline/data/research/phase_c/atr_stops.json (per-ticker ATR stops)
  - live_ltp endpoint (current prices)
  - pipeline/config/expected_engine_versions.json (config for badge)
  - <output>.provenance.json sidecars (running-system truth)

Returns one row per OPEN position + a top-strip provenance badge state.

The badge is the user-visible answer to "did the cutover land?" — green if
the running version matches config, amber on missing/stale, red on mismatch.
Until producers opt in to writing provenance sidecars, badges are amber
"unknown", which is the correct failure mode.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from pipeline import provenance

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_REPO_ROOT = _HERE.parent.parent
_LEDGER_PATH = _REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "live_paper_ledger.json"
_ATR_PATH = _REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "atr_stops.json"
_REGIME_PATH = _REPO_ROOT / "data" / "today_regime.json"
_EXPECTED_VERSIONS_PATH = _REPO_ROOT / "pipeline" / "config" / "expected_engine_versions.json"

IST = timezone(timedelta(hours=5, minutes=30))
TIME_STOP_HHMM = (14, 30)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def _load_expected_versions() -> dict[str, dict]:
    cfg = _read_json(_EXPECTED_VERSIONS_PATH, default={"outputs": {}})
    return cfg.get("outputs", {})


def _badge_for(rel_output_path: str, expected_versions: dict) -> dict:
    """Compose the badge dict for an output by relative repo path."""
    abs_path = _REPO_ROOT / rel_output_path
    cfg = expected_versions.get(rel_output_path, {})
    expected = cfg.get("expected_engine_version")
    badge = provenance.assess(abs_path, expected_engine_version=expected)
    badge["output_path"] = rel_output_path
    badge["owner_task"] = cfg.get("owner_task")
    return badge


def _seconds_to_time_stop_now() -> int | None:
    """Seconds remaining until 14:30 IST today; None if already past."""
    now = datetime.now(IST)
    target = now.replace(hour=TIME_STOP_HHMM[0], minute=TIME_STOP_HHMM[1],
                          second=0, microsecond=0)
    if now >= target:
        return None
    return int((target - now).total_seconds())


def _classify_status(
    side: str, ltp: float | None, entry: float, atr_stop: float | None,
    trail_stop: float | None, exit_reason: str | None,
) -> str:
    """ACTIVE / TRAIL_ARMED / AT_RISK / STOPPED / TIME_CLOSED / NO_LTP."""
    if exit_reason:
        if exit_reason == "TIME_STOP":
            return "TIME_CLOSED"
        return "STOPPED"
    if ltp is None:
        return "NO_LTP"
    if trail_stop is not None:
        # AT_RISK if LTP within 30% of distance from entry to trail
        dist_full = abs(entry - trail_stop)
        dist_now = abs(ltp - trail_stop)
        if dist_full > 0 and dist_now / dist_full < 0.30:
            return "AT_RISK"
        return "TRAIL_ARMED"
    if atr_stop is not None:
        dist_full = abs(entry - atr_stop)
        dist_now = abs(ltp - atr_stop)
        if dist_full > 0 and dist_now / dist_full < 0.30:
            return "AT_RISK"
    return "ACTIVE"


def _pnl_pct(side: str, entry: float, ltp: float | None) -> float | None:
    if ltp is None or entry in (0, None):
        return None
    raw = (ltp - entry) / entry * 100.0
    return round(raw if side == "LONG" else -raw, 3)


def _enrich_row(row: dict, ltps: dict[str, float], atr_map: dict[str, dict]) -> dict:
    sym = row.get("symbol") or row.get("ticker")
    side = row.get("side", "LONG")
    entry = float(row.get("entry_px") or row.get("entry_price") or 0.0)
    ltp = ltps.get(sym)
    atr_info = atr_map.get(sym, {})
    atr_stop = atr_info.get("stop_price") if isinstance(atr_info, dict) else None
    trail_stop = row.get("trail_stop_px")
    exit_reason = row.get("exit_reason") if row.get("status") == "CLOSED" else None
    status = _classify_status(side, ltp, entry, atr_stop, trail_stop, exit_reason)
    return {
        "ticker": sym,
        "side": side,
        "entry_time": row.get("opened_at") or row.get("signal_time"),
        "entry": entry,
        "ltp": ltp,
        "pnl_pct": _pnl_pct(side, entry, ltp),
        "atr_stop": atr_stop,
        "trail_stop": trail_stop,
        "exit_reason": exit_reason,
        "status": status,
        "z_score": row.get("z_score"),
        "classification": row.get("classification"),
        "regime": row.get("regime"),
        "tag": row.get("tag"),
    }


def _aggregate_pnl(rows: list[dict]) -> dict:
    realized = [r["pnl_pct"] for r in rows if r["status"] in {"STOPPED", "TIME_CLOSED"} and r["pnl_pct"] is not None]
    open_marks = [r["pnl_pct"] for r in rows if r["status"] in {"ACTIVE", "TRAIL_ARMED", "AT_RISK"} and r["pnl_pct"] is not None]
    return {
        "n_open": sum(1 for r in rows if r["status"] in {"ACTIVE", "TRAIL_ARMED", "AT_RISK"}),
        "n_closed": sum(1 for r in rows if r["status"] in {"STOPPED", "TIME_CLOSED"}),
        "n_no_ltp": sum(1 for r in rows if r["status"] == "NO_LTP"),
        "realized_pnl_pp_sum": round(sum(realized), 3) if realized else 0.0,
        "open_marked_pnl_pp_sum": round(sum(open_marks), 3) if open_marks else 0.0,
    }


@router.get("/live_monitor")
def live_monitor():
    """Return open Phase C positions + provenance badges + aggregate P&L."""
    raw_ledger = _read_json(_LEDGER_PATH, default=[])
    if isinstance(raw_ledger, dict):
        raw_ledger = raw_ledger.get("entries", [])

    today = datetime.now(IST).strftime("%Y-%m-%d")
    today_rows = [
        r for r in raw_ledger
        if (r.get("date") or r.get("opened_at", "")[:10]) == today
    ]

    tickers = sorted({(r.get("symbol") or r.get("ticker", "")).upper()
                      for r in today_rows if (r.get("symbol") or r.get("ticker"))})
    ltps: dict[str, float] = {}
    if tickers:
        try:
            from pipeline.terminal.api.live import fetch_ltps
            ltps = fetch_ltps(tickers) or {}
        except Exception:
            ltps = {}

    atr_map = _read_json(_ATR_PATH, default={})

    rows = [_enrich_row(r, ltps, atr_map) for r in today_rows]
    rows.sort(key=lambda r: r.get("entry_time") or "")

    expected = _load_expected_versions()
    badges = {
        "live_paper_ledger": _badge_for(
            "pipeline/data/research/phase_c/live_paper_ledger.json", expected
        ),
        "regime": _badge_for("data/today_regime.json", expected),
        "correlation_breaks": _badge_for(
            "pipeline/data/correlation_breaks.json", expected
        ),
    }

    regime_doc = _read_json(_REGIME_PATH, default={})
    regime_label = (
        regime_doc.get("zone") or regime_doc.get("regime")
        or regime_doc.get("regime_zone") or "UNKNOWN"
    )

    return {
        "today": today,
        "regime": regime_label,
        "time_to_close_seconds": _seconds_to_time_stop_now(),
        "rows": rows,
        "aggregate": _aggregate_pnl(rows),
        "badges": badges,
        "n_total": len(rows),
    }
