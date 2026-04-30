"""SECRSI forward-shadow paper-trade driver (H-2026-04-27-003).

Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md

Three CLI subcommands run during the holdout window 2026-04-28 → 2026-07-31:

    python -m pipeline.research.h_2026_04_27_secrsi.forward_shadow capture-opens
        09:16 IST. Fetches Kite LTP for the full F&O universe (canonical
        fno_research_v3) and writes to
        ``pipeline/data/research/h_2026_04_27_secrsi/opens/<date>.json``.
        Idempotent (overwrites). Required input for ``basket-open``.

    python -m pipeline.research.h_2026_04_27_secrsi.forward_shadow basket-open
        11:00 IST. Reads today's opens file, fetches Kite LTP, computes
        per-stock %chg, aggregates to per-sector median via SectorMapper,
        picks top-2/bottom-2 sectors, picks 2 best/worst stocks each (8
        legs), computes ATR(14)*2 stops, appends OPEN rows to
        ``pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv``.
        Idempotent on (date, basket_id) — re-runs are a no-op.

    python -m pipeline.research.h_2026_04_27_secrsi.forward_shadow basket-close [--date YYYY-MM-DD]
        14:30 IST. For each OPEN leg with the given date, fetches LTP and
        writes exit_px / pnl_pct / status=CLOSED, exit_reason=TIME_STOP.
        Idempotent on already-CLOSED rows.

This driver is intentionally additive. It does not touch H-001
(``pipeline/h_2026_04_26_001_paper.py``) or any other paper book.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pipeline.research.h_2026_04_27_secrsi.basket_builder import build_basket
from pipeline.research.h_2026_04_27_secrsi.sector_snapshot import take_snapshot

log = logging.getLogger("anka.secrsi.forward_shadow")

_IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = _REPO_ROOT / "pipeline"
_RESEARCH_DIR = _PIPELINE_DIR / "data" / "research" / "h_2026_04_27_secrsi"
_OPENS_DIR = _RESEARCH_DIR / "opens"
_RECS_PATH = _RESEARCH_DIR / "recommendations.csv"
_TODAY_REGIME_PATH = _PIPELINE_DIR / "data" / "today_regime.json"
_CANONICAL_UNIVERSE = _PIPELINE_DIR / "data" / "canonical_fno_research_v3.json"

_CSV_COLUMNS = [
    "basket_id", "leg_id", "ticker", "date", "sector", "sector_score",
    "side", "weight", "stock_pct_at_snap", "regime",
    "entry_time", "entry_px", "atr_14", "stop_px",
    "exit_time", "exit_px", "exit_reason", "pnl_pct", "status",
    # Retroactive PIT-correction columns. Always empty on forward writes;
    # only populated by a backfill script when a later audit finds the
    # `regime` value was sourced from a stale truth file (e.g. the
    # 2026-04-30 stale-VPS-regime backfill). Keeps the original
    # recorded value intact for forensic audit.
    "regime_pit_corrected", "regime_correction_reason",
]

_MIN_STOCKS_PER_SECTOR = 4


def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _basket_id(date_iso: str) -> str:
    return f"SECRSI-{date_iso}"


def _leg_id(date_iso: str, ticker: str, side: str) -> str:
    return f"SECRSI-{date_iso}-{ticker}-{side}"


# ---- Live data wrappers (lazy-imported so tests can stub) -----------------

def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


def _compute_atr_stop(symbol: str, direction: str) -> dict:
    from pipeline.atr_stops import compute_atr_stop
    return compute_atr_stop(symbol, direction, window=14, mult=2.0)


def _load_universe() -> list[str]:
    if not _CANONICAL_UNIVERSE.is_file():
        log.error("canonical_fno_research_v3.json not found at %s", _CANONICAL_UNIVERSE)
        return []
    doc = json.loads(_CANONICAL_UNIVERSE.read_text(encoding="utf-8"))
    return list(doc.get("tickers", []))


def _load_sector_map() -> dict[str, str]:
    """Return {ticker: sector_key}. Loads SectorMapper at call time."""
    try:
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
    except Exception as exc:
        log.error("SectorMapper import failed: %s", exc)
        return {}
    sm = SectorMapper()
    full = sm.map_all()
    return {sym: meta.get("sector", "") for sym, meta in full.items()}


def _load_today_regime() -> str:
    if not _TODAY_REGIME_PATH.is_file():
        return "UNKNOWN"
    try:
        d = json.loads(_TODAY_REGIME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "UNKNOWN"
    return (d.get("zone") or d.get("regime") or d.get("regime_zone") or "UNKNOWN")


# ---- CSV ledger I/O -------------------------------------------------------

def _read_recs() -> list[dict]:
    if not _RECS_PATH.is_file():
        return []
    with _RECS_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_recs(rows: list[dict]) -> None:
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _RECS_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


def _append_rec(row: dict) -> None:
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = _RECS_PATH.is_file()
    with _RECS_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in _CSV_COLUMNS})


# ---- capture-opens --------------------------------------------------------

def cmd_capture_opens() -> int:
    today = _today_iso()
    universe = _load_universe()
    if not universe:
        log.error("no F&O universe loaded; aborting capture-opens")
        return 1

    log.info("capture-opens: fetching LTP for %d tickers", len(universe))
    prices = _fetch_ltp(universe)
    if not prices:
        log.error("no opens fetched (Kite session?); aborting")
        return 1

    _OPENS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OPENS_DIR / f"{today}.json"
    out_path.write_text(json.dumps({
        "date": today,
        "captured_at": _now_iso(),
        "n_tickers_requested": len(universe),
        "n_tickers_fetched": len(prices),
        "prices": prices,
    }, indent=2), encoding="utf-8")
    log.info("capture-opens: wrote %d/%d to %s", len(prices), len(universe), out_path)
    return 0


def _load_opens(date_iso: str) -> dict[str, float]:
    p = _OPENS_DIR / f"{date_iso}.json"
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = doc.get("prices", {}) or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


# ---- basket-open ----------------------------------------------------------

def _build_open_row(
    leg: dict,
    entry_px: float,
    atr_info: dict,
    regime: str,
    today: str,
    now: str,
) -> dict:
    atr_14 = atr_info.get("atr_14")
    stop_px = atr_info.get("stop_price")
    return {
        "basket_id": _basket_id(today),
        "leg_id": _leg_id(today, leg["ticker"], leg["side"]),
        "ticker": leg["ticker"],
        "date": today,
        "sector": leg["sector"],
        "sector_score": f"{leg['sector_score']:.6f}",
        "side": leg["side"],
        "weight": f"{leg['weight']:.4f}",
        "stock_pct_at_snap": f"{leg['stock_pct_at_snap']:.6f}",
        "regime": regime,
        "entry_time": now,
        "entry_px": f"{entry_px:.4f}",
        "atr_14": "" if atr_14 is None else f"{atr_14:.4f}",
        "stop_px": "" if stop_px is None else f"{stop_px:.4f}",
        "exit_time": "",
        "exit_px": "",
        "exit_reason": "",
        "pnl_pct": "",
        "status": "OPEN",
        "regime_pit_corrected": "",
        "regime_correction_reason": "",
    }


def cmd_basket_open() -> int:
    today = _today_iso()
    now = _now_iso()

    existing = _read_recs()
    if any(r.get("basket_id") == _basket_id(today) for r in existing):
        log.info("basket-open: basket %s already opened — skipping", _basket_id(today))
        return 0

    prices_open = _load_opens(today)
    if not prices_open:
        log.error("basket-open: opens file missing for %s — run capture-opens first", today)
        return 1

    universe = list(prices_open.keys())
    log.info("basket-open: fetching LTP for %d tickers", len(universe))
    prices_now = _fetch_ltp(universe)
    if not prices_now:
        log.error("basket-open: no LTP fetched; aborting")
        return 1

    sector_map = _load_sector_map()
    if not sector_map:
        log.error("basket-open: empty sector map; aborting")
        return 1

    snapshot = take_snapshot(
        prices_open, prices_now, sector_map,
        min_stocks_per_sector=_MIN_STOCKS_PER_SECTOR,
    )
    basket = build_basket(snapshot)
    if not basket:
        log.warning("basket-open: insufficient qualifying sectors for %s — no trade", today)
        return 0

    regime = _load_today_regime()
    log.info("basket-open: regime=%s, %d legs", regime, len(basket))

    for leg in basket:
        entry_px = prices_now.get(leg["ticker"])
        if entry_px is None or entry_px <= 0:
            log.warning("basket-open: missing entry price for %s — dropping leg", leg["ticker"])
            continue
        atr_info = _compute_atr_stop(leg["ticker"], leg["side"])
        row = _build_open_row(leg, float(entry_px), atr_info, regime, today, now)
        _append_rec(row)
        log.info(
            "basket-open: %s %s sector=%s @ %.2f stop=%s",
            leg["side"], leg["ticker"], leg["sector"], entry_px,
            atr_info.get("stop_price"),
        )

    _save_basket_snapshot(today, snapshot, basket, regime)
    return 0


def _save_basket_snapshot(date_iso: str, snapshot: list[dict], basket: list[dict], regime: str) -> None:
    """Forensic record of what the snapshot saw and what the basket picked."""
    snapshots_dir = _RESEARCH_DIR / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    out = snapshots_dir / f"{date_iso}.json"
    out.write_text(json.dumps({
        "date": date_iso,
        "captured_at": _now_iso(),
        "regime": regime,
        "snapshot": snapshot,
        "basket": basket,
    }, indent=2, default=str), encoding="utf-8")


# ---- basket-close ---------------------------------------------------------

def _pnl_pct(side: str, entry: float, exit_: float) -> float:
    if entry <= 0:
        return 0.0
    raw = (exit_ - entry) / entry * 100.0
    return raw if side == "LONG" else -raw


def cmd_basket_close(target_date: Optional[str] = None) -> int:
    date_iso = target_date or _today_iso()
    rows = _read_recs()
    open_rows = [r for r in rows if r.get("date") == date_iso and r.get("status") == "OPEN"]
    if not open_rows:
        log.info("basket-close: no OPEN legs for %s — nothing to do", date_iso)
        return 0

    tickers = [r["ticker"] for r in open_rows]
    log.info("basket-close: fetching LTP for %d open legs on %s", len(tickers), date_iso)
    ltp = _fetch_ltp(tickers)
    if not ltp:
        log.error("basket-close: no LTP fetched; aborting")
        return 1

    now = _now_iso()
    closed_count = 0
    for r in rows:
        if r.get("date") != date_iso or r.get("status") != "OPEN":
            continue
        ticker = r["ticker"]
        side = r["side"]
        exit_px = ltp.get(ticker)
        if exit_px is None or exit_px <= 0:
            log.warning("basket-close: missing LTP for %s — leaving OPEN", ticker)
            continue
        try:
            entry_px = float(r["entry_px"])
        except (TypeError, ValueError):
            continue
        pnl = _pnl_pct(side, entry_px, float(exit_px))
        r["exit_time"] = now
        r["exit_px"] = f"{float(exit_px):.4f}"
        r["exit_reason"] = "TIME_STOP"
        r["pnl_pct"] = f"{pnl:.4f}"
        r["status"] = "CLOSED"
        closed_count += 1

    _write_recs(rows)
    log.info("basket-close: closed %d legs for %s", closed_count, date_iso)
    return 0


# ---- entrypoint -----------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="secrsi.forward_shadow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture-opens")
    sub.add_parser("basket-open")
    p_close = sub.add_parser("basket-close")
    p_close.add_argument("--date", default=None, help="YYYY-MM-DD; default = today IST")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.cmd == "capture-opens":
        return cmd_capture_opens()
    if args.cmd == "basket-open":
        return cmd_basket_open()
    if args.cmd == "basket-close":
        return cmd_basket_close(args.date)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
