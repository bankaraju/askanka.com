"""GET /api/sidebar-status — per-tab live counts + freshness.

One file, one endpoint. Reads existing artifact files only, returns a small
payload the sidebar can use to render counts/badges/dots without hitting 11
separate endpoints.

Freshness buckets per tab use file mtime vs an expected cadence ceiling
(in seconds): live = mtime within cadence, fresh = within 3x cadence,
stale = older. If the file is missing entirely, status is "missing".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

_HERE = Path(__file__).resolve().parent.parent
_DATA_DIR = _HERE.parent.parent / "data"           # askanka.com/data
_PIPELINE_DATA_DIR = _HERE.parent / "data"          # pipeline/data


@dataclass(frozen=True)
class TabSpec:
    tab: str
    file: Path
    cadence_s: int
    counter: str  # name of counter function below


def _count_open_signals(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("positions", "open", "signals", "items"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    return 0


def _count_correlation_breaks(payload: Any) -> int:
    if isinstance(payload, dict):
        breaks = payload.get("breaks") or payload.get("events") or []
        if isinstance(breaks, list):
            return len(breaks)
    if isinstance(payload, list):
        return len(payload)
    return 0


def _count_pattern_signals(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("top_10", "top10", "ranked", "patterns", "signals"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    if isinstance(payload, list):
        return len(payload)
    return 0


def _count_news(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("verdicts", "events", "items"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    return 0


def _count_track_record_closed(payload: Any) -> int:
    if isinstance(payload, dict):
        # Modern shape: { engines: [...], totals: {...}, closed: [...] }
        for key in ("closed", "trades", "history"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
        totals = payload.get("totals") or {}
        if isinstance(totals, dict):
            n = totals.get("n") or totals.get("n_closed")
            if isinstance(n, int):
                return n
    if isinstance(payload, list):
        return len(payload)
    return 0


def _count_articles(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("articles", "items"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
    if isinstance(payload, list):
        return len(payload)
    return 0


def _count_trust_scores(payload: Any) -> int:
    if isinstance(payload, dict):
        # trust_scores.json carries an explicit total + the list itself.
        total = payload.get("total_scored")
        if isinstance(total, int):
            return total
        for key in ("stocks", "scores", "tickers"):
            v = payload.get(key)
            if isinstance(v, list):
                return len(v)
            if isinstance(v, dict):
                return len(v)
    return 0


def _count_options_oi(payload: Any) -> int:
    if isinstance(payload, dict):
        return len(payload.get("anomalies") or payload.get("items") or [])
    if isinstance(payload, list):
        return len(payload)
    return 0


def _count_risk(payload: Any) -> int:
    """gap_risk.json is a single-record gap forecast, not a list. Surface
    the absolute predicted gap (basis points) so the sidebar shows magnitude
    rather than a meaningless "1". Severity drives badge accent via status."""
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("flags")
        if isinstance(items, list):
            return len(items)
        gaps = payload.get("gaps")
        if isinstance(gaps, dict):
            return len(gaps)
        pct = payload.get("predicted_gap_pct")
        if isinstance(pct, (int, float)):
            return int(round(abs(pct) * 100))  # bps
    if isinstance(payload, list):
        return len(payload)
    return 0


_COUNTERS = {
    "open_signals": _count_open_signals,
    "correlation_breaks": _count_correlation_breaks,
    "pattern_signals": _count_pattern_signals,
    "news": _count_news,
    "track_record_closed": _count_track_record_closed,
    "articles": _count_articles,
    "trust_scores": _count_trust_scores,
    "options_oi": _count_options_oi,
    "risk": _count_risk,
}


# Cadence ceilings reflect when the artifact SHOULD update during market hours.
# Outside market hours, file ages naturally; UI degrades from live → fresh → stale.
_TABS: list[TabSpec] = [
    # Dashboard: rolls up live_status which morning_scan + intraday refresh.
    TabSpec("dashboard",     _DATA_DIR / "live_status.json",                            900,  "open_signals"),
    # Live monitor: open_signals.json under signals/ — touched every intraday cycle (15 min).
    TabSpec("live-monitor",  _PIPELINE_DATA_DIR / "signals" / "open_signals.json",      900,  "open_signals"),
    # Regime: today_regime.json — fixed at 09:25, but file mtime updated daily.
    TabSpec("regime",        _PIPELINE_DATA_DIR / "today_regime.json",                  86400, "open_signals"),
    # Scanner: pattern_signals_today.json — daily 16:30 scan; cadence 1 day.
    TabSpec("scanner",       _PIPELINE_DATA_DIR / "pattern_signals_today.json",         86400, "pattern_signals"),
    # Trust: trust_scores.json — refreshed quarterly+; counts the universe scored.
    TabSpec("trust",         _DATA_DIR / "trust_scores.json",                           7 * 86400, "trust_scores"),
    # News: news_verdicts.json — touched 16:20 EOD + intraday news scans.
    TabSpec("news",          _PIPELINE_DATA_DIR / "news_verdicts.json",                 3600, "news"),
    # Options: oi_anomalies.json — touched every intraday cycle.
    TabSpec("options",       _PIPELINE_DATA_DIR / "oi_anomalies.json",                  900,  "options_oi"),
    # Risk: gap_risk.json — touched 08:30 pre-market; daily cadence.
    TabSpec("risk",          _DATA_DIR / "gap_risk.json",                               86400, "risk"),
    # Research: articles_index.json — daily article generation 04:45.
    TabSpec("research",      _DATA_DIR / "articles_index.json",                         86400, "articles"),
    # Track record: track_record.json — written at 16:15 EOD.
    TabSpec("track-record",  _DATA_DIR / "track_record.json",                           86400, "track_record_closed"),
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _bucket(age_s: float, cadence_s: int) -> str:
    if age_s < 0:
        return "live"
    if age_s <= cadence_s:
        return "live"
    if age_s <= 3 * cadence_s:
        return "fresh"
    return "stale"


def _build_tab_status(spec: TabSpec, now: datetime) -> dict:
    if not spec.file.exists():
        return {
            "tab": spec.tab,
            "count": None,
            "status": "missing",
            "age_s": None,
            "cadence_s": spec.cadence_s,
        }
    try:
        mtime = datetime.fromtimestamp(spec.file.stat().st_mtime, tz=IST)
    except OSError:
        mtime = None
    age_s = (now - mtime).total_seconds() if mtime else None
    payload = _read_json(spec.file)
    counter = _COUNTERS[spec.counter]
    count = counter(payload) if payload is not None else None
    status = _bucket(age_s, spec.cadence_s) if age_s is not None else "missing"
    return {
        "tab": spec.tab,
        "count": count,
        "status": status,
        "age_s": int(age_s) if age_s is not None else None,
        "cadence_s": spec.cadence_s,
    }


@router.get("/sidebar-status")
def sidebar_status():
    now = datetime.now(IST)
    tabs = [_build_tab_status(spec, now) for spec in _TABS]
    return {
        "timestamp": now.isoformat(),
        "tabs": tabs,
    }
