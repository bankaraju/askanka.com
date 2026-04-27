"""Live shadow paper-trade ledger for the Scanner (TA) Top-10 paired shadow.

Scanner is a paper engine (exempt from 14:30 IST cutoff). Opens at 09:25 IST T+1
with Kite LTP, closes at 15:30 IST same session.

Schema doc: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §7.3
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date as _date
from pathlib import Path

from pipeline.research.phase_c_v5 import cost_model

log = logging.getLogger(__name__)

_LEDGER_PATH = Path("pipeline/data/research/scanner/live_paper_scanner_futures_ledger.json")
_DEFAULT_NOTIONAL = 50_000


def _load() -> list[dict]:
    """Return ledger contents or [] if file is missing or corrupt."""
    path = Path(_LEDGER_PATH)
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("corrupt scanner futures ledger, starting fresh: %s", exc)
        return []


def _save(ledger: list[dict]) -> None:
    """Atomic write via tempfile + os.replace."""
    target = Path(_LEDGER_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False,
        dir=target.parent, prefix=target.name + ".", suffix=".tmp",
    ) as tmp:
        tmp.write(json.dumps(ledger, indent=2))
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, target)


def _make_tag(n: int) -> str:
    return f"SCANNER_VERIFY_{_date.today().isoformat()}_{n}"


def record_opens(top_10_rows: list[dict], ltp: dict[str, float]) -> int:
    """Append OPEN entries for top_10_rows; idempotent on signal_id.

    Spec §7.3: each row must have signal_id, ticker, pattern_id, direction,
    composite_score, z_score, n_occurrences, win_rate, scan_date.
    Tickers absent from ltp are silently skipped (debug log).

    Returns: count of newly inserted rows.
    """
    if not top_10_rows:
        return 0
    ledger = _load()
    seen_ids = {e["signal_id"] for e in ledger}
    new = 0
    entry_date = _date.today().isoformat()
    for row in top_10_rows:
        signal_id = row.get("signal_id")
        if not signal_id:
            log.debug("record_opens: row missing signal_id, skipping: %s", row)
            continue
        if signal_id in seen_ids:
            log.debug("record_opens: idempotent skip %s", signal_id)
            continue
        ticker = row.get("ticker") or row.get("symbol")
        if not ticker:
            log.debug("record_opens: row missing ticker, skipping: %s", signal_id)
            continue
        if ticker not in ltp:
            log.debug("record_opens: no LTP for %s (signal_id=%s), skipping", ticker, signal_id)
            continue
        entry_px = float(ltp[ticker])
        side = "LONG" if str(row.get("direction", "LONG")).upper() == "LONG" else "SHORT"
        ledger.append({
            "tag": _make_tag(len(ledger) + 1),
            "signal_id": signal_id,
            "date": entry_date,
            "scan_date": str(row.get("scan_date", row.get("date", ""))),
            "ticker": ticker,
            "pattern_id": str(row.get("pattern_id", "")),
            "side": side,
            "composite_score": float(row.get("composite_score", 0.0)),
            "z_score": float(row.get("z_score", 0.0)),
            "n_occurrences": int(row.get("n_occurrences", 0)),
            "win_rate": float(row.get("win_rate", 0.0)),
            "entry_px": entry_px,
            "notional_inr": _DEFAULT_NOTIONAL,
            "status": "OPEN",
            "exit_px": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl_gross_inr": None,
            "pnl_net_inr": None,
        })
        seen_ids.add(signal_id)
        new += 1
    _save(ledger)
    return new


def close_at_1530(date_str: str, exit_prices: dict[str, float]) -> int:
    """Mechanically close all OPEN entries for date_str at supplied prices.

    Scanner closes at 15:30 IST (NOT 14:30 like Phase C). Spec §8.4.

    LONG P&L: (exit - entry) / entry * notional.
    SHORT P&L: (entry - exit) / entry * notional.
    Cost applied via phase_c_v5.cost_model (instrument=stock_future).

    Tickers with no exit price are skipped with a debug log.
    Returns: count of entries transitioned OPEN -> CLOSED.
    """
    ledger = _load()
    closed = 0
    for entry in ledger:
        if entry["date"] != date_str or entry["status"] != "OPEN":
            continue
        ticker = entry["ticker"]
        if ticker not in exit_prices:
            log.debug("close_at_1530: no exit price for %s on %s, skipping", ticker, date_str)
            continue
        exit_px = float(exit_prices[ticker])
        entry_px = float(entry["entry_px"])
        if entry_px <= 0:
            log.warning(
                "close_at_1530: non-positive entry_px for %s on %s, skipping", ticker, date_str
            )
            continue
        side = entry["side"]
        direction = 1 if side == "LONG" else -1
        signed_ret = (exit_px - entry_px) / entry_px * direction
        notional = float(entry["notional_inr"])
        pnl_gross = signed_ret * notional
        pnl_net = cost_model.apply_to_pnl(
            pnl_gross, instrument="stock_future", notional_inr=notional, side=side
        )
        entry.update({
            "status": "CLOSED",
            "exit_px": exit_px,
            "exit_time": f"{date_str} 15:30:00",
            "exit_reason": "TIME_STOP",
            "pnl_gross_inr": pnl_gross,
            "pnl_net_inr": pnl_net,
        })
        closed += 1
    _save(ledger)
    return closed
