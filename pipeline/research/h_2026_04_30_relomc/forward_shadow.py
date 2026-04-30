"""RELOMC-EUPHORIA forward-shadow paper-trade driver (H-2026-04-30-RELOMC-EUPHORIA).

Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md

Three CLI subcommands run during the holdout window 2026-05-01 -> 2027-04-30:

    python -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-open
        09:15-09:25 IST. Reads today_regime.json, fires only if zone == EUPHORIA
        AND basket-id for today is not already in the ledger AND today is
        within the holdout window. Writes 3 OPEN rows (RELIANCE LONG,
        BPCL SHORT, IOC SHORT) at Kite LTP. Equal-notional dollar-neutral
        sizing (each leg's weight = 1/n_long for longs, -1/n_short for shorts).
        Idempotent on (basket_id) — re-runs are a no-op.

    python -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-monitor
        Every intraday cycle. For each open basket, computes basket-level
        pnl_bps using current Kite LTP. If basket pnl <= STOP_BPS (-300 bps),
        closes all 3 legs at LTP with exit_reason=BASKET_STOP.

    python -m pipeline.research.h_2026_04_30_relomc.forward_shadow basket-close [--date YYYY-MM-DD]
        14:25 IST. For each open basket, if today >= entry_date + 5 trading
        days, closes all 3 legs at LTP with exit_reason=TIME_STOP.

This driver is intentionally additive. It does not touch any other paper book
or live signal path.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.relomc.forward_shadow")

_IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = _REPO_ROOT / "pipeline"
_RESEARCH_DIR = _PIPELINE_DIR / "data" / "research" / "h_2026_04_30_relomc"
_RECS_PATH = _RESEARCH_DIR / "recommendations.csv"
_TODAY_REGIME_PATH = _PIPELINE_DIR / "data" / "today_regime.json"

# Hypothesis lock - DO NOT change during holdout (single_touch_locked).
LONG_LEGS: tuple[str, ...] = ("RELIANCE",)
SHORT_LEGS: tuple[str, ...] = ("BPCL", "IOC")
REGIME_GATE = "EUPHORIA"
HOLD_TRADING_DAYS = 5
STOP_BPS = -300.0  # -3.0% per basket
COST_RT_BPS = 20.0
HOLDOUT_START = date(2026, 5, 1)
HOLDOUT_END = date(2027, 4, 30)

_CSV_COLUMNS = [
    "basket_id", "leg_id", "ticker", "side", "weight",
    "entry_date", "entry_time", "entry_px",
    "regime_at_entry",
    "target_close_date",
    "exit_date", "exit_time", "exit_px", "exit_reason",
    "pnl_pct", "status",
    "regime_pit_corrected", "regime_correction_reason",
]


def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _basket_id(date_iso: str) -> str:
    return f"RELOMC-{date_iso}"


def _leg_id(date_iso: str, ticker: str, side: str) -> str:
    return f"RELOMC-{date_iso}-{ticker}-{side}"


def _add_trading_days(start: date, n: int) -> date:
    """Return the date that is `n` trading days after `start` (NSE calendar)."""
    from pipeline.trading_calendar import is_trading_day
    out = start
    added = 0
    while added < n:
        out = out + timedelta(days=1)
        if is_trading_day(datetime.combine(out, datetime.min.time(), tzinfo=_IST)):
            added += 1
    return out


def _in_holdout(d: date) -> bool:
    return HOLDOUT_START <= d <= HOLDOUT_END


# ---- Live data wrappers (lazy-imported so tests can stub) -----------------

def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


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


def _append_rows(new_rows: list[dict]) -> None:
    if not new_rows:
        return
    _RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = _RECS_PATH.is_file()
    with _RECS_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        for r in new_rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


# ---- basket-open ----------------------------------------------------------

def _build_open_rows(today: str, prices: dict[str, float], regime: str) -> list[dict]:
    long_w = 1.0 / len(LONG_LEGS)
    short_w = 1.0 / len(SHORT_LEGS)
    target_close = _add_trading_days(date.fromisoformat(today), HOLD_TRADING_DAYS).isoformat()
    now = _now_iso()
    bid = _basket_id(today)
    rows: list[dict] = []
    for tkr in LONG_LEGS:
        px = prices.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing price for LONG %s", tkr)
            return []
        rows.append({
            "basket_id": bid,
            "leg_id": _leg_id(today, tkr, "LONG"),
            "ticker": tkr,
            "side": "LONG",
            "weight": f"{long_w:.4f}",
            "entry_date": today,
            "entry_time": now,
            "entry_px": f"{float(px):.4f}",
            "regime_at_entry": regime,
            "target_close_date": target_close,
            "exit_date": "",
            "exit_time": "",
            "exit_px": "",
            "exit_reason": "",
            "pnl_pct": "",
            "status": "OPEN",
            "regime_pit_corrected": "",
            "regime_correction_reason": "",
        })
    for tkr in SHORT_LEGS:
        px = prices.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing price for SHORT %s", tkr)
            return []
        rows.append({
            "basket_id": bid,
            "leg_id": _leg_id(today, tkr, "SHORT"),
            "ticker": tkr,
            "side": "SHORT",
            "weight": f"{-short_w:.4f}",
            "entry_date": today,
            "entry_time": now,
            "entry_px": f"{float(px):.4f}",
            "regime_at_entry": regime,
            "target_close_date": target_close,
            "exit_date": "",
            "exit_time": "",
            "exit_px": "",
            "exit_reason": "",
            "pnl_pct": "",
            "status": "OPEN",
            "regime_pit_corrected": "",
            "regime_correction_reason": "",
        })
    return rows


def cmd_basket_open() -> int:
    today = _today_iso()
    today_d = date.fromisoformat(today)

    if not _in_holdout(today_d):
        log.info("basket-open: %s outside holdout window — no-op", today)
        return 0

    existing = _read_recs()
    if any(r.get("basket_id") == _basket_id(today) for r in existing):
        log.info("basket-open: basket %s already opened — skipping", _basket_id(today))
        return 0

    regime = _load_today_regime()
    if regime != REGIME_GATE:
        log.info("basket-open: regime=%s != %s — no trade today", regime, REGIME_GATE)
        return 0

    universe = list(LONG_LEGS) + list(SHORT_LEGS)
    log.info("basket-open: regime=%s — fetching LTP for %s", regime, universe)
    prices = _fetch_ltp(universe)
    missing = [t for t in universe if t not in prices or prices.get(t, 0) <= 0]
    if missing:
        log.error("basket-open: missing LTP for %s — aborting", missing)
        return 1

    rows = _build_open_rows(today, prices, regime)
    if not rows:
        return 1
    _append_rows(rows)
    log.info("basket-open: opened %d legs for basket %s", len(rows), _basket_id(today))
    return 0


# ---- basket-monitor (basket-stop check) -----------------------------------

def _basket_pnl_bps(basket_rows: list[dict], live_ltp: dict[str, float]) -> Optional[float]:
    """Compute current basket pnl in bps. Returns None if any leg is missing LTP."""
    if not basket_rows:
        return None
    total_weighted = 0.0
    weight_sum = 0.0
    for r in basket_rows:
        try:
            entry = float(r["entry_px"])
            w = float(r["weight"])
        except (TypeError, ValueError, KeyError):
            return None
        ltp = live_ltp.get(r["ticker"])
        if ltp is None or ltp <= 0 or entry <= 0:
            return None
        # signed return contribution: weight already encodes sign (LONG +, SHORT -)
        leg_ret = (ltp - entry) / entry
        total_weighted += w * leg_ret
        weight_sum += abs(w)
    if weight_sum == 0:
        return None
    return total_weighted / weight_sum * 10000.0


def _close_basket(rows: list[dict], basket_id: str, live_ltp: dict[str, float],
                  exit_reason: str, today: str, now: str) -> int:
    closed = 0
    for r in rows:
        if r.get("basket_id") != basket_id or r.get("status") != "OPEN":
            continue
        ltp = live_ltp.get(r["ticker"])
        if ltp is None or ltp <= 0:
            log.warning("close: missing LTP for %s in %s — leaving OPEN", r["ticker"], basket_id)
            continue
        try:
            entry = float(r["entry_px"])
        except (TypeError, ValueError):
            continue
        side = r["side"]
        raw = (float(ltp) - entry) / entry * 100.0
        pnl_pct = raw if side == "LONG" else -raw
        r["exit_date"] = today
        r["exit_time"] = now
        r["exit_px"] = f"{float(ltp):.4f}"
        r["exit_reason"] = exit_reason
        r["pnl_pct"] = f"{pnl_pct:.4f}"
        r["status"] = "CLOSED"
        closed += 1
    return closed


def cmd_basket_monitor() -> int:
    today = _today_iso()
    now = _now_iso()
    rows = _read_recs()
    open_rows = [r for r in rows if r.get("status") == "OPEN"]
    if not open_rows:
        log.info("basket-monitor: no open baskets — nothing to do")
        return 0

    by_basket: dict[str, list[dict]] = {}
    for r in open_rows:
        by_basket.setdefault(r["basket_id"], []).append(r)

    tickers = sorted({r["ticker"] for r in open_rows})
    ltp = _fetch_ltp(tickers)
    if not ltp:
        log.error("basket-monitor: no LTP fetched — aborting")
        return 1

    any_closed = False
    for bid, brs in by_basket.items():
        pnl = _basket_pnl_bps(brs, ltp)
        if pnl is None:
            log.warning("basket-monitor: %s missing LTP — skipping", bid)
            continue
        if pnl <= STOP_BPS:
            log.info("basket-monitor: %s pnl=%.1fbp <= stop=%.1fbp — closing", bid, pnl, STOP_BPS)
            _close_basket(rows, bid, ltp, "BASKET_STOP", today, now)
            any_closed = True
        else:
            log.info("basket-monitor: %s pnl=%.1fbp (no stop)", bid, pnl)

    if any_closed:
        _write_recs(rows)
    return 0


# ---- basket-close (time-stop) ---------------------------------------------

def cmd_basket_close(target_date_iso: Optional[str] = None) -> int:
    today = target_date_iso or _today_iso()
    today_d = date.fromisoformat(today)
    now = _now_iso()
    rows = _read_recs()
    open_rows = [r for r in rows if r.get("status") == "OPEN"]
    if not open_rows:
        log.info("basket-close: no open baskets — nothing to do")
        return 0

    # Group open rows by basket_id, only those whose target_close_date <= today.
    by_basket: dict[str, list[dict]] = {}
    for r in open_rows:
        try:
            tgt = date.fromisoformat(r.get("target_close_date", ""))
        except ValueError:
            continue
        if today_d >= tgt:
            by_basket.setdefault(r["basket_id"], []).append(r)

    if not by_basket:
        log.info("basket-close: no baskets with target_close_date <= %s", today)
        return 0

    tickers = sorted({r["ticker"] for brs in by_basket.values() for r in brs})
    ltp = _fetch_ltp(tickers)
    if not ltp:
        log.error("basket-close: no LTP fetched — aborting")
        return 1

    closed_count = 0
    for bid in by_basket:
        n = _close_basket(rows, bid, ltp, "TIME_STOP", today, now)
        log.info("basket-close: %s closed %d legs", bid, n)
        closed_count += n

    if closed_count:
        _write_recs(rows)
    return 0


# ---- entrypoint -----------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="relomc.forward_shadow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("basket-open")
    sub.add_parser("basket-monitor")
    p_close = sub.add_parser("basket-close")
    p_close.add_argument("--date", default=None, help="YYYY-MM-DD; default = today IST")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.cmd == "basket-open":
        return cmd_basket_open()
    if args.cmd == "basket-monitor":
        return cmd_basket_monitor()
    if args.cmd == "basket-close":
        return cmd_basket_close(args.date)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
