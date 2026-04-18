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
