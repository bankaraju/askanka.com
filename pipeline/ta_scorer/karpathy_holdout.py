"""H-2026-04-29-ta-karpathy-v1 holdout OPEN/CLOSE paper-trade driver.

Spec: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md sections 10, 14, 15.

Single-touch forward holdout 2026-04-29 09:15 IST -> 2026-05-28 15:25 IST.

CLI:
    python -m pipeline.ta_scorer.karpathy_holdout open
        09:15 IST. Reads pipeline/data/research/h_2026_04_29_ta_karpathy_v1/
        today_predictions.json and manifest.json. For each cell where
        signal_long==True or signal_short==True AND the cell's
        qualifier_pass==True in manifest.json, fetches Kite LTP, computes
        ATR(14)*2 stop, appends one OPEN row per (date, ticker, direction)
        to recommendations.csv. Idempotent on (date, ticker, direction).

    python -m pipeline.ta_scorer.karpathy_holdout close [--date YYYY-MM-DD]
        15:25 IST mechanical close. For each OPEN row on `date`, fetches
        LTP, sets exit_px / pnl_pct / status=CLOSED, exit_reason=TIME_STOP.
        Idempotent on already-CLOSED rows.

Holdout window guard: skip OPEN if today < 2026-04-29 or today > 2026-05-28.
Qualifier_pass gate: only cells passing all 5 gates of spec section 9 are
opened, even if today_predictions.json emits a signal for them.

Position size: NOT enforced. Spec section 10 specifies notional Rs.50000 per
leg per stock for verdict comparability; the live ledger writes percentage
P&L only and the verdict runner converts to notional at evaluation time.

Holding period: T+1 09:15 -> T+1 15:25 intraday only. Per spec section 10.7
(no overnight, no T+2, no scale-out, no trail).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("anka.karpathy_holdout")

_IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUN_ROOT = _REPO_ROOT / "pipeline" / "data" / "research" / "h_2026_04_29_ta_karpathy_v1"
_PREDICTIONS_PATH = _RUN_ROOT / "today_predictions.json"
_MANIFEST_PATH = _RUN_ROOT / "manifest.json"
_RECS_PATH = _RUN_ROOT / "recommendations.csv"

# Spec section 7: single-touch holdout window
HOLDOUT_START = "2026-04-29"
HOLDOUT_END = "2026-05-28"

# Spec section 14: locked column order
_CSV_COLUMNS = [
    "signal_id", "ticker", "date", "direction", "regime",
    "p_long", "p_short", "side", "entry_time", "entry_px",
    "atr_14", "stop_px", "exit_time", "exit_px", "exit_reason",
    "pnl_pct", "status",
]


# ---- Time / date helpers (separated for monkeypatching) -------------------

def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _within_holdout(today: str) -> bool:
    return HOLDOUT_START <= today <= HOLDOUT_END


# ---- Live data wrappers (lazy-imported to keep tests off live infra) ------

def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


def _compute_atr_stop(symbol: str, direction: str) -> dict:
    from pipeline.atr_stops import compute_atr_stop
    return compute_atr_stop(symbol, direction, window=14, mult=2.0)


def _load_today_regime_zone() -> str:
    """Today's regime zone from the live engine's today_regime.json.

    Same source as h_2026_04_26_001_paper -- canonical live signal, NOT the
    hindsight-built regime_history.csv (see
    memory/reference_regime_history_csv_contamination.md).
    """
    path = _REPO_ROOT / "pipeline" / "data" / "today_regime.json"
    if not path.is_file():
        log.warning("today_regime.json not found at %s", path)
        return "UNKNOWN"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("today_regime.json read failed: %s", exc)
        return "UNKNOWN"
    return d.get("zone") or d.get("regime") or d.get("regime_zone") or "UNKNOWN"


# ---- Pure helpers ---------------------------------------------------------

def _load_predictions() -> list[dict]:
    if not _PREDICTIONS_PATH.is_file():
        log.warning("today_predictions.json not found at %s", _PREDICTIONS_PATH)
        return []
    try:
        doc = json.loads(_PREDICTIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("today_predictions.json invalid JSON: %s", exc)
        return []
    return doc.get("predictions", []) or []


def _load_qualifying_cells() -> set[tuple[str, str]]:
    """Read manifest.json and return the set of (ticker, direction) cells
    whose qualifier_pass==True. These are the only cells eligible for forward
    trading per spec section 9.
    """
    if not _MANIFEST_PATH.is_file():
        log.warning("manifest.json not found at %s -- no cells qualify", _MANIFEST_PATH)
        return set()
    try:
        doc = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("manifest.json invalid JSON: %s", exc)
        return set()
    cells = doc.get("qualifier_summary_per_cell", []) or []
    qualifying: set[tuple[str, str]] = set()
    for c in cells:
        if c.get("qualifier_pass") is True:
            qualifying.add((c["ticker"], c["direction"]))
    return qualifying


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
    file_exists = _RECS_PATH.is_file()
    with _RECS_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in _CSV_COLUMNS})


# ---- OPEN command ---------------------------------------------------------

def _eligible_signals(predictions: list[dict],
                      qualifying: set[tuple[str, str]]) -> list[tuple[dict, str]]:
    """Yield (prediction_row, direction) for each signal that fires AND whose
    cell qualified the manifest gate.
    """
    out: list[tuple[dict, str]] = []
    for p in predictions:
        ticker = p.get("ticker")
        if not ticker:
            continue
        if p.get("signal_long") and (ticker, "long") in qualifying:
            out.append((p, "long"))
        if p.get("signal_short") and (ticker, "short") in qualifying:
            out.append((p, "short"))
    return out


def _build_open_row(pred: dict, direction: str, entry_px: float,
                    atr_info: dict, regime: str, today: str, now: str) -> dict:
    side = "LONG" if direction == "long" else "SHORT"
    ticker = pred["ticker"]
    atr_14 = atr_info.get("atr_14")
    stop_px = atr_info.get("stop_price")
    p_long = pred.get("p_long")
    p_short = pred.get("p_short")
    return {
        "signal_id": f"KARP-{today}-{ticker}-{direction.upper()}",
        "ticker": ticker, "date": today,
        "direction": direction, "regime": regime,
        "p_long": "" if p_long is None else f"{p_long:.4f}",
        "p_short": "" if p_short is None else f"{p_short:.4f}",
        "side": side,
        "entry_time": now, "entry_px": f"{entry_px:.4f}",
        "atr_14": "" if atr_14 is None else f"{atr_14:.4f}",
        "stop_px": "" if stop_px is None else f"{stop_px:.4f}",
        "exit_time": "", "exit_px": "", "exit_reason": "",
        "pnl_pct": "", "status": "OPEN",
    }


def cmd_open() -> int:
    today = _today_iso()
    if not _within_holdout(today):
        log.info("today=%s is outside single-touch holdout window [%s, %s] -- nothing to open",
                 today, HOLDOUT_START, HOLDOUT_END)
        return 0

    predictions = _load_predictions()
    if not predictions:
        log.info("no predictions; nothing to open")
        return 0

    qualifying = _load_qualifying_cells()
    if not qualifying:
        log.info("no qualifying cells in manifest -- 0 stocks eligible for trading")
        return 0
    log.info("%d qualifying cells: %s", len(qualifying), sorted(qualifying))

    eligible = _eligible_signals(predictions, qualifying)
    if not eligible:
        log.info("no signals fire for qualifying cells today")
        return 0

    seen: set[tuple[str, str, str]] = {
        (r["date"], r["ticker"], r["direction"]) for r in _read_recs()
    }
    new_signals: list[tuple[dict, str]] = []
    for pred, direction in eligible:
        key = (today, pred["ticker"], direction)
        if key in seen:
            log.info("skip duplicate (date=%s, ticker=%s, direction=%s) -- already in CSV",
                     *key)
            continue
        new_signals.append((pred, direction))

    if not new_signals:
        log.info("no new signals to record")
        return 0

    syms = sorted({p["ticker"] for p, _ in new_signals})
    log.info("fetching LTP for %d eligible tickers", len(syms))
    ltp = _fetch_ltp(syms)

    regime = _load_today_regime_zone()
    now = _now_iso()
    n_written = 0
    for pred, direction in new_signals:
        sym = pred["ticker"]
        if sym not in ltp:
            log.warning("no LTP for %s -- skipping", sym)
            continue
        entry_px = float(ltp[sym])
        side_word = "LONG" if direction == "long" else "SHORT"
        try:
            atr_info = _compute_atr_stop(sym, side_word)
        except Exception as exc:
            log.warning("ATR stop failed for %s: %s -- using empty atr/stop", sym, exc)
            atr_info = {"atr_14": None, "stop_price": None,
                        "stop_pct": None, "stop_source": "fallback"}
        row = _build_open_row(pred, direction, entry_px, atr_info, regime, today, now)
        _append_rec(row)
        n_written += 1
        log.info("OPEN  %-12s dir=%-5s side=%-5s entry=%.2f stop=%s p_long=%s p_short=%s",
                 sym, direction, row["side"], entry_px,
                 row["stop_px"] or "-", row["p_long"] or "-", row["p_short"] or "-")

    log.info("recommendations.csv: %d new OPEN rows", n_written)
    return 0


# ---- CLOSE command --------------------------------------------------------

def _pnl_pct(entry_px: float, exit_px: float, side: str) -> float:
    sign = 1.0 if side == "LONG" else -1.0
    return (exit_px - entry_px) / entry_px * sign * 100.0


def cmd_close(date_override: Optional[str] = None) -> int:
    target_date = date_override or _today_iso()
    rows = _read_recs()
    if not rows:
        log.info("recommendations.csv empty or missing; nothing to close")
        return 0

    open_idxs = [i for i, r in enumerate(rows)
                 if r.get("date") == target_date and r.get("status") == "OPEN"]
    if not open_idxs:
        log.info("no OPEN rows for date=%s; nothing to close", target_date)
        return 0

    open_syms = sorted({rows[i]["ticker"] for i in open_idxs})
    log.info("fetching LTP for %d OPEN tickers @ TIME_STOP", len(open_syms))
    ltp = _fetch_ltp(open_syms)
    if not ltp:
        log.error("LTP fetch returned nothing -- leaving CSV untouched")
        return 1

    now = _now_iso()
    n_closed = 0
    for i in open_idxs:
        r = rows[i]
        sym = r["ticker"]
        if sym not in ltp:
            log.warning("no LTP for OPEN ticker %s -- leaving as OPEN", sym)
            continue
        try:
            entry_px = float(r["entry_px"])
        except (TypeError, ValueError):
            log.warning("bad entry_px on row for %s -- skipping", sym)
            continue
        exit_px = float(ltp[sym])
        pnl = _pnl_pct(entry_px, exit_px, r["side"])
        r["exit_px"] = f"{exit_px:.4f}"
        r["exit_time"] = now
        r["exit_reason"] = "TIME_STOP"
        r["pnl_pct"] = f"{pnl:.4f}"
        r["status"] = "CLOSED"
        n_closed += 1
        log.info("CLOSE %-12s dir=%-5s side=%-5s entry=%.2f exit=%.2f pnl=%+.2f%%",
                 sym, r.get("direction", "?"), r["side"], entry_px, exit_px, pnl)

    if n_closed == 0:
        log.info("no rows transitioned OPEN -> CLOSED")
        return 0
    _write_recs(rows)
    log.info("recommendations.csv: %d rows transitioned OPEN -> CLOSED", n_closed)
    return 0


# ---- CLI ------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.ta_scorer.karpathy_holdout",
        description="H-2026-04-29-ta-karpathy-v1 holdout paper-trade driver "
                    "(spec: docs/superpowers/specs/"
                    "2026-04-29-ta-karpathy-v1-design.md sections 10/14/15)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open", help="Append OPEN rows for today's qualifying-cell signals (09:15 IST)")
    p_close = sub.add_parser("close", help="Close today's OPEN rows at LTP (15:25 IST)")
    p_close.add_argument("--date", default=None,
                         help="Override the trade date (YYYY-MM-DD). Defaults to today IST.")
    return parser


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    _setup_logging()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "open":
        return cmd_open()
    if args.cmd == "close":
        return cmd_close(args.date)
    parser.error(f"unknown cmd: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
