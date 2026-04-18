"""GET /api/risk-gates — current risk gate status."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))
_HERE = Path(__file__).resolve().parent.parent
_CLOSED_SIGNALS_FILE = _HERE.parent / "data" / "signals" / "closed_signals.json"
L1_THRESHOLD = -10.0
L2_THRESHOLD = -15.0
WINDOW_DAYS = 20


@router.get("/risk-gates")
def risk_gates():
    closed = _load_closed()
    recent = _filter_recent(closed, WINDOW_DAYS)
    cumulative = sum(_extract_pnl(t) for t in recent)
    trades_in_window = len(recent)
    if cumulative <= L2_THRESHOLD:
        return {"allowed": False, "sizing_factor": 0.0, "level": "L2",
                "reason": f"Cumulative P&L {cumulative:.1f}% breaches L2 ({L2_THRESHOLD}%)",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}
    elif cumulative <= L1_THRESHOLD:
        return {"allowed": True, "sizing_factor": 0.5, "level": "L1",
                "reason": f"Cumulative P&L {cumulative:.1f}% breaches L1 ({L1_THRESHOLD}%)",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}
    else:
        return {"allowed": True, "sizing_factor": 1.0, "level": "L0",
                "reason": "Normal operations",
                "cumulative_pnl": round(cumulative, 2), "trades_in_window": trades_in_window}


def _load_closed() -> list:
    if not _CLOSED_SIGNALS_FILE.exists():
        return []
    try:
        data = json.loads(_CLOSED_SIGNALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("signals", [])
    except Exception:
        return []


def _filter_recent(trades: list, days: int) -> list:
    cutoff = datetime.now(IST) - timedelta(days=days)
    result = []
    for t in trades:
        ts = t.get("close_timestamp") or t.get("close_date")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            if dt >= cutoff:
                result.append(t)
        except (ValueError, TypeError):
            continue
    return result


def _extract_pnl(trade: dict) -> float:
    fp = trade.get("final_pnl")
    if isinstance(fp, dict):
        return fp.get("spread_pnl_pct", 0.0)
    return trade.get("pnl_pct", 0.0)
