"""Defence momentum forward-shadow paper-trade driver (bundle).

Spec: docs/superpowers/specs/2026-04-30-defence-momentum-design.md

Drives BOTH:
  - H-2026-04-30-DEFENCE-IT-NEUTRAL  (short_id=DEFIT)
  - H-2026-04-30-DEFENCE-AUTO-RISKON (short_id=DEFAU)

via a `--hypothesis` CLI flag. Each hypothesis has its own ledger
directory; they are independent paper books.

CLI subcommands:

    python -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow \
        --hypothesis DEFIT  basket-open
        09:15-09:25 IST. Fires only if today_regime.json zone matches
        the hypothesis's regime_gate AND today is in holdout window AND
        the basket-id for today is not already in the ledger. Computes
        ATR(14)-scaled per-leg weights, opens 6 (or 4) legs at LTP.
        Aborts if any leg LTP missing.

    python -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow \
        --hypothesis DEFIT  basket-monitor
        Every intraday cycle. Computes basket-level pnl in bps; if
        <= stop_bps (-250 bps), closes all legs with BASKET_STOP.

    python -m pipeline.research.h_2026_04_30_defence_momentum.forward_shadow \
        --hypothesis DEFIT  basket-close [--date YYYY-MM-DD]
        14:25 IST. Closes baskets whose target_close_date <= today
        with TIME_STOP.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pipeline.research.h_2026_04_30_defence_momentum.config import (
    CONFIGS, HypothesisConfig, get_config,
)
from pipeline.research.h_2026_04_30_defence_momentum.sizing import atr_scaled_weights

log = logging.getLogger("anka.defence_momentum.forward_shadow")

_IST = timezone(timedelta(hours=5, minutes=30))
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = _REPO_ROOT / "pipeline"
_RESEARCH_BASE = _PIPELINE_DIR / "data" / "research" / "h_2026_04_30_defence_momentum"
_TODAY_REGIME_PATH = _PIPELINE_DIR / "data" / "today_regime.json"
_FNO_HIST = _PIPELINE_DIR / "data" / "fno_historical"

_CSV_COLUMNS = [
    "hypothesis_id", "basket_id", "leg_id",
    "ticker", "side", "weight",
    "entry_date", "entry_time", "entry_px", "atr_pct",
    "regime_at_entry", "target_close_date",
    "exit_date", "exit_time", "exit_px", "exit_reason",
    "pnl_pct", "status",
    "regime_pit_corrected", "regime_correction_reason",
]


def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _basket_id(short_id: str, date_iso: str) -> str:
    return f"{short_id}-{date_iso}"


def _leg_id(short_id: str, date_iso: str, ticker: str, side: str) -> str:
    return f"{short_id}-{date_iso}-{ticker}-{side}"


def _ledger_path(cfg: HypothesisConfig) -> Path:
    return _RESEARCH_BASE / cfg.short_id.lower() / "recommendations.csv"


def _add_trading_days(start: date, n: int) -> date:
    from pipeline.trading_calendar import is_trading_day
    out = start
    added = 0
    while added < n:
        out = out + timedelta(days=1)
        if is_trading_day(datetime.combine(out, datetime.min.time(), tzinfo=_IST)):
            added += 1
    return out


def _in_holdout(cfg: HypothesisConfig, d: date) -> bool:
    return cfg.holdout_start <= d <= cfg.holdout_end


# ---- Live data wrappers ---------------------------------------------------

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


def _atr_pct_from_csv(ticker: str, fno_hist_dir: Path = _FNO_HIST, window: int = 14) -> Optional[float]:
    """Compute ATR(window) / Close from fno_historical/<TICKER>.csv,
    using the True-Range definition. Returns ATR as a fraction
    (e.g. 0.025 for 2.5%), or None if data is insufficient.
    """
    p = fno_hist_dir / f"{ticker}.csv"
    if not p.is_file():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(p, parse_dates=["Date"])
    except Exception:
        return None
    if df.empty or len(df) < window + 2:
        return None
    df = df.sort_values("Date").tail(window + 2).copy()
    prev_close = df["Close"].shift(1)
    tr = (df[["High", "Low"]].assign(prev=prev_close)
          .apply(lambda r: max(r["High"] - r["Low"],
                               abs(r["High"] - r["prev"]) if not _isnan(r["prev"]) else 0.0,
                               abs(r["Low"] - r["prev"]) if not _isnan(r["prev"]) else 0.0),
                 axis=1))
    atr = float(tr.tail(window).mean())
    last_close = float(df["Close"].iloc[-1])
    if last_close <= 0:
        return None
    return atr / last_close


def _isnan(x) -> bool:
    try:
        return x != x
    except Exception:
        return False


# ---- CSV ledger I/O -------------------------------------------------------

def _read_recs(cfg: HypothesisConfig) -> list[dict]:
    path = _ledger_path(cfg)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_recs(cfg: HypothesisConfig, rows: list[dict]) -> None:
    path = _ledger_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


def _append_rows(cfg: HypothesisConfig, new_rows: list[dict]) -> None:
    if not new_rows:
        return
    path = _ledger_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not exists:
            writer.writeheader()
        for r in new_rows:
            writer.writerow({k: r.get(k, "") for k in _CSV_COLUMNS})


# ---- basket-open ----------------------------------------------------------

def _build_open_rows(
    cfg: HypothesisConfig, today: str, prices: dict[str, float],
    atr_pcts: dict[str, float], regime: str,
) -> list[dict]:
    long_w_raw = atr_scaled_weights(list(cfg.long_legs), atr_pcts, cap_x_baseline=cfg.cap_x_baseline)
    short_w_raw = atr_scaled_weights(list(cfg.short_legs), atr_pcts, cap_x_baseline=cfg.cap_x_baseline)
    target_close = _add_trading_days(date.fromisoformat(today), cfg.hold_trading_days).isoformat()
    now = _now_iso()
    bid = _basket_id(cfg.short_id, today)
    rows: list[dict] = []

    for tkr in cfg.long_legs:
        px = prices.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing price for LONG %s", tkr)
            return []
        rows.append(_make_row(
            cfg, bid, today, tkr, "LONG",
            float(long_w_raw.get(tkr, 0.0)),
            float(px), atr_pcts.get(tkr), regime, target_close, now,
        ))
    for tkr in cfg.short_legs:
        px = prices.get(tkr)
        if px is None or px <= 0:
            log.error("basket-open: missing price for SHORT %s", tkr)
            return []
        rows.append(_make_row(
            cfg, bid, today, tkr, "SHORT",
            -float(short_w_raw.get(tkr, 0.0)),
            float(px), atr_pcts.get(tkr), regime, target_close, now,
        ))
    return rows


def _make_row(
    cfg: HypothesisConfig, bid: str, today: str, tkr: str, side: str,
    weight: float, entry_px: float, atr_pct: Optional[float],
    regime: str, target_close: str, now: str,
) -> dict:
    return {
        "hypothesis_id": cfg.hypothesis_id,
        "basket_id": bid,
        "leg_id": _leg_id(cfg.short_id, today, tkr, side),
        "ticker": tkr,
        "side": side,
        "weight": f"{weight:.4f}",
        "entry_date": today,
        "entry_time": now,
        "entry_px": f"{entry_px:.4f}",
        "atr_pct": "" if atr_pct is None else f"{atr_pct:.6f}",
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
    }


def cmd_basket_open(cfg: HypothesisConfig) -> int:
    today = _today_iso()
    today_d = date.fromisoformat(today)
    if not _in_holdout(cfg, today_d):
        log.info("basket-open: %s outside holdout — no-op", today)
        return 0

    existing = _read_recs(cfg)
    if any(r.get("basket_id") == _basket_id(cfg.short_id, today) for r in existing):
        log.info("basket-open: basket %s already opened — skipping", _basket_id(cfg.short_id, today))
        return 0

    regime = _load_today_regime()
    if regime != cfg.regime_gate:
        log.info("basket-open: regime=%s != %s — no trade today", regime, cfg.regime_gate)
        return 0

    universe = list(cfg.long_legs) + list(cfg.short_legs)
    log.info("basket-open: regime=%s — fetching LTP for %s", regime, universe)
    prices = _fetch_ltp(universe)
    missing = [t for t in universe if t not in prices or prices.get(t, 0) <= 0]
    if missing:
        log.error("basket-open: missing LTP for %s — aborting", missing)
        return 1

    atr_pcts: dict[str, float] = {}
    for t in universe:
        ap = _atr_pct_from_csv(t)
        if ap is None:
            log.warning("basket-open: ATR unavailable for %s — sizing falls back to equal-weight", t)
        atr_pcts[t] = ap if ap is not None else 0.0

    rows = _build_open_rows(cfg, today, prices, atr_pcts, regime)
    if not rows:
        return 1
    _append_rows(cfg, rows)
    log.info("basket-open: opened %d legs for %s", len(rows), _basket_id(cfg.short_id, today))
    return 0


# ---- basket-monitor (basket-stop check) -----------------------------------

def _basket_pnl_bps(basket_rows: list[dict], live_ltp: dict[str, float]) -> Optional[float]:
    """Weighted-return basket pnl in bps. Weights are signed; positive
    weight = LONG, negative = SHORT, |sum_long| = 1, |sum_short| = 1.
    Total leverage |sum(|w|)| = 2 → bps = sum_signed_returns * 5000.

    Returns None if any leg is missing LTP.
    """
    if not basket_rows:
        return None
    weighted_ret = 0.0
    abs_w_sum = 0.0
    for r in basket_rows:
        try:
            entry = float(r["entry_px"])
            w = float(r["weight"])
        except (TypeError, ValueError, KeyError):
            return None
        ltp = live_ltp.get(r["ticker"])
        if ltp is None or ltp <= 0 or entry <= 0:
            return None
        weighted_ret += w * (float(ltp) - entry) / entry
        abs_w_sum += abs(w)
    if abs_w_sum == 0:
        return None
    return weighted_ret / abs_w_sum * 10000.0


def _close_basket(rows: list[dict], basket_id: str, live_ltp: dict[str, float],
                  exit_reason: str, today: str, now: str) -> int:
    closed = 0
    for r in rows:
        if r.get("basket_id") != basket_id or r.get("status") != "OPEN":
            continue
        ltp = live_ltp.get(r["ticker"])
        if ltp is None or ltp <= 0:
            log.warning("close: missing LTP for %s in %s", r["ticker"], basket_id)
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


def cmd_basket_monitor(cfg: HypothesisConfig) -> int:
    today = _today_iso()
    now = _now_iso()
    rows = _read_recs(cfg)
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
        log.error("basket-monitor: no LTP fetched")
        return 1

    any_closed = False
    for bid, brs in by_basket.items():
        pnl = _basket_pnl_bps(brs, ltp)
        if pnl is None:
            log.warning("basket-monitor: %s missing LTP — skipping", bid)
            continue
        if pnl <= cfg.stop_bps:
            log.info("basket-monitor: %s pnl=%.1fbp <= stop=%.1fbp — closing",
                     bid, pnl, cfg.stop_bps)
            _close_basket(rows, bid, ltp, "BASKET_STOP", today, now)
            any_closed = True
        else:
            log.info("basket-monitor: %s pnl=%.1fbp (no stop)", bid, pnl)

    if any_closed:
        _write_recs(cfg, rows)
    return 0


# ---- basket-close (time-stop) ---------------------------------------------

def cmd_basket_close(cfg: HypothesisConfig, target_date_iso: Optional[str] = None) -> int:
    today = target_date_iso or _today_iso()
    today_d = date.fromisoformat(today)
    now = _now_iso()
    rows = _read_recs(cfg)
    open_rows = [r for r in rows if r.get("status") == "OPEN"]
    if not open_rows:
        log.info("basket-close: no open baskets — nothing to do")
        return 0

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
        log.error("basket-close: no LTP fetched")
        return 1

    closed_count = 0
    for bid in by_basket:
        n = _close_basket(rows, bid, ltp, "TIME_STOP", today, now)
        log.info("basket-close: %s closed %d legs", bid, n)
        closed_count += n

    if closed_count:
        _write_recs(cfg, rows)
    return 0


# ---- entrypoint -----------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="defence_momentum.forward_shadow")
    parser.add_argument(
        "--hypothesis", required=True,
        choices=[c.short_id for c in CONFIGS],
        help="Which hypothesis to drive: DEFIT or DEFAU",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("basket-open")
    sub.add_parser("basket-monitor")
    p_close = sub.add_parser("basket-close")
    p_close.add_argument("--date", default=None, help="YYYY-MM-DD; default = today IST")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    cfg = get_config(args.hypothesis)
    if args.cmd == "basket-open":
        return cmd_basket_open(cfg)
    if args.cmd == "basket-monitor":
        return cmd_basket_monitor(cfg)
    if args.cmd == "basket-close":
        return cmd_basket_close(cfg, args.date)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
