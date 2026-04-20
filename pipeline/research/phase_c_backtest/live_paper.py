"""Live shadow paper-trade ledger for the F3 ongoing-confirmation leg.

A flat JSON ledger of OPPORTUNITY trades opened daily at signal time and
closed mechanically at 14:30 IST by :func:`close_at_1430`. The ledger is
forward-only (audit trail) — entries are never mutated except for the
single OPEN -> CLOSED transition.

Tag convention:
    ``PHASE_C_VERIFY_<date>_<n>`` where ``n`` is ``len(ledger) + 1`` at
    insertion time. This means tags are globally monotonic across calls
    rather than per-day. Acceptable for a forward-only audit log.

Idempotency:
    :func:`record_opens` skips entries with a matching ``(date, symbol)``
    pair already present in the ledger.
"""
from __future__ import annotations

import logging
from pathlib import Path
import json

import pandas as pd

from . import paths
from .cost_model import apply_to_pnl

log = logging.getLogger(__name__)

_LEDGER_PATH: Path = paths.CACHE_DIR / "live_paper_ledger.json"
_DEFAULT_NOTIONAL = 50_000
_DEFAULT_SLIPPAGE_BPS = 5.0
_DEFAULT_STOP_PCT = 0.02
_DEFAULT_TARGET_PCT = 0.01


def _load() -> list[dict]:
    """Return ledger contents or ``[]`` if file does not yet exist."""
    path = Path(_LEDGER_PATH)
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save(ledger: list[dict]) -> None:
    """Write the ledger to disk, creating parent dirs as needed."""
    path = Path(_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def _make_tag(date_str: str, n: int) -> str:
    return f"PHASE_C_VERIFY_{date_str}_{n}"


def record_opens(signals: pd.DataFrame) -> int:
    """Append OPEN entries for new signals; idempotent per ``(date, symbol)``.

    Args:
        signals: DataFrame with columns ``date, signal_time, symbol, side,
            z_score`` (required). Optional columns: ``entry_px``,
            ``stop_pct``, ``target_pct``. An empty DataFrame is a no-op
            (the existing ledger is preserved).

    Returns:
        Number of newly inserted entries.
    """
    ledger = _load()
    seen = {(e["date"], e["symbol"]) for e in ledger}
    new = 0
    for _, sig in signals.iterrows():
        key = (sig["date"], sig["symbol"])
        if key in seen:
            continue
        ledger.append({
            "tag": _make_tag(sig["date"], len(ledger) + 1),
            "date": sig["date"],
            "signal_time": sig["signal_time"],
            "symbol": sig["symbol"],
            "side": sig["side"],
            "z_score": float(sig["z_score"]),
            "entry_px": float(sig.get("entry_px", 0.0)),
            "stop_pct": float(sig.get("stop_pct", _DEFAULT_STOP_PCT)),
            "target_pct": float(sig.get("target_pct", _DEFAULT_TARGET_PCT)),
            "notional_inr": _DEFAULT_NOTIONAL,
            "status": "OPEN",
            "exit_px": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl_gross_inr": None,
            "pnl_net_inr": None,
        })
        seen.add(key)
        new += 1
    _save(ledger)
    return new


def close_at_1430(date_str: str, exit_prices: dict[str, float]) -> int:
    """Mechanically close all OPEN entries for ``date_str`` at supplied prices.

    LONG P&L: ``(exit - entry) / entry * notional``.
    SHORT P&L: ``(entry - exit) / entry * notional`` (signed via direction).
    Round-trip cost is applied via
    :func:`pipeline.research.phase_c_backtest.cost_model.apply_to_pnl`.

    Symbols with no entry in ``exit_prices`` are skipped silently and a
    debug-level message is logged so an operator can audit gaps.

    Args:
        date_str: The trade date (``YYYY-MM-DD``) whose OPEN entries to close.
        exit_prices: Mapping ``{symbol: 14:30 IST exit price}``.

    Returns:
        Number of entries transitioned from OPEN to CLOSED.
    """
    ledger = _load()
    closed = 0
    for entry in ledger:
        if entry["date"] != date_str or entry["status"] != "OPEN":
            continue
        sym = entry["symbol"]
        if sym not in exit_prices:
            log.debug("close_at_1430: no exit price for %s on %s, skipping", sym, date_str)
            continue
        exit_px = float(exit_prices[sym])
        entry_px = float(entry["entry_px"])
        if entry_px <= 0:
            log.warning("close_at_1430: non-positive entry_px for %s on %s, skipping", sym, date_str)
            continue
        side = entry["side"]
        direction = 1 if side == "LONG" else -1
        signed_ret = (exit_px - entry_px) / entry_px * direction
        pnl_gross = signed_ret * entry["notional_inr"]
        pnl_net = apply_to_pnl(pnl_gross, entry["notional_inr"], side, _DEFAULT_SLIPPAGE_BPS)
        entry.update({
            "status": "CLOSED",
            "exit_px": exit_px,
            "exit_time": f"{date_str} 14:30:00",
            "exit_reason": "TIME_STOP",
            "pnl_gross_inr": pnl_gross,
            "pnl_net_inr": pnl_net,
        })
        closed += 1
    _save(ledger)
    return closed
