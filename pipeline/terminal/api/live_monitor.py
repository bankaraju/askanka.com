"""GET /api/live_monitor — open paper positions with stops + provenance.

Reads:
  - pipeline/data/research/phase_c/live_paper_ledger.json (Phase C shadow)
  - pipeline/data/research/h_2026_04_26_001/recommendations.csv (H-001/H-002 paper)
  - pipeline/data/research/phase_c/atr_stops.json (per-ticker ATR stops)
  - live_ltp endpoint (current prices)
  - pipeline/config/expected_engine_versions.json (config for badge)
  - <output>.provenance.json sidecars (running-system truth)

Returns one row per OPEN position (across all paper engines) + a top-strip
provenance badge state. Each row carries an `engine` field so the UI can
distinguish Phase C shadow rows from H-001/H-002 paper rows.

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
from pipeline.research.vwap_filter import normalize_legacy_tag, NA as _FILTER_NA


def _normalize_filter_tag(raw: Any) -> str:
    """Map legacy KEEP/DROP/WATCH on-disk values to EARLY/LATE/N/A.

    Default for an absent or empty value is N/A (data was unavailable at
    entry — not the same as "skipped"). New writes already emit the
    EARLY/LATE/N/A vocabulary; this normalize handles older rows so
    historical and live data display in one consistent vocabulary.
    """
    if not raw:
        return _FILTER_NA
    return normalize_legacy_tag(raw) or raw

router = APIRouter()


# In-process LTP cache. The frontend polls /api/live_monitor every 10s, and
# this endpoint also gets hit ad-hoc from other pages — without a TTL cache,
# successive calls inside one poll window each fired a fresh Kite bulk
# round-trip. 3s TTL means at most one fetch per 3s regardless of caller
# count, and successive 10s polls always fall outside the window so the
# user always sees a current quote.
_LTP_CACHE: dict[str, Any] = {"key": None, "value": {}, "ts": 0.0}
_LTP_CACHE_TTL_S = 3.0


def _cached_fetch_ltps(tickers: list[str]) -> dict[str, float]:
    """fetch_ltps with a 3s in-process TTL cache keyed on ticker set."""
    import time

    if not tickers:
        return {}
    key = tuple(sorted(tickers))
    now = time.time()
    if (
        _LTP_CACHE["key"] == key
        and (now - _LTP_CACHE["ts"]) < _LTP_CACHE_TTL_S
    ):
        return _LTP_CACHE["value"]
    try:
        from pipeline.terminal.api.live import fetch_ltps
        value = fetch_ltps(list(key)) or {}
    except Exception:
        value = {}
    _LTP_CACHE["key"] = key
    _LTP_CACHE["value"] = value
    _LTP_CACHE["ts"] = now
    return value


def _build_sector_lookup() -> dict[str, dict]:
    """Build symbol -> {sector, display_name} once at module load.

    Falls back to an empty dict on any failure (e.g. opus/artifacts not yet
    populated on a fresh clone), so the API stays up — the Sector column
    just shows "—" until the next overnight refresh fills the artifacts.
    """
    try:
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
        return SectorMapper().map_all()
    except Exception:
        return {}


_SECTOR_LOOKUP = _build_sector_lookup()


def _sector_for(symbol: str | None) -> tuple[str | None, str | None]:
    """Return (sector_key, display_name) or (None, None) if unknown."""
    if not symbol:
        return None, None
    info = _SECTOR_LOOKUP.get(symbol.upper())
    if not info:
        return None, None
    return info.get("sector"), info.get("display_name")

_HERE = Path(__file__).resolve().parent.parent
_REPO_ROOT = _HERE.parent.parent
_LEDGER_PATH = _REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "live_paper_ledger.json"
_H001_PATH = _REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_26_001" / "recommendations.csv"
_ATR_PATH = _REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "atr_stops.json"
_REGIME_PATH = _REPO_ROOT / "pipeline" / "data" / "today_regime.json"
_BREAKS_PATH = _REPO_ROOT / "pipeline" / "data" / "correlation_breaks.json"
_BREAKS_HIST_PATH = _REPO_ROOT / "pipeline" / "data" / "correlation_break_history.json"
_EXPECTED_VERSIONS_PATH = _REPO_ROOT / "pipeline" / "config" / "expected_engine_versions.json"

IST = timezone(timedelta(hours=5, minutes=30))
TIME_STOP_HHMM = (14, 30)

# Round-trip transaction cost haircut applied to every paper-trade P&L.
# 10 bps = 0.10% — covers brokerage (₹40 RT discount-broker) + STT (sell-side
# 0.0125% on F&O futures) + exchange fee (~0.00188% × 2) + SEBI (0.0001% × 2)
# + stamp duty (0.002% buy-side) + 18% GST on (brokerage+exchange+SEBI), at
# representative ₹6L notional per leg. Conservative (true intraday F&O RT is
# ~5-7 bps; equity intraday MIS RT is ~10-12 bps depending on ticket size).
# Adjust here to model a different broker/instrument.
_ROUND_TRIP_COST_PCT = 0.10


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


def _net_of_costs(gross_pct: float | None) -> float | None:
    """Subtract _ROUND_TRIP_COST_PCT from gross. None passes through."""
    if gross_pct is None:
        return None
    return round(gross_pct - _ROUND_TRIP_COST_PCT, 3)


def _enrich_row(row: dict, ltps: dict[str, float], atr_map: dict[str, dict],
                breaks_map: dict[str, dict]) -> dict:
    sym = row.get("symbol") or row.get("ticker")
    side = row.get("side", "LONG")
    entry = float(row.get("entry_px") or row.get("entry_price") or 0.0)
    ltp = ltps.get(sym)
    # CLOSED rows: fall back to exit_px so the LTP cell is populated post-close
    # (live LTP fetch is intentionally skipped for closed tickers).
    if ltp is None and row.get("status") == "CLOSED":
        try:
            ex = row.get("exit_px") or row.get("exit_price")
            ltp = float(ex) if ex not in (None, "") else None
        except (TypeError, ValueError):
            ltp = None
    atr_info = atr_map.get(sym, {})
    atr_stop = atr_info.get("stop_price") if isinstance(atr_info, dict) else None
    trail_stop = row.get("trail_stop_px")
    exit_reason = row.get("exit_reason") if row.get("status") == "CLOSED" else None
    status = _classify_status(side, ltp, entry, atr_stop, trail_stop, exit_reason)
    brk = breaks_map.get((sym or "").upper(), {})
    gross = _pnl_pct(side, entry, ltp)
    sector_key, sector_display = _sector_for(sym)
    return {
        "engine": "PhaseC",
        "ticker": sym,
        "sector": sector_key,
        "sector_display": sector_display,
        "side": side,
        "entry_time": row.get("opened_at") or row.get("signal_time"),
        "entry": entry,
        "ltp": ltp,
        "pnl_pct": gross,
        "pnl_net_pct": _net_of_costs(gross),
        "atr_stop": atr_stop,
        "trail_stop": trail_stop,
        "exit_reason": exit_reason,
        "status": status,
        "z_score": row.get("z_score"),
        "classification": row.get("classification"),
        "geometry": brk.get("event_geometry"),
        # PCR fields removed 2026-04-27: per-stock PCR is illiquid and not
        # used as a gate anywhere in the intraday pipeline. The geometric
        # Class column already captures the actionable read.
        "regime": row.get("regime"),
        "tag": row.get("tag"),
    }


def _load_breaks_by_ticker(today: str | None = None) -> dict[str, dict]:
    """Index breaks by symbol, preferring earliest entry-time geometry.

    Three-tier lookup, falling through if a ticker is missing:
      1. correlation_break_history.json — earliest row per (ticker, today).
         This is the entry-time geometry, captured at the first scan that
         flagged the ticker. Stable across the day.
      2. correlation_breaks.json — latest 15-min scan. Reflects current state.
         Only used as a fallback when the archive doesn't have the ticker.
      3. Empty — ticker not seen anywhere. UI shows dash.

    Tier 1 is preferred because the live breaks file is overwritten every
    15 min, drifting the displayed geometry away from what was true at
    09:30 entry. The archive freezes the entry-time read.
    """
    if today is None:
        today = datetime.now(IST).strftime("%Y-%m-%d")
    out: dict[str, dict] = {}

    # Tier 1: archive — earliest scan today for each ticker
    hist_doc = _read_json(_BREAKS_HIST_PATH, default=[])
    today_rows = []
    if isinstance(hist_doc, list):
        today_rows = [r for r in hist_doc if r.get("date") == today]
    elif isinstance(hist_doc, dict):
        today_rows = hist_doc.get(today, []) or []
    for r in today_rows:
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        existing = out.get(sym)
        if existing is None or r.get("time", "zz") < existing.get("time", "zz"):
            out[sym] = r

    # Tier 2: current scan — fill any tickers archive didn't capture
    cur_doc = _read_json(_BREAKS_PATH, default={})
    for b in cur_doc.get("breaks", []) or []:
        sym = (b.get("symbol") or "").upper()
        if sym and sym not in out:
            out[sym] = b
    return out


def _read_h001_today_rows(today: str) -> list[dict]:
    """Read today's H-001/H-002 paper rows from recommendations.csv.

    Returns a list of dicts in the live-monitor row shape. The H-001 CSV
    schema differs from Phase C shadow JSON, so we transform here. Marks
    each row with `engine="H-001"` and exposes the H-002 cohort flag via
    `regime_gate_pass` so the frontend can label rows as in-cohort or out.
    """
    import csv
    if not _H001_PATH.is_file():
        return []
    out: list[dict] = []
    try:
        with _H001_PATH.open("r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("date") != today:
                    continue
                out.append(r)
    except (OSError, csv.Error):
        return []
    return out


def _enrich_h001_row(row: dict, ltps: dict[str, float],
                     breaks_map: dict[str, dict]) -> dict:
    """Transform an H-001 CSV row into the live-monitor row shape."""
    sym = row.get("ticker", "")
    side = row.get("side", "LONG")
    try:
        entry = float(row.get("entry_px") or 0.0)
    except (TypeError, ValueError):
        entry = 0.0
    # CLOSED rows: live-LTP fetch is intentionally skipped (no Kite round-trip
    # for cosmetic display), but the CSV's exit_px is the closing mark — show
    # it as the "LTP" cell so the column isn't blank for closed trades.
    ltp = ltps.get(sym)
    if ltp is None and row.get("status") == "CLOSED":
        try:
            ex = row.get("exit_px")
            ltp = float(ex) if ex not in (None, "") else None
        except (TypeError, ValueError):
            ltp = None
    try:
        atr_stop = float(row.get("stop_px")) if row.get("stop_px") else None
    except (TypeError, ValueError):
        atr_stop = None
    try:
        trail_stop = float(row.get("trail_arm_px")) if row.get("trail_arm_px") else None
    except (TypeError, ValueError):
        trail_stop = None
    csv_status = row.get("status", "OPEN")
    exit_reason = row.get("exit_reason") if csv_status == "CLOSED" else None
    if csv_status == "CLOSED":
        status = "STOPPED" if exit_reason and exit_reason != "TIME_STOP" else "TIME_CLOSED"
    else:
        status = _classify_status(side, ltp, entry, atr_stop, trail_stop, None)
    pnl_pct: float | None
    if csv_status == "CLOSED" and row.get("pnl_pct"):
        try:
            pnl_pct = round(float(row["pnl_pct"]), 3)
        except (TypeError, ValueError):
            pnl_pct = _pnl_pct(side, entry, ltp)
    else:
        pnl_pct = _pnl_pct(side, entry, ltp)
    brk = breaks_map.get((sym or "").upper(), {})
    # H-001 v1 doesn't enforce trail stops (TODO(v2) in h_2026_04_26_001_paper.py).
    # For a hard-14:30-close day-trade, trail is structurally unnecessary anyway.
    # Suppress trail in the UI surface; ATR stop remains as the meaningful
    # historical-volatility cut-loss reference.
    status = _classify_status(side, ltp, entry, atr_stop, None, None) \
        if csv_status != "CLOSED" else status
    sector_key, sector_display = _sector_for(sym)
    return {
        "engine": "H-001",
        "ticker": sym,
        "sector": sector_key,
        "sector_display": sector_display,
        "side": side,
        "entry_time": row.get("entry_time"),
        "entry": entry,
        "ltp": ltp,
        "pnl_pct": pnl_pct,
        "pnl_net_pct": _net_of_costs(pnl_pct),
        "atr_stop": atr_stop,
        "trail_stop": None,
        "exit_reason": exit_reason,
        "status": status,
        "z_score": None,
        "classification": row.get("classification"),
        "geometry": brk.get("event_geometry"),
        # PCR fields removed 2026-04-27 (per-stock PCR illiquid, not a gate).
        "regime": row.get("regime"),
        "regime_gate_pass": row.get("regime_gate_pass") == "True",
        "sigma_bucket": row.get("sigma_bucket"),
        "vwap_dev_signed_pct": row.get("vwap_dev_signed_pct") or None,
        # Normalize old KEEP/DROP/WATCH to new EARLY/LATE/NA so historical
        # rows display consistently with newly-written rows. Default for an
        # absent value is N/A (data was unavailable at entry, not skipped).
        "filter_tag": _normalize_filter_tag(row.get("filter_tag")),
        "tag": "H-001" + ("/H-002" if row.get("regime_gate_pass") == "True" else ""),
    }


def _aggregate_pnl(rows: list[dict]) -> dict:
    """Equal-weighted average P&L across all trades with a usable mark.

    Average (not sum) is the right portfolio number: if you sized equally
    across N positions, the average per-trade % == your portfolio % return.
    Sum-of-percents is meaningless — it scales with N and isn't a return.
    """
    closed_rows = [r for r in rows if r["status"] in {"STOPPED", "TIME_CLOSED"}]
    open_rows = [r for r in rows if r["status"] in {"ACTIVE", "TRAIL_ARMED", "AT_RISK"}]
    all_marked = [r for r in (closed_rows + open_rows) if r.get("pnl_pct") is not None]
    gross_vals = [r["pnl_pct"] for r in all_marked]
    net_vals = [r["pnl_net_pct"] for r in all_marked if r.get("pnl_net_pct") is not None]

    def _mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    return {
        "n_open": len(open_rows),
        "n_closed": len(closed_rows),
        "n_no_ltp": sum(1 for r in rows if r["status"] == "NO_LTP"),
        "n_with_pnl": len(all_marked),
        "mean_pnl_pct_gross": _mean(gross_vals),
        "mean_pnl_pct_net": _mean(net_vals),
        "round_trip_cost_pct": _ROUND_TRIP_COST_PCT,
        # Kept for back-compat with anything still reading the sums:
        "realized_pnl_pp_sum": round(sum(r["pnl_pct"] for r in closed_rows if r.get("pnl_pct") is not None), 3),
        "open_marked_pnl_pp_sum": round(sum(r["pnl_pct"] for r in open_rows if r.get("pnl_pct") is not None), 3),
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

    # Union Phase C and H-001 ticker sets, but only for OPEN rows. Closed
    # rows already have realized P&L — fetching their LTP burns the Kite
    # round-trip for cosmetic display value. After 14:30 IST every paper
    # engine has CLOSED everything, so on the post-close polling burst the
    # endpoint returns instantly with no network IO at all.
    h001_rows_raw = _read_h001_today_rows(today)

    def _is_open_phase_c(r: dict) -> bool:
        # Phase C ledger uses status field; rows missing exit_at are still open.
        return (r.get("status") or "OPEN") == "OPEN" and not r.get("exit_at")

    phase_c_open_tickers = {
        (r.get("symbol") or r.get("ticker", "")).upper()
        for r in today_rows
        if (r.get("symbol") or r.get("ticker")) and _is_open_phase_c(r)
    }
    h001_open_tickers = {
        (r.get("ticker") or "").upper()
        for r in h001_rows_raw
        if r.get("ticker") and r.get("status") == "OPEN"
    }
    all_open_tickers = sorted(phase_c_open_tickers | h001_open_tickers)

    ltps = _cached_fetch_ltps(all_open_tickers)

    atr_map = _read_json(_ATR_PATH, default={})
    breaks_map = _load_breaks_by_ticker(today)

    rows = [_enrich_row(r, ltps, atr_map, breaks_map) for r in today_rows]
    if h001_rows_raw:
        rows.extend(_enrich_h001_row(r, ltps, breaks_map) for r in h001_rows_raw)

    rows.sort(key=lambda r: r.get("entry_time") or "")

    expected = _load_expected_versions()
    badges = {
        "live_paper_ledger": _badge_for(
            "pipeline/data/research/phase_c/live_paper_ledger.json", expected
        ),
        "regime": _badge_for("pipeline/data/today_regime.json", expected),
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
