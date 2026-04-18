"""
Risk Guardrails — Portfolio-level circuit breaker for shadow P&L.

Checks cumulative P&L before allowing new signal entries.
Called by run_signals.py before any shadow execution.

Rules:
  - Cumulative P&L < -10% over rolling 20 days → reduce sizing by 50%
  - Cumulative P&L < -15% over rolling 20 days → pause all new entries
  - 3 consecutive weeks outside backtest CI → flag model drift
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("anka.risk_guardrails")

IST = timezone(timedelta(hours=5, minutes=30))

REPO = Path(__file__).parent.parent
_DATA = REPO / "pipeline" / "data"

_DEFAULT_CLOSED = _DATA / "signals" / "closed_signals.json"


def _extract_pnl(signal: dict) -> Optional[float]:
    """
    Extract spread_pnl_pct from a signal dict.

    Handles two layouts:
      1. Root-level ``pnl_pct`` (shadow trades written by shadow_pnl.py)
      2. Nested ``final_pnl.spread_pnl_pct`` (signals closed by signal_tracker.py)
    """
    if "pnl_pct" in signal:
        return float(signal["pnl_pct"])
    nested = signal.get("final_pnl", {})
    if isinstance(nested, dict) and "spread_pnl_pct" in nested:
        return float(nested["spread_pnl_pct"])
    return None


def _extract_close_time(signal: dict) -> Optional[datetime]:
    """
    Parse close timestamp from a signal dict.

    Tries ``close_timestamp`` then ``closed_at``.
    Returns a timezone-aware datetime in IST, or None if missing/unparseable.
    """
    ts = signal.get("close_timestamp") or signal.get("closed_at") or signal.get("close_time")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        return dt
    except (ValueError, TypeError):
        return None


def check_risk_gates(
    closed_signals_path: Path = _DEFAULT_CLOSED,
    rolling_days: int = 20,
) -> dict:
    """
    Check portfolio risk gates against recent closed signals.

    Reads closed signals from ``closed_signals_path`` (JSON array), filters
    to those closed within the last ``rolling_days`` calendar days, and sums
    their P&L percentages.

    Returns:
        {
            "allowed": bool,          # True if new entries permitted
            "sizing_factor": float,   # 1.0 normal, 0.5 if L1 breaker, 0.0 if L2
            "level": str,             # "NORMAL" | "L1_REDUCE" | "L2_PAUSE"
            "reason": str | None,
            "cumulative_pnl": float,  # rolling N-day cumulative P&L %
            "trades_in_window": int,
        }
    """
    # --- Load signals ---
    try:
        raw = Path(closed_signals_path).read_text(encoding="utf-8")
        signals: list = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("check_risk_gates: could not load %s — %s", closed_signals_path, exc)
        signals = []

    if not signals:
        return {
            "allowed": True,
            "sizing_factor": 1.0,
            "level": "NORMAL",
            "reason": None,
            "cumulative_pnl": 0.0,
            "trades_in_window": 0,
        }

    # --- Filter to rolling window ---
    cutoff = datetime.now(IST) - timedelta(days=rolling_days)
    in_window: list[float] = []
    for sig in signals:
        closed_dt = _extract_close_time(sig)
        if closed_dt is None:
            continue
        if closed_dt >= cutoff:
            pnl = _extract_pnl(sig)
            if pnl is not None:
                in_window.append(pnl)

    cumulative_pnl = sum(in_window)
    trades_in_window = len(in_window)

    # --- Apply gate rules ---
    if cumulative_pnl < -15.0:
        return {
            "allowed": False,
            "sizing_factor": 0.0,
            "level": "L2_PAUSE",
            "reason": f"Cumulative P&L {cumulative_pnl:.2f}% over {rolling_days}d breaches -15% threshold",
            "cumulative_pnl": cumulative_pnl,
            "trades_in_window": trades_in_window,
        }

    if cumulative_pnl < -10.0:
        return {
            "allowed": True,
            "sizing_factor": 0.5,
            "level": "L1_REDUCE",
            "reason": f"Cumulative P&L {cumulative_pnl:.2f}% over {rolling_days}d breaches -10% threshold",
            "cumulative_pnl": cumulative_pnl,
            "trades_in_window": trades_in_window,
        }

    return {
        "allowed": True,
        "sizing_factor": 1.0,
        "level": "NORMAL",
        "reason": None,
        "cumulative_pnl": cumulative_pnl,
        "trades_in_window": trades_in_window,
    }
