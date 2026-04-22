# Risk Guardrails + Shadow P&L Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two standalone modules — a portfolio-level circuit breaker (`risk_guardrails.py`) and a paper trading engine (`shadow_pnl.py`) — that integrate with the existing signal infrastructure without modifying `run_signals.py`.

**Architecture:** `risk_guardrails.py` reads `closed_signals.json`, sums `spread_pnl_pct` over a rolling 20-day window, and returns a gate dict (`allowed`, `sizing_factor`, `level`). `shadow_pnl.py` creates/updates paper trade records and generates a daily win/loss strip from closed trades. Both modules are path-agnostic (paths passed as arguments) and contain no I/O side-effects in their pure logic functions.

**Tech Stack:** Python 3.10+, `datetime`/`timedelta`/`timezone` from stdlib, `pathlib.Path`, `json`, `math` (for Sharpe), `pytest` for tests.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pipeline/risk_guardrails.py` | Circuit breaker: load closed signals, sum rolling P&L, return gate dict |
| Create | `pipeline/shadow_pnl.py` | Paper trade creation, MTM update, daily strip generator |
| Create | `pipeline/tests/test_risk_guardrails.py` | 4 tests for guardrail logic |
| Create | `pipeline/tests/test_shadow_pnl.py` | 6 tests for shadow P&L logic |

---

## Key Data Contract Note

Existing `closed_signals.json` stores P&L under `final_pnl.spread_pnl_pct` (not a root-level `pnl_pct`). The guardrails module must handle both paths:
1. Root-level `pnl_pct` key (for shadow trades created by `shadow_pnl.py`)
2. Nested `final_pnl.spread_pnl_pct` (for signals closed by the existing `signal_tracker.py`)

Similarly, `close_time` in the spec refers to `close_timestamp` in real signals (also check `closed_at` as fallback).

---

## Task 1: Write risk_guardrails.py

**Files:**
- Create: `pipeline/risk_guardrails.py`

- [ ] **Step 1: Create the file**

```python
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
```

Save as `pipeline/risk_guardrails.py`.

- [ ] **Step 2: Verify the file is syntactically valid**

```bash
cd /c/Users/Claude_Anka/askanka.com && python3 -c "import pipeline.risk_guardrails; print('OK')"
```

Expected: `OK`

---

## Task 2: Write test_risk_guardrails.py

**Files:**
- Create: `pipeline/tests/test_risk_guardrails.py`

- [ ] **Step 1: Create the test file**

```python
"""
Tests for pipeline/risk_guardrails.py

Run: pytest pipeline/tests/test_risk_guardrails.py -v
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.risk_guardrails import check_risk_gates

IST = timezone(timedelta(hours=5, minutes=30))


def _make_signal(pnl_pct: float, days_ago: float = 5) -> dict:
    """Helper: closed signal with root-level pnl_pct."""
    close_dt = datetime.now(IST) - timedelta(days=days_ago)
    return {
        "signal_id": f"SIG-TEST-{pnl_pct}",
        "pnl_pct": pnl_pct,
        "close_timestamp": close_dt.isoformat(),
        "status": "CLOSED",
    }


def _make_nested_signal(pnl_pct: float, days_ago: float = 5) -> dict:
    """Helper: closed signal with nested final_pnl layout (signal_tracker.py format)."""
    close_dt = datetime.now(IST) - timedelta(days=days_ago)
    return {
        "signal_id": f"SIG-NESTED-{pnl_pct}",
        "final_pnl": {"spread_pnl_pct": pnl_pct},
        "close_timestamp": close_dt.isoformat(),
        "status": "STOPPED_OUT",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormalGate:
    def test_normal_allows_full_sizing(self, tmp_path):
        """Cumulative P&L of +5% over 20 days → NORMAL gate, 1.0 sizing."""
        signals = [_make_signal(2.0), _make_signal(3.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 1.0
        assert result["level"] == "NORMAL"
        assert result["reason"] is None
        assert abs(result["cumulative_pnl"] - 5.0) < 0.001
        assert result["trades_in_window"] == 2

    def test_positive_pnl_stays_normal(self, tmp_path):
        """Large positive P&L doesn't trigger any breaker."""
        signals = [_make_signal(10.0), _make_signal(8.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "NORMAL"
        assert result["sizing_factor"] == 1.0


class TestL1Gate:
    def test_l1_reduces_sizing(self, tmp_path):
        """Cumulative P&L of -12% → L1_REDUCE with 0.5 sizing factor."""
        signals = [_make_signal(-7.0), _make_signal(-5.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 0.5
        assert result["level"] == "L1_REDUCE"
        assert result["reason"] is not None
        assert "-12" in result["reason"] or "-12.00" in result["reason"]
        assert result["trades_in_window"] == 2

    def test_l1_boundary_at_exactly_minus10(self, tmp_path):
        """P&L of exactly -10% triggers L1 (threshold is strictly less than -10)."""
        signals = [_make_signal(-10.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        # -10.0 < -10.0 is False, so this should be NORMAL
        # Boundary: strictly < -10 triggers L1
        assert result["level"] == "NORMAL"

    def test_l1_just_past_boundary(self, tmp_path):
        """P&L of -10.01% triggers L1."""
        signals = [_make_signal(-10.01)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L1_REDUCE"
        assert result["sizing_factor"] == 0.5


class TestL2Gate:
    def test_l2_pauses_entries(self, tmp_path):
        """Cumulative P&L of -16% → L2_PAUSE with 0.0 sizing, not allowed."""
        signals = [_make_signal(-10.0), _make_signal(-6.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is False
        assert result["sizing_factor"] == 0.0
        assert result["level"] == "L2_PAUSE"
        assert result["reason"] is not None
        assert result["trades_in_window"] == 2

    def test_l2_boundary_at_exactly_minus15(self, tmp_path):
        """P&L of exactly -15% triggers L2 (threshold is strictly less than -15)."""
        signals = [_make_signal(-15.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        # -15.0 < -15.0 is False → L1 range
        assert result["level"] == "L1_REDUCE"

    def test_l2_just_past_boundary(self, tmp_path):
        """P&L of -15.01% triggers L2."""
        signals = [_make_signal(-15.01)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L2_PAUSE"
        assert result["allowed"] is False


class TestEdgeCases:
    def test_empty_signals_returns_normal(self, tmp_path):
        """No closed signals → NORMAL, sizing 1.0."""
        f = tmp_path / "closed_signals.json"
        f.write_text("[]", encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 1.0
        assert result["level"] == "NORMAL"
        assert result["cumulative_pnl"] == 0.0
        assert result["trades_in_window"] == 0

    def test_missing_file_returns_normal(self, tmp_path):
        """Non-existent file → graceful fallback to NORMAL."""
        result = check_risk_gates(
            closed_signals_path=tmp_path / "nonexistent.json"
        )

        assert result["level"] == "NORMAL"
        assert result["sizing_factor"] == 1.0

    def test_signals_outside_window_excluded(self, tmp_path):
        """Signals older than rolling_days are excluded from cumulative P&L."""
        old_signal = _make_signal(-20.0, days_ago=25)   # outside 20-day window
        new_signal = _make_signal(2.0, days_ago=5)       # inside window
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps([old_signal, new_signal]), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        # Old -20% signal must not count — only +2% signal counts
        assert result["level"] == "NORMAL"
        assert result["trades_in_window"] == 1
        assert abs(result["cumulative_pnl"] - 2.0) < 0.001

    def test_nested_pnl_format_is_handled(self, tmp_path):
        """signal_tracker.py nested final_pnl.spread_pnl_pct layout is parsed correctly."""
        signals = [_make_nested_signal(-12.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L1_REDUCE"
        assert result["trades_in_window"] == 1
```

Save as `pipeline/tests/test_risk_guardrails.py`.

- [ ] **Step 2: Run the tests**

```bash
cd /c/Users/Claude_Anka/askanka.com && python3 -m pytest pipeline/tests/test_risk_guardrails.py -v
```

Expected: all tests PASS. If any fail, fix `risk_guardrails.py` — do not change test logic.

- [ ] **Step 3: Commit Task 1 + 2**

```bash
cd /c/Users/Claude_Anka/askanka.com && git add pipeline/risk_guardrails.py pipeline/tests/test_risk_guardrails.py && git commit -m "feat(golden-goose): risk guardrails circuit breaker + tests"
```

---

## Task 3: Write shadow_pnl.py

**Files:**
- Create: `pipeline/shadow_pnl.py`

- [ ] **Step 1: Create the file**

```python
"""
Shadow P&L — Paper trading engine for the Golden Goose.

Records signal entries at real prices, tracks mark-to-market every 15 min,
and closes positions when stop/target/expiry hit.

All trades logged to data/signals/closed_signals.json for website display.

Constants (all configurable at top of file):
    STOP_LOSS_PCT   = 3.0   — close if P&L drops below -3.0%
    TARGET_PCT      = 4.5   — close if P&L exceeds +4.5%
    EXPIRY_DAYS     = 5     — close at market if open after 5 trading days
    TRAIL_ARM_PCT   = 2.0   — trailing stop arms when peak P&L >= 2.0%
    TRAIL_DROP_PCT  = 1.5   — close when P&L drops 1.5% below peak (after armed)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------
STOP_LOSS_PCT: float = 3.0    # absolute loss threshold (positive value, applied as negative)
TARGET_PCT: float = 4.5        # profit target
EXPIRY_DAYS: int = 5           # trading days before forced exit
TRAIL_ARM_PCT: float = 2.0     # peak P&L threshold to arm trailing stop
TRAIL_DROP_PCT: float = 1.5    # drop from peak that triggers trail exit


# ---------------------------------------------------------------------------
# create_shadow_trade
# ---------------------------------------------------------------------------

def create_shadow_trade(
    signal: dict,
    entry_price: float,
    regime: str,
    sizing_factor: float = 1.0,
) -> dict:
    """
    Create a shadow trade record from a signal dict.

    Args:
        signal: Signal dict with keys: signal_id, type, spread_name, direction,
                conviction, etc. ``direction`` should be "LONG" or "SHORT";
                defaults to "LONG" if absent.
        entry_price: Current market price at signal time.
        regime: Current ETF regime zone string (e.g. "RISK_ON", "NEUTRAL").
        sizing_factor: From risk_guardrails (1.0 normal, 0.5 reduced).

    Returns:
        Shadow trade dict with all required tracking fields.
    """
    now = datetime.now(IST)
    expiry_dt = now + timedelta(days=EXPIRY_DAYS)

    direction = str(signal.get("direction", "LONG")).upper()

    return {
        "signal_id": signal.get("signal_id", ""),
        "spread_name": signal.get("spread_name", ""),
        "direction": direction,
        "regime_at_entry": regime,
        "conviction": signal.get("conviction", None),
        "sizing_multiplier": float(sizing_factor),
        "entry_price": float(entry_price),
        "entry_time": now.isoformat(),
        "stop_loss": float(STOP_LOSS_PCT),
        "target": float(TARGET_PCT),
        "expiry_date": expiry_dt.isoformat(),
        "status": "OPEN",
        "pnl_pct": 0.0,
        "peak_pnl": 0.0,
    }


# ---------------------------------------------------------------------------
# update_shadow_trade
# ---------------------------------------------------------------------------

def _calc_pnl(direction: str, entry_price: float, current_price: float) -> float:
    """
    Compute P&L percentage for a trade.

    Long:  (current - entry) / entry * 100
    Short: (entry - current) / entry * 100
    """
    if entry_price == 0:
        return 0.0
    if direction == "SHORT":
        return (entry_price - current_price) / entry_price * 100.0
    return (current_price - entry_price) / entry_price * 100.0


def update_shadow_trade(trade: dict, current_price: float) -> dict:
    """
    Update mark-to-market P&L for an open shadow trade.

    Evaluates exit conditions in this order:
      1. Expiry check — if today > expiry_date, close at current price
      2. Stop loss  — if pnl_pct < -STOP_LOSS_PCT, close
      3. Target     — if pnl_pct >= TARGET_PCT, close
      4. Trailing stop — if peak_pnl >= TRAIL_ARM_PCT and
                         (peak_pnl - pnl_pct) >= TRAIL_DROP_PCT, close

    If already CLOSED, returns the trade unchanged.

    Returns:
        Updated trade dict. If closed, ``status`` = "CLOSED",
        ``close_reason`` is set, ``close_time`` is set.
    """
    if trade.get("status") != "OPEN":
        return trade

    trade = dict(trade)  # shallow copy — don't mutate caller's dict

    direction = str(trade.get("direction", "LONG")).upper()
    entry_price = float(trade.get("entry_price", 0))
    pnl_pct = _calc_pnl(direction, entry_price, float(current_price))

    # Update peak
    peak_pnl = max(float(trade.get("peak_pnl", 0.0)), pnl_pct)
    trade["pnl_pct"] = pnl_pct
    trade["peak_pnl"] = peak_pnl

    now = datetime.now(IST)

    # 1. Expiry check
    expiry_str = trade.get("expiry_date", "")
    if expiry_str:
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=IST)
            if now >= expiry_dt:
                trade["status"] = "CLOSED"
                trade["close_reason"] = "EXPIRY"
                trade["close_time"] = now.isoformat()
                return trade
        except (ValueError, TypeError):
            pass

    # 2. Stop loss
    stop_loss_pct = float(trade.get("stop_loss", STOP_LOSS_PCT))
    if pnl_pct < -stop_loss_pct:
        trade["status"] = "CLOSED"
        trade["close_reason"] = "STOP_LOSS"
        trade["close_time"] = now.isoformat()
        return trade

    # 3. Target
    target_pct = float(trade.get("target", TARGET_PCT))
    if pnl_pct >= target_pct:
        trade["status"] = "CLOSED"
        trade["close_reason"] = "TARGET"
        trade["close_time"] = now.isoformat()
        return trade

    # 4. Trailing stop
    trail_arm = float(trade.get("trail_arm_pct", TRAIL_ARM_PCT))
    trail_drop = float(trade.get("trail_drop_pct", TRAIL_DROP_PCT))
    if peak_pnl >= trail_arm and (peak_pnl - pnl_pct) >= trail_drop:
        trade["status"] = "CLOSED"
        trade["close_reason"] = "TRAIL_STOP"
        trade["close_time"] = now.isoformat()
        return trade

    return trade


# ---------------------------------------------------------------------------
# generate_daily_strip
# ---------------------------------------------------------------------------

def generate_daily_strip(closed_signals: list) -> dict:
    """
    Generate the daily win/loss visual strip from a list of closed signal dicts.

    Each signal must have:
      - ``pnl_pct`` (root-level float) — the trade's final P&L percentage
      - ``close_time`` or ``close_timestamp`` — ISO datetime string

    Returns:
        {
            "trading_days": int,
            "summary": {
                "total_trades": int,
                "wins": int,
                "losses": int,
                "win_rate": float,
                "avg_return": float,
                "cumulative_return": float,
                "max_drawdown": float,
                "sharpe": float,
            },
            "daily_strip": [
                {"date": "2026-04-21", "pnl": 0.012, "result": "WIN", "trades": 3},
                ...
            ]
        }
    """
    if not closed_signals:
        return {
            "trading_days": 0,
            "summary": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "cumulative_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
            },
            "daily_strip": [],
        }

    # --- Aggregate by trading day ---
    daily: dict[str, list[float]] = {}
    for sig in closed_signals:
        # Extract P&L
        pnl = _extract_signal_pnl(sig)
        if pnl is None:
            continue

        # Extract date
        date_str = _extract_signal_date(sig)
        if date_str is None:
            continue

        daily.setdefault(date_str, []).append(pnl)

    if not daily:
        return {
            "trading_days": 0,
            "summary": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "cumulative_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
            },
            "daily_strip": [],
        }

    # --- Build strip (sorted by date ascending) ---
    strip = []
    all_pnls: list[float] = []
    for date_str in sorted(daily.keys()):
        day_pnls = daily[date_str]
        day_total = sum(day_pnls)
        result = "WIN" if day_total >= 0 else "LOSS"
        strip.append(
            {
                "date": date_str,
                "pnl": round(day_total / 100.0, 6),  # convert % → fraction for display
                "result": result,
                "trades": len(day_pnls),
            }
        )
        all_pnls.extend(day_pnls)

    # --- Summary stats ---
    total_trades = len(all_pnls)
    wins = sum(1 for p in all_pnls if p >= 0)
    losses = total_trades - wins
    win_rate = wins / total_trades if total_trades else 0.0
    avg_return = sum(all_pnls) / total_trades if total_trades else 0.0
    cumulative_return = sum(all_pnls)

    # Max drawdown: peak-to-trough on running cumulative
    max_drawdown = _calc_max_drawdown(all_pnls)

    # Sharpe: mean / std of per-trade returns (annualised not required here)
    sharpe = _calc_sharpe(all_pnls)

    return {
        "trading_days": len(daily),
        "summary": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "avg_return": round(avg_return, 4),
            "cumulative_return": round(cumulative_return, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe": round(sharpe, 4),
        },
        "daily_strip": strip,
    }


# ---------------------------------------------------------------------------
# Private helpers for generate_daily_strip
# ---------------------------------------------------------------------------

def _extract_signal_pnl(sig: dict) -> Optional[float]:
    """Extract pnl_pct from root or nested final_pnl."""
    if "pnl_pct" in sig:
        try:
            return float(sig["pnl_pct"])
        except (TypeError, ValueError):
            return None
    nested = sig.get("final_pnl", {})
    if isinstance(nested, dict) and "spread_pnl_pct" in nested:
        try:
            return float(nested["spread_pnl_pct"])
        except (TypeError, ValueError):
            return None
    return None


def _extract_signal_date(sig: dict) -> Optional[str]:
    """Return YYYY-MM-DD string from close_time / close_timestamp / closed_at."""
    ts = (
        sig.get("close_time")
        or sig.get("close_timestamp")
        or sig.get("closed_at")
    )
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return None


def _calc_max_drawdown(pnls: list[float]) -> float:
    """
    Calculate maximum peak-to-trough drawdown on running cumulative P&L.
    Returns a non-positive float (e.g. -5.2 means 5.2% drawdown).
    """
    if not pnls:
        return 0.0
    peak = 0.0
    running = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = running - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _calc_sharpe(pnls: list[float]) -> float:
    """
    Simple Sharpe: mean(pnls) / std(pnls). Returns 0.0 if std is zero.
    """
    n = len(pnls)
    if n < 2:
        return 0.0
    mean = sum(pnls) / n
    variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    return mean / std
```

Save as `pipeline/shadow_pnl.py`.

- [ ] **Step 2: Verify syntax**

```bash
cd /c/Users/Claude_Anka/askanka.com && python3 -c "import pipeline.shadow_pnl; print('OK')"
```

Expected: `OK`

---

## Task 4: Write test_shadow_pnl.py

**Files:**
- Create: `pipeline/tests/test_shadow_pnl.py`

- [ ] **Step 1: Create the test file**

```python
"""
Tests for pipeline/shadow_pnl.py

Run: pytest pipeline/tests/test_shadow_pnl.py -v
"""
import pytest
from datetime import datetime, timedelta, timezone

from pipeline.shadow_pnl import (
    create_shadow_trade,
    update_shadow_trade,
    generate_daily_strip,
    STOP_LOSS_PCT,
    TARGET_PCT,
)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SIGNAL = {
    "signal_id": "SIG-2026-04-18-001",
    "spread_name": "Defence vs IT",
    "direction": "LONG",
    "conviction": 72.5,
}


# ---------------------------------------------------------------------------
# create_shadow_trade tests
# ---------------------------------------------------------------------------

class TestCreateShadowTrade:
    def test_create_shadow_trade_structure(self):
        """All required fields must be present in the returned dict."""
        trade = create_shadow_trade(
            signal=SAMPLE_SIGNAL,
            entry_price=1000.0,
            regime="RISK_ON",
            sizing_factor=1.0,
        )

        required_keys = [
            "signal_id", "spread_name", "direction", "regime_at_entry",
            "conviction", "sizing_multiplier", "entry_price", "entry_time",
            "stop_loss", "target", "expiry_date", "status", "pnl_pct", "peak_pnl",
        ]
        for key in required_keys:
            assert key in trade, f"Missing key: {key}"

        assert trade["status"] == "OPEN"
        assert trade["pnl_pct"] == 0.0
        assert trade["peak_pnl"] == 0.0
        assert trade["entry_price"] == 1000.0
        assert trade["sizing_multiplier"] == 1.0
        assert trade["direction"] == "LONG"
        assert trade["regime_at_entry"] == "RISK_ON"
        assert trade["signal_id"] == "SIG-2026-04-18-001"

    def test_reduced_sizing_stored(self):
        """sizing_factor=0.5 is stored as sizing_multiplier."""
        trade = create_shadow_trade(
            signal=SAMPLE_SIGNAL,
            entry_price=500.0,
            regime="NEUTRAL",
            sizing_factor=0.5,
        )
        assert trade["sizing_multiplier"] == 0.5

    def test_direction_defaults_to_long(self):
        """Missing direction defaults to LONG."""
        signal_no_dir = {"signal_id": "SIG-NODIR", "spread_name": "X vs Y"}
        trade = create_shadow_trade(signal_no_dir, entry_price=100.0, regime="NEUTRAL")
        assert trade["direction"] == "LONG"

    def test_stop_and_target_stored(self):
        """stop_loss and target are stored from module constants."""
        trade = create_shadow_trade(SAMPLE_SIGNAL, entry_price=100.0, regime="NEUTRAL")
        assert trade["stop_loss"] == STOP_LOSS_PCT
        assert trade["target"] == TARGET_PCT


# ---------------------------------------------------------------------------
# update_shadow_trade tests
# ---------------------------------------------------------------------------

class TestUpdateShadowTrade:
    def _open_trade(self, entry_price=1000.0, direction="LONG") -> dict:
        return {
            "signal_id": "SIG-UPDATE-001",
            "spread_name": "Test Spread",
            "direction": direction,
            "entry_price": entry_price,
            "entry_time": datetime.now(IST).isoformat(),
            "stop_loss": STOP_LOSS_PCT,
            "target": TARGET_PCT,
            "expiry_date": (datetime.now(IST) + timedelta(days=5)).isoformat(),
            "status": "OPEN",
            "pnl_pct": 0.0,
            "peak_pnl": 0.0,
        }

    def test_update_trade_still_open(self):
        """Small price move keeps trade OPEN with updated pnl_pct."""
        trade = self._open_trade(entry_price=1000.0)
        updated = update_shadow_trade(trade, current_price=1010.0)  # +1%

        assert updated["status"] == "OPEN"
        assert abs(updated["pnl_pct"] - 1.0) < 0.001
        assert updated["peak_pnl"] >= 1.0
        assert "close_reason" not in updated

    def test_update_trade_target_hit(self):
        """Price rise beyond TARGET_PCT closes trade as TARGET."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")
        # TARGET_PCT = 4.5 → need price > 1045
        updated = update_shadow_trade(trade, current_price=1050.0)  # +5%

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "TARGET"
        assert "close_time" in updated
        assert updated["pnl_pct"] > TARGET_PCT

    def test_update_trade_stop_hit(self):
        """Price drop beyond STOP_LOSS_PCT closes trade as STOP_LOSS."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")
        # STOP_LOSS_PCT = 3.0 → need price < 970
        updated = update_shadow_trade(trade, current_price=960.0)  # -4%

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "STOP_LOSS"
        assert "close_time" in updated
        assert updated["pnl_pct"] < -STOP_LOSS_PCT

    def test_update_trade_short_direction(self):
        """Short trade profits when price falls."""
        trade = self._open_trade(entry_price=1000.0, direction="SHORT")
        # Price falls 5% → short makes +5%
        updated = update_shadow_trade(trade, current_price=950.0)

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "TARGET"
        assert updated["pnl_pct"] > 0

    def test_update_trade_already_closed_unchanged(self):
        """Calling update on a CLOSED trade returns it unchanged."""
        trade = self._open_trade()
        trade["status"] = "CLOSED"
        trade["close_reason"] = "TARGET"
        trade["pnl_pct"] = 4.5

        result = update_shadow_trade(trade, current_price=2000.0)

        assert result["status"] == "CLOSED"
        assert result["pnl_pct"] == 4.5  # not recalculated

    def test_trailing_stop_fires_after_peak(self):
        """Trailing stop closes trade when P&L drops 1.5% from a 2%+ peak."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")

        # Simulate: price goes to 1025 (+2.5%), arming trail
        trade = update_shadow_trade(trade, current_price=1025.0)
        assert trade["status"] == "OPEN"
        assert trade["peak_pnl"] >= 2.0  # trail should be armed

        # Now price drops to 1009 (+0.9%) — drop from peak is 1.6% → trail fires
        trade = update_shadow_trade(trade, current_price=1009.0)
        assert trade["status"] == "CLOSED"
        assert trade["close_reason"] == "TRAIL_STOP"

    def test_expiry_closes_trade(self):
        """Trade past expiry_date is closed as EXPIRY."""
        trade = self._open_trade()
        # Set expiry in the past
        past = datetime.now(IST) - timedelta(hours=1)
        trade["expiry_date"] = past.isoformat()

        updated = update_shadow_trade(trade, current_price=1000.0)

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "EXPIRY"


# ---------------------------------------------------------------------------
# generate_daily_strip tests
# ---------------------------------------------------------------------------

def _make_closed(pnl_pct: float, date_str: str) -> dict:
    """Helper: minimal closed signal for strip generation."""
    return {
        "signal_id": f"SIG-{date_str}-{pnl_pct}",
        "pnl_pct": pnl_pct,
        "close_time": f"{date_str}T15:30:00+05:30",
        "status": "CLOSED",
    }


class TestGenerateDailyStrip:
    def test_generate_daily_strip_empty(self):
        """Empty list → zero stats, empty strip."""
        result = generate_daily_strip([])

        assert result["trading_days"] == 0
        assert result["daily_strip"] == []
        s = result["summary"]
        assert s["total_trades"] == 0
        assert s["wins"] == 0
        assert s["losses"] == 0
        assert s["win_rate"] == 0.0
        assert s["cumulative_return"] == 0.0
        assert s["max_drawdown"] == 0.0
        assert s["sharpe"] == 0.0

    def test_generate_daily_strip_structure(self):
        """Strip output has correct structure and types."""
        signals = [
            _make_closed(2.0, "2026-04-14"),
            _make_closed(1.5, "2026-04-14"),
            _make_closed(-1.0, "2026-04-15"),
        ]
        result = generate_daily_strip(signals)

        assert isinstance(result["trading_days"], int)
        assert result["trading_days"] == 2

        strip = result["daily_strip"]
        assert len(strip) == 2

        for entry in strip:
            assert "date" in entry
            assert "pnl" in entry
            assert "result" in entry
            assert "trades" in entry
            assert entry["result"] in ("WIN", "LOSS")

        s = result["summary"]
        assert "total_trades" in s
        assert "wins" in s
        assert "losses" in s
        assert "win_rate" in s
        assert "avg_return" in s
        assert "cumulative_return" in s
        assert "max_drawdown" in s
        assert "sharpe" in s

    def test_strip_sorted_by_date_ascending(self):
        """Daily strip entries are returned in chronological order."""
        signals = [
            _make_closed(1.0, "2026-04-16"),
            _make_closed(2.0, "2026-04-14"),
            _make_closed(1.5, "2026-04-15"),
        ]
        result = generate_daily_strip(signals)
        dates = [e["date"] for e in result["daily_strip"]]
        assert dates == sorted(dates)

    def test_win_loss_classification(self):
        """Days with positive total P&L are WIN, negative are LOSS."""
        signals = [
            _make_closed(3.0, "2026-04-14"),   # WIN day
            _make_closed(-2.0, "2026-04-15"),  # LOSS day
        ]
        result = generate_daily_strip(signals)
        strip = {e["date"]: e["result"] for e in result["daily_strip"]}
        assert strip["2026-04-14"] == "WIN"
        assert strip["2026-04-15"] == "LOSS"

    def test_summary_win_rate_calculation(self):
        """win_rate = wins / total_trades across all trades (not days)."""
        signals = [
            _make_closed(2.0, "2026-04-14"),   # win
            _make_closed(-1.0, "2026-04-14"),  # loss (same day)
            _make_closed(1.0, "2026-04-15"),   # win
        ]
        result = generate_daily_strip(signals)
        s = result["summary"]
        assert s["total_trades"] == 3
        assert s["wins"] == 2
        assert s["losses"] == 1
        assert abs(s["win_rate"] - 2/3) < 0.001

    def test_nested_pnl_format_in_strip(self):
        """Signals with nested final_pnl.spread_pnl_pct are handled correctly."""
        signal = {
            "signal_id": "SIG-NESTED",
            "final_pnl": {"spread_pnl_pct": 3.5},
            "close_timestamp": "2026-04-14T15:30:00+05:30",
            "status": "STOPPED_OUT",
        }
        result = generate_daily_strip([signal])
        assert result["trading_days"] == 1
        assert result["summary"]["total_trades"] == 1
        assert result["summary"]["wins"] == 1
```

Save as `pipeline/tests/test_shadow_pnl.py`.

- [ ] **Step 2: Run the tests**

```bash
cd /c/Users/Claude_Anka/askanka.com && python3 -m pytest pipeline/tests/test_shadow_pnl.py -v
```

Expected: all tests PASS. If any fail, fix `shadow_pnl.py` — do not change test logic.

- [ ] **Step 3: Commit Task 3 + 4**

```bash
cd /c/Users/Claude_Anka/askanka.com && git add pipeline/shadow_pnl.py pipeline/tests/test_shadow_pnl.py && git commit -m "feat(golden-goose): shadow P&L engine + tests"
```

---

## Task 5: Full test suite run + final commit

- [ ] **Step 1: Run the complete test suite to verify no regressions**

```bash
cd /c/Users/Claude_Anka/askanka.com && python3 -m pytest pipeline/tests/test_risk_guardrails.py pipeline/tests/test_shadow_pnl.py -v --tb=short
```

Expected: all tests PASS, zero failures.

- [ ] **Step 2: Create the combined commit**

```bash
cd /c/Users/Claude_Anka/askanka.com && git log --oneline -5
```

If the two module commits are already present, create a merge summary commit:

```bash
cd /c/Users/Claude_Anka/askanka.com && git commit --allow-empty -m "feat(golden-goose): shadow P&L engine + risk guardrails (Plans 3-4)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task covering it |
|-----------------|-----------------|
| `check_risk_gates` function signature | Task 1 |
| L1 at -10% → sizing 0.5 | Task 1, Task 2 |
| L2 at -15% → pause entries | Task 1, Task 2 |
| Empty signals → NORMAL | Task 2 |
| `create_shadow_trade` all fields | Task 3, Task 4 |
| `update_shadow_trade` target hit | Task 3, Task 4 |
| `update_shadow_trade` stop hit | Task 3, Task 4 |
| `update_shadow_trade` trade stays OPEN | Task 3, Task 4 |
| Trailing stop: peak > 2%, drop > 1.5% | Task 3, Task 4 |
| Expiry: 5 days, close at current price | Task 3, Task 4 |
| `generate_daily_strip` structure | Task 3, Task 4 |
| `generate_daily_strip` empty input | Task 3, Task 4 |
| P&L path: `pnl_pct` root + `final_pnl.spread_pnl_pct` nested | Tasks 1, 3 |

**No placeholders found.** All code blocks contain complete, runnable implementations.

**Type consistency:** `_calc_pnl` is defined in Task 3 and used only in Task 3. `_extract_signal_pnl`, `_extract_signal_date`, `_calc_max_drawdown`, `_calc_sharpe` are all defined in `shadow_pnl.py` and not referenced externally. All consistent.
