"""H-2026-05-01-earnings-drift-long-v1 — live OPEN/CLOSE entrypoint.

PURPOSE
-------
- `open_today()`: at T-1 14:25 IST, query the FROZEN signal generator for any
  qualified LONG candidates whose event_date is the next trading day, fetch Kite
  LTP, and write OPEN rows to recommendations.csv.
- `close_today()`: at 14:30 IST every trading day, scan recommendations.csv for
  OPEN rows where (entry_date + 5 trading days) <= today, fetch Kite LTP, and
  CLOSE at the LTP. ATR×2 per-leg stops are checked at every minute via the
  separate intraday loop (not implemented here at v1 — TIME_STOP only).

CALLED BY
---------
- AnkaEarningsDriftOpen scheduled task at 14:25 IST trading days
- AnkaEarningsDriftClose scheduled task at 14:30 IST trading days

This file matches the kill-switch regex (`*_engine.py`); registry row required.

Spec: docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
Audit: docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "pipeline" / "data" / "research" / "h_2026_05_01_earnings_drift_long" / "recommendations.csv"
HOLD_TRADING_DAYS = 5

LEDGER_COLS = [
    "id", "status", "symbol", "event_date", "entry_date", "exit_date",
    "side", "entry_price", "exit_price", "exit_reason",
    "volume_z", "short_mom_bps", "realized_vol_21d_pct", "regime", "atr_14_pct",
    "gross_bps", "net_s1_bps",
    "open_ts_ist", "close_ts_ist", "spec_version",
]

SPEC_VERSION = "v1.0"

from pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_signal_generator import (
    SignalCandidate,
    generate_signals_for_entry_date,
    signal_summary_string,
)


def _ist_now() -> datetime:
    """Current IST timestamp (naive but conventional UTC+5:30 anchor)."""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


def _read_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    with open(LEDGER_PATH, newline="") as f:
        return list(csv.DictReader(f))


def _write_ledger(rows: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in LEDGER_COLS})


def _next_id(rows: list[dict]) -> int:
    if not rows:
        return 1
    ids = [int(r["id"]) for r in rows if r.get("id")]
    return max(ids, default=0) + 1


def _kite_ltp(symbol: str) -> float | None:
    """Best-effort Kite LTP fetch. Returns None on any failure."""
    try:
        from pipeline.kite_client import KiteClient
        kc = KiteClient()
        return float(kc.get_ltp(symbol))
    except Exception as e:
        print(f"  [Kite LTP error for {symbol}: {e}]", file=sys.stderr)
        return None


def open_today(entry_date: date | None = None) -> int:
    """Run signal generator + write OPEN ledger rows. Returns count opened."""
    ed = entry_date or _ist_now().date()
    print(f"\n[earnings_drift_engine.open_today] entry_date={ed}")

    cands = generate_signals_for_entry_date(ed)
    print(f"  qualified candidates: {len(cands)}")
    if not cands:
        return 0

    rows = _read_ledger()
    next_id = _next_id(rows)

    # First-touch dedup: per (symbol, event_date) — at most one OPEN per name per quarter
    existing_keys = set((r["symbol"], r["event_date"]) for r in rows
                        if r.get("status") in ("OPEN", "CLOSED"))

    opened = 0
    for c in cands:
        key = (c.symbol, str(c.event_date.date()))
        if key in existing_keys:
            print(f"  SKIP (dedup) {c.symbol} {c.event_date.date()}")
            continue

        ltp = _kite_ltp(c.symbol)
        if ltp is None or ltp <= 0:
            print(f"  SKIP (no LTP) {c.symbol}")
            continue

        new_row = {
            "id": next_id,
            "status": "OPEN",
            "symbol": c.symbol,
            "event_date": str(c.event_date.date()),
            "entry_date": str(c.entry_date.date()),
            "exit_date": "",
            "side": c.side,
            "entry_price": f"{ltp:.2f}",
            "exit_price": "",
            "exit_reason": "",
            "volume_z": f"{c.volume_z:.4f}",
            "short_mom_bps": f"{c.short_mom_bps:.2f}",
            "realized_vol_21d_pct": f"{c.realized_vol_21d_pct:.2f}",
            "regime": c.regime,
            "atr_14_pct": f"{c.atr_14_pct:.6f}",
            "gross_bps": "",
            "net_s1_bps": "",
            "open_ts_ist": _ist_now().strftime("%Y-%m-%d %H:%M:%S"),
            "close_ts_ist": "",
            "spec_version": SPEC_VERSION,
        }
        rows.append(new_row)
        next_id += 1
        opened += 1
        print(f"  OPEN id={new_row['id']} {signal_summary_string(c)} entry_ltp={ltp:.2f}")

    _write_ledger(rows)
    print(f"  total opened: {opened}")
    return opened


def _add_trading_days(d: date, n: int) -> date:
    """Add n trading days using FNO daily bars as the trading-day calendar."""
    from pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_signal_generator import (
        _read_daily,
    )
    # Use HDFCBANK as a reliable trading-day reference
    daily = _read_daily("HDFCBANK")
    if daily is None or daily.empty:
        # Fallback to weekday math if no daily data available
        result = d
        added = 0
        while added < n:
            result = result + timedelta(days=1)
            if result.weekday() < 5:
                added += 1
        return result
    dts = pd.to_datetime(daily["Date"]).dt.date
    after = sorted([x for x in dts if x > d])
    if len(after) < n:
        # Asked for too many days into the future — use last available + business-day fallback
        last_known = after[-1] if after else d
        remainder = n - len(after)
        result = last_known
        added = 0
        while added < remainder:
            result = result + timedelta(days=1)
            if result.weekday() < 5:
                added += 1
        return result
    return after[n - 1]


def close_today(today: date | None = None) -> int:
    """Mechanical TIME_STOP close at 14:30 IST. Returns count closed."""
    today = today or _ist_now().date()
    print(f"\n[earnings_drift_engine.close_today] today={today}")

    rows = _read_ledger()
    if not rows:
        print("  no rows")
        return 0

    closed = 0
    for r in rows:
        if r.get("status") != "OPEN":
            continue
        entry_d = datetime.strptime(r["entry_date"], "%Y-%m-%d").date()
        target_close_d = _add_trading_days(entry_d, HOLD_TRADING_DAYS)
        if today < target_close_d:
            continue

        symbol = r["symbol"]
        ltp = _kite_ltp(symbol)
        if ltp is None or ltp <= 0:
            print(f"  SKIP CLOSE (no LTP) {symbol} id={r['id']}")
            continue

        entry_price = float(r["entry_price"])
        gross_bps = (ltp / entry_price - 1.0) * 10_000.0
        net_s1_bps = gross_bps - 20.0

        r["status"] = "CLOSED"
        r["exit_date"] = str(today)
        r["exit_price"] = f"{ltp:.2f}"
        r["exit_reason"] = "time_stop"
        r["gross_bps"] = f"{gross_bps:.2f}"
        r["net_s1_bps"] = f"{net_s1_bps:.2f}"
        r["close_ts_ist"] = _ist_now().strftime("%Y-%m-%d %H:%M:%S")
        closed += 1
        print(f"  CLOSE id={r['id']} {symbol} entry={entry_price:.2f} exit={ltp:.2f} gross={gross_bps:+.0f} bps")

    _write_ledger(rows)
    print(f"  total closed: {closed}")
    return closed


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("open", "close"):
        print("Usage: python -m pipeline.research.h_2026_05_01_earnings_drift_long.earnings_drift_engine {open|close} [YYYY-MM-DD]")
        sys.exit(1)
    mode = sys.argv[1]
    d = datetime.strptime(sys.argv[2], "%Y-%m-%d").date() if len(sys.argv) > 2 else None
    if mode == "open":
        open_today(d)
    elif mode == "close":
        close_today(d)


if __name__ == "__main__":
    main()
