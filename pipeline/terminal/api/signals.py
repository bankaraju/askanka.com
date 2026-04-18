"""GET /api/signals — active signals, recommendations, and positions."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_OPEN_SIGNALS_FILE = _HERE.parent / "data" / "signals" / "open_signals.json"
_RECOMMENDATIONS_FILE = _HERE.parent.parent / "data" / "today_recommendations.json"
_LIVE_STATUS_FILE = _HERE.parent.parent / "data" / "live_status.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/signals")
def signals():
    raw_signals = _read_json(_OPEN_SIGNALS_FILE, default=[])
    if isinstance(raw_signals, dict):
        raw_signals = raw_signals.get("signals", [])
    raw_recs = _read_json(_RECOMMENDATIONS_FILE)
    stocks = raw_recs.get("stocks", [])
    raw_positions = _read_json(_LIVE_STATUS_FILE)
    positions = raw_positions.get("positions", [])
    return {
        "signals": raw_signals,
        "recommendations": stocks,
        "positions": positions,
        "regime_zone": raw_recs.get("regime_zone"),
        "updated_at": raw_recs.get("updated_at") or raw_positions.get("updated_at"),
    }
