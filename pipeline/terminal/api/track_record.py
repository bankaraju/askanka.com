"""GET /api/track-record — shadow P&L and trade history."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TRACK_FILE = _HERE.parent.parent / "data" / "track_record.json"
_CLOSED_FILE = _HERE.parent / "data" / "signals" / "closed_signals.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/track-record")
def track_record():
    raw = _read_json(_TRACK_FILE)
    trades = raw.get("recent", [])

    return {
        "total_closed": raw.get("total_closed", len(trades)),
        "win_rate_pct": raw.get("win_rate_pct", 0),
        "avg_pnl_pct": raw.get("avg_pnl_pct", 0),
        "trades": trades,
        "updated_at": raw.get("updated_at"),
    }


@router.get("/track-record/equity-curve")
def equity_curve():
    raw = _read_json(_TRACK_FILE)
    trades = raw.get("recent", [])

    curve = []
    cumulative = 0.0
    for t in sorted(trades, key=lambda x: x.get("close_date", "")):
        pnl = t.get("final_pnl_pct", 0) or 0
        cumulative += pnl
        curve.append({
            "time": t.get("close_date", ""),
            "value": round(cumulative, 2),
        })

    return {"curve": curve, "total_return": round(cumulative, 2)}
