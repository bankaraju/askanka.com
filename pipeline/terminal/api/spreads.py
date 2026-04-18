"""GET /api/spreads — eligible spread trades from regime trade map."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TRADE_MAP_FILE = _HERE.parent / "autoresearch" / "regime_trade_map.json"
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/spreads")
def spreads():
    today = _read_json(_TODAY_REGIME_FILE)
    eligible = today.get("eligible_spreads", {})
    zone = today.get("regime", "UNKNOWN")

    trade_map = _read_json(_TRADE_MAP_FILE)
    results = trade_map.get("results", {})
    zone_data = results.get(zone, {})

    spread_list = []
    for name, stats in eligible.items():
        detail = zone_data.get(name, {})
        spread_list.append({
            "name": name,
            "best_win": stats.get("best_win", 0),
            "best_period": stats.get("best_period", 0),
            "1d_win": stats.get("1d_win", 0),
            "3d_win": stats.get("3d_win", 0),
            "5d_win": stats.get("5d_win", 0),
            "1d_avg": stats.get("1d_avg", 0),
            "3d_avg": stats.get("3d_avg", 0),
            "5d_avg": stats.get("5d_avg", 0),
            "detail": detail,
        })

    spread_list.sort(key=lambda s: s["best_win"], reverse=True)

    return {
        "zone": zone,
        "spreads": spread_list,
        "total": len(spread_list),
    }
