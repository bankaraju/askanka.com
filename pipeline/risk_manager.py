"""
ANKA Risk Manager — Stop-Loss, Re-entry, and Position Sizing

Rules:
1. NO stock enters portfolio without deep ANKA Trust Score
2. Stop-loss levels set by Trust Score grade:
   - A+ / A: 8% stop (high conviction, wider leash)
   - B+ / B: 5% stop (moderate conviction)
   - C / D: 3% stop (low conviction, tight leash)
3. Re-entry: allowed after 3 trading days IF:
   - Trust Score hasn't deteriorated
   - Regime supports the direction
   - Price retraces 50% of the stop-loss move
4. Position sizing:
   - Max 10% per position
   - Scaled by Trust Score: A+ gets 10%, D gets 3%
   - Reduced by 50% in CAUTION, 75% in RISK-OFF
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent.parent / "artifacts"


# ── Stop-Loss Rules ──────────────────────────────────────────────────

STOP_BY_GRADE = {
    "A+": 8.0,
    "A":  8.0,
    "B+": 5.0,
    "B":  5.0,
    "C":  3.0,
    "D":  3.0,
    "F":  0.0,  # Should never be in portfolio
}

MAX_WEIGHT_BY_GRADE = {
    "A+": 10.0,
    "A":  8.0,
    "B+": 6.0,
    "B":  5.0,
    "C":  3.0,
    "D":  2.0,
    "F":  0.0,
}

REGIME_SIZE_MULTIPLIER = {
    "EUPHORIA":  1.0,
    "RISK-ON":   1.0,
    "NEUTRAL":   0.8,
    "CAUTION":   0.5,
    "RISK-OFF":  0.25,
}


def get_stop_loss(grade: str, side: str, entry_price: float) -> dict:
    """Calculate stop-loss level for a position."""
    stop_pct = STOP_BY_GRADE.get(grade, 5.0)

    if side == "LONG":
        stop_price = entry_price * (1 - stop_pct / 100)
    else:  # SHORT
        stop_price = entry_price * (1 + stop_pct / 100)

    return {
        "stop_pct": stop_pct,
        "stop_price": round(stop_price, 2),
        "grade_basis": f"{grade} grade → {stop_pct}% stop",
    }


def get_position_size(grade: str, regime: str) -> float:
    """Calculate max position weight for a stock."""
    base = MAX_WEIGHT_BY_GRADE.get(grade, 5.0)
    multiplier = REGIME_SIZE_MULTIPLIER.get(regime, 0.8)
    return round(base * multiplier, 1)


def check_stop_hit(position: dict, current_price: float) -> dict | None:
    """Check if a position's stop-loss has been hit.

    Returns alert dict if stop hit, None otherwise.
    """
    entry = position.get("entry_price") or position.get("price")
    if not entry:
        return None

    stop = position.get("stop_price")
    if not stop:
        grade = position.get("trust_grade", "B")
        side = position.get("side", "LONG")
        stop_info = get_stop_loss(grade, side, entry)
        stop = stop_info["stop_price"]

    side = position.get("side", "LONG")
    symbol = position.get("symbol", "?")

    if side == "LONG" and current_price <= stop:
        pnl = (current_price / entry - 1) * 100
        return {
            "type": "STOP_HIT",
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop": stop,
            "current": current_price,
            "pnl_pct": round(pnl, 2),
            "action": f"EXIT {symbol} LONG at Rs {current_price:,.0f} (stop {stop:,.0f} hit, P&L {pnl:+.1f}%)",
            "severity": "HIGH",
        }
    elif side == "SHORT" and current_price >= stop:
        pnl = (1 - current_price / entry) * 100
        return {
            "type": "STOP_HIT",
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop": stop,
            "current": current_price,
            "pnl_pct": round(pnl, 2),
            "action": f"COVER {symbol} SHORT at Rs {current_price:,.0f} (stop {stop:,.0f} hit, P&L {pnl:+.1f}%)",
            "severity": "HIGH",
        }

    return None


# ── Re-entry Rules ───────────────────────────────────────────────────

def check_reentry_eligible(stopped_position: dict, current_price: float,
                           current_regime: str, days_since_stop: int) -> dict | None:
    """Check if a stopped-out position is eligible for re-entry.

    Conditions:
    1. At least 3 trading days since stop (cooling period)
    2. Trust Score hasn't deteriorated
    3. Regime supports direction
    4. Technical confirmation (at least 2 of 3):
       a. RSI(14) oversold (<30 for longs) or overbought (>70 for shorts)
       b. Price near lower Bollinger Band (for longs) or upper (for shorts)
       c. Price retraced 50%+ of the stop-loss move
    """
    symbol = stopped_position.get("symbol", "?")
    side = stopped_position.get("side", "LONG")
    entry = stopped_position.get("entry_price") or stopped_position.get("price", 0)
    stop = stopped_position.get("stop_price", 0)
    grade = stopped_position.get("trust_grade", "?")

    # Rule 1: Cooling period
    if days_since_stop < 3:
        return None

    # Rule 2: Trust Score check
    current_trust = _load_current_trust(symbol)
    if current_trust and current_trust.get("trust_score_grade", "F") < grade:
        return None

    # Rule 3: Regime check
    if side == "LONG" and current_regime in ("RISK-OFF",):
        return None
    if side == "SHORT" and current_regime in ("EUPHORIA", "RISK-ON"):
        return None

    # Rule 4: Technical confirmation (need 2 of 3 signals)
    technicals = compute_technicals(symbol)
    if not technicals:
        return None

    signals = 0
    signal_reasons = []

    rsi = technicals.get("rsi_14")
    bb_lower = technicals.get("bb_lower")
    bb_upper = technicals.get("bb_upper")

    # 4a. RSI signal
    if rsi is not None:
        if side == "LONG" and rsi < 35:
            signals += 1
            signal_reasons.append(f"RSI {rsi:.0f} oversold")
        elif side == "SHORT" and rsi > 65:
            signals += 1
            signal_reasons.append(f"RSI {rsi:.0f} overbought")

    # 4b. Bollinger Band signal
    if side == "LONG" and bb_lower and current_price <= bb_lower * 1.02:
        signals += 1
        signal_reasons.append(f"Near lower BB (Rs {bb_lower:,.0f})")
    elif side == "SHORT" and bb_upper and current_price >= bb_upper * 0.98:
        signals += 1
        signal_reasons.append(f"Near upper BB (Rs {bb_upper:,.0f})")

    # 4c. 50% retracement
    if entry and stop:
        retracement_target = stop + (entry - stop) * 0.5 if side == "LONG" else stop - (stop - entry) * 0.5
        if side == "LONG" and current_price >= retracement_target:
            signals += 1
            signal_reasons.append("50% retracement")
        elif side == "SHORT" and current_price <= retracement_target:
            signals += 1
            signal_reasons.append("50% retracement")

    # Need at least 2 of 3
    if signals < 2:
        return None

    new_stop = get_stop_loss(grade, side, current_price)
    trust_grade = current_trust.get("trust_score_grade", grade) if current_trust else grade

    return {
        "type": "REENTRY_ELIGIBLE",
        "symbol": symbol,
        "side": side,
        "old_entry": entry,
        "new_entry": current_price,
        "new_stop": new_stop["stop_price"],
        "trust_grade": trust_grade,
        "technical_signals": signal_reasons,
        "rsi": rsi,
        "action": f"RE-ENTER {symbol} {side} at Rs {current_price:,.0f} — {', '.join(signal_reasons)}",
        "severity": "MEDIUM",
    }


def compute_technicals(symbol: str, period: int = 20) -> dict | None:
    """Compute RSI(14) and Bollinger Bands(20,2) from yfinance data."""
    try:
        import yfinance as yf
        import numpy as np

        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="3mo")
        if hist.empty or len(hist) < period:
            return None

        close = hist["Close"]

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1]) if not rsi.empty else None

        # Bollinger Bands (20, 2)
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        bb_upper = float((sma + 2 * std).iloc[-1])
        bb_lower = float((sma - 2 * std).iloc[-1])
        bb_mid = float(sma.iloc[-1])

        # Trend: price vs 50-day SMA
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        return {
            "rsi_14": round(current_rsi, 1) if current_rsi else None,
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "bb_mid": round(bb_mid, 2),
            "sma_50": round(sma50, 2) if sma50 else None,
            "last_close": float(close.iloc[-1]),
        }
    except ImportError:
        return None
    except Exception:
        return None


def _load_current_trust(symbol: str) -> dict | None:
    """Load the latest Trust Score from artifacts."""
    ts_file = ARTIFACTS / symbol / "trust_score.json"
    if ts_file.exists():
        try:
            return json.loads(ts_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ── Portfolio Gate: Deep Analysis Required ───────────────────────────

def has_deep_trust_score(symbol: str) -> bool:
    """Check if a stock has a deep Trust Score (not just fast proxy)."""
    ts_file = ARTIFACTS / symbol / "trust_score.json"
    narr_file = ARTIFACTS / symbol / "narratives.json"

    if not ts_file.exists() or not narr_file.exists():
        return False

    try:
        ts = json.loads(ts_file.read_text(encoding="utf-8"))
        narr = json.loads(narr_file.read_text(encoding="utf-8"))

        # Must have scored at least 5 guidance items from actual annual reports
        scored = ts.get("guidance_scored", 0)
        reports = len(narr)
        return scored >= 5 and reports >= 2
    except Exception:
        return False


def stocks_needing_deep_analysis(portfolio: dict) -> list:
    """Return list of portfolio stocks that lack deep Trust Score."""
    missing = []
    for pos in portfolio.get("positions", []):
        sym = pos.get("symbol", "")
        if sym and not has_deep_trust_score(sym):
            missing.append(sym)
    return missing
