"""H-2026-04-26-001 sigma-break mechanical mean-reversion -- paper-trade driver.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md

Forward paper test for hypothesis H-2026-04-26-001 and its sister cohort
H-2026-04-26-002 (regime-gated). Single-touch holdout window
2026-04-27 09:30 IST -> 2026-05-26 14:30 IST.

CLI:
    python -m pipeline.h_2026_04_26_001_paper open
        09:30 IST. Reads pipeline/data/correlation_breaks.json, keeps
        |z_score| >= 2.0, fades the divergence (z>0 -> SHORT, z<0 -> LONG),
        fetches Kite LTP, computes ATR(14)*2 stop, appends one OPEN row per
        (date, ticker) to pipeline/data/research/h_2026_04_26_001/
        recommendations.csv. Idempotent on (date, ticker).

    python -m pipeline.h_2026_04_26_001_paper close [--date YYYY-MM-DD]
        14:30 IST mechanical close. For each OPEN row on `date`, fetches
        LTP, sets exit_px / pnl_pct / status=CLOSED, exit_reason=TIME_STOP.
        Idempotent on already-CLOSED rows.

TODO(v2): intraday trail-stop arming + ATR stop enforcement. Spec calls
for trails arming at +0.6% and trailing by 1.2%, but live polling adds
operational complexity that is deferred. v1 only fires the 14:30 hard
close; trail levels are still written to the CSV for forensic post-trade
analysis (via end-of-day Kite minute-bar download).

Purely additive. Does not modify pipeline/phase_c_shadow.py (legacy Phase C
shadow ledger using deprecated PCR-LAG bucket; stays running for back-comp).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("anka.h_2026_04_26_001_paper")

_IST = timezone(timedelta(hours=5, minutes=30))
_PIPELINE_DIR = Path(__file__).resolve().parent
_BREAKS_PATH = _PIPELINE_DIR / "data" / "correlation_breaks.json"
_TODAY_REGIME_PATH = _PIPELINE_DIR / "data" / "today_regime.json"
_RECS_PATH = _PIPELINE_DIR / "data" / "research" / "h_2026_04_26_001" / "recommendations.csv"

# Spec section 14: locked column order. Two display-only columns appended
# 2026-04-29 — vwap_dev_signed_pct + filter_tag (KEEP/DROP/WATCH). Tag is
# informational during the holdout per §10.4 strict; existing rows that
# pre-date the addition write empty strings for both.
_CSV_COLUMNS = [
    "signal_id", "ticker", "date", "sigma_bucket", "regime", "sectoral_index",
    "side", "classification", "regime_gate_pass", "entry_time", "entry_px",
    "atr_14", "stop_px", "trail_arm_px", "trail_dist_pct", "exit_time",
    "exit_px", "exit_reason", "pnl_pct", "status",
    "vwap_dev_signed_pct", "filter_tag",
]

# Spec section 4-5 locked parameters
_SIGMA_THRESHOLD = 2.0
_TRAIL_ARM_PCT = 0.006   # arms at +0.6% favorable
_TRAIL_DIST_PCT = 1.2    # trail distance, in % units


# ---- Time / date helpers (separated for monkeypatching) -------------------

def _today_iso() -> str:
    return datetime.now(_IST).date().isoformat()


def _now_iso() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


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

    Canonical live source — written by AnkaETFSignal at 04:45 IST. Returns
    'UNKNOWN' when the file is missing or zone is absent. Not a fallback to
    regime_history.csv: that file is built with hindsight v2 weights (see
    memory/reference_regime_history_csv_contamination.md) and is unsuitable
    for live trade-tagging.
    """
    if not _TODAY_REGIME_PATH.is_file():
        log.warning("today_regime.json not found at %s", _TODAY_REGIME_PATH)
        return "UNKNOWN"
    try:
        d = json.loads(_TODAY_REGIME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("today_regime.json read failed: %s", exc)
        return "UNKNOWN"
    zone = d.get("zone") or d.get("regime") or d.get("regime_zone")
    return zone or "UNKNOWN"


# ---- Pure helpers ---------------------------------------------------------

def _load_breaks() -> dict:
    if not _BREAKS_PATH.is_file():
        log.warning("correlation_breaks.json not found at %s", _BREAKS_PATH)
        return {}
    try:
        return json.loads(_BREAKS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("correlation_breaks.json invalid JSON: %s", exc)
        return {}


def _filter_signals(breaks: list[dict]) -> list[dict]:
    """Keep rows with |z_score| >= _SIGMA_THRESHOLD and a usable symbol."""
    out: list[dict] = []
    for b in breaks:
        sym = b.get("symbol")
        if not sym:
            continue
        try:
            zf = float(b.get("z_score"))
        except (TypeError, ValueError):
            continue
        if abs(zf) >= _SIGMA_THRESHOLD:
            out.append(b)
    return out


def _side_from_z(z: float) -> str:
    """Spec section 5: z>0 = leader -> SHORT (fade); z<0 = laggard -> LONG."""
    return "SHORT" if z > 0 else "LONG"


def _sigma_bucket(z: float) -> str:
    az = abs(z)
    if az < 2.0:   return "<2.0"
    if az < 3.0:   return "[2.0,3.0)"
    if az < 4.0:   return "[3.0,4.0)"
    if az < 5.0:   return "[4.0,5.0)"
    return "5.0+"


def _trail_arm_px(entry_px: float, side: str) -> float:
    """+0.6% in the favorable direction (LONG up, SHORT down)."""
    factor = 1.0 + _TRAIL_ARM_PCT if side == "LONG" else 1.0 - _TRAIL_ARM_PCT
    return round(entry_px * factor, 4)


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

def _compute_filter_tag(symbol: str, side: str) -> tuple[str, str]:
    """Return (vwap_dev_signed_pct_str, filter_tag) for the row.

    Display-only — never raises; on any error returns ("", "WATCH"). The
    H-001 holdout (§10.4 strict) does not gate on this tag.
    """
    try:
        from pipeline.research.vwap_filter import compute_filter_tag
        dev, tag = compute_filter_tag(symbol, side)
        if dev is None:
            return "", tag
        return f"{dev * 100.0:.4f}", tag
    except Exception as exc:
        log.warning("vwap_filter failed for %s/%s: %s -- WATCH", symbol, side, exc)
        return "", "WATCH"


def _build_open_row(signal: dict, entry_px: float, atr_info: dict,
                    regime: str, today: str, now: str) -> dict:
    z = float(signal["z_score"])
    side = _side_from_z(z)
    ticker = signal["symbol"]
    sectoral_index = (signal.get("sectoral_index")
                      or signal.get("sector_index") or "UNKNOWN")
    atr_14 = atr_info.get("atr_14")
    stop_px = atr_info.get("stop_price")
    vwap_dev_str, filter_tag = _compute_filter_tag(ticker, side)
    return {
        "signal_id": f"BRK-{today}-{ticker}",
        "ticker": ticker, "date": today,
        "sigma_bucket": _sigma_bucket(z),
        "regime": regime, "sectoral_index": sectoral_index,
        "side": side, "classification": signal.get("classification", ""),
        "regime_gate_pass": str(regime != "NEUTRAL"),
        "entry_time": now, "entry_px": f"{entry_px:.4f}",
        "atr_14": "" if atr_14 is None else f"{atr_14:.4f}",
        "stop_px": "" if stop_px is None else f"{stop_px:.4f}",
        "trail_arm_px": f"{_trail_arm_px(entry_px, side):.4f}",
        "trail_dist_pct": f"{_TRAIL_DIST_PCT:.2f}",
        "exit_time": "", "exit_px": "", "exit_reason": "",
        "pnl_pct": "", "status": "OPEN",
        "vwap_dev_signed_pct": vwap_dev_str, "filter_tag": filter_tag,
    }


def cmd_open() -> int:
    today = _today_iso()
    doc = _load_breaks()
    if not doc:
        log.info("no breaks doc; nothing to open")
        return 0

    breaks = doc.get("breaks", []) or []
    filtered = _filter_signals(breaks)
    if not filtered:
        log.info("no signals at |z|>=%.1f sigma from %d total breaks",
                 _SIGMA_THRESHOLD, len(breaks))
        return 0

    seen: set[tuple[str, str]] = {(r["date"], r["ticker"]) for r in _read_recs()}
    by_ticker: dict[str, dict] = {}
    for s in filtered:
        sym = s["symbol"]
        if (today, sym) in seen:
            log.info("skip duplicate (date=%s, ticker=%s) -- already in CSV", today, sym)
            continue
        if sym in by_ticker:
            continue
        by_ticker[sym] = s

    if not by_ticker:
        log.info("no new signals to record")
        return 0

    syms = sorted(by_ticker.keys())
    log.info("fetching LTP for %d >=%.1f-sigma symbols", len(syms), _SIGMA_THRESHOLD)
    ltp = _fetch_ltp(syms)

    regime = _load_today_regime_zone()
    now = _now_iso()
    n_written = 0
    for sym in syms:
        signal = by_ticker[sym]
        if sym not in ltp:
            log.warning("no LTP for %s -- skipping", sym)
            continue
        entry_px = float(ltp[sym])
        side = _side_from_z(float(signal["z_score"]))
        try:
            atr_info = _compute_atr_stop(sym, side)
        except Exception as exc:
            log.warning("ATR stop failed for %s: %s -- using empty atr/stop", sym, exc)
            atr_info = {"atr_14": None, "stop_price": None,
                        "stop_pct": None, "stop_source": "fallback"}
        row = _build_open_row(signal, entry_px, atr_info, regime, today, now)
        _append_rec(row)
        n_written += 1
        log.info("OPEN  %-12s side=%-5s z=%.2f entry=%.2f stop=%s atr=%s",
                 sym, row["side"], float(signal["z_score"]),
                 entry_px, row["stop_px"] or "-", row["atr_14"] or "-")

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
        log.info("CLOSE %-12s side=%-5s entry=%.2f exit=%.2f pnl=%+.2f%%",
                 sym, r["side"], entry_px, exit_px, pnl)

    if n_closed == 0:
        log.info("no rows transitioned OPEN -> CLOSED")
        return 0
    _write_recs(rows)
    log.info("recommendations.csv: %d rows transitioned OPEN -> CLOSED", n_closed)
    return 0


# ---- CLI ------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.h_2026_04_26_001_paper",
        description="H-2026-04-26-001 sigma-break paper-trade driver "
                    "(spec: docs/superpowers/specs/"
                    "2026-04-26-sigma-break-mechanical-v1-design.md)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open", help="Append OPEN rows for today's >=2-sigma breaks (09:30 IST)")
    p_close = sub.add_parser("close", help="Close today's OPEN rows at LTP (14:30 IST)")
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
