"""GET /api/regime — current market regime and eligible spreads."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_GLOBAL_REGIME_FILE = _HERE.parent.parent / "data" / "global_regime.json"
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.get("/regime")
def regime():
    global_data = _read_json(_GLOBAL_REGIME_FILE)
    today_data = _read_json(_TODAY_REGIME_FILE)
    zone = global_data.get("zone") or today_data.get("regime") or "UNKNOWN"
    stable = global_data.get("stable", today_data.get("regime_stable", False))
    consecutive = global_data.get("consecutive_days", today_data.get("consecutive_days", 0))
    return {
        "zone": zone,
        "score": global_data.get("score", 0.0),
        "regime_source": global_data.get("regime_source", today_data.get("regime_source", "unknown")),
        "stable": stable,
        "consecutive_days": consecutive,
        "msi_score": today_data.get("msi_score", 0.0),
        "msi_regime": today_data.get("msi_regime", "UNAVAILABLE"),
        "trade_map_key": today_data.get("trade_map_key"),
        "eligible_spreads": today_data.get("eligible_spreads", {}),
        "top_drivers": global_data.get("top_drivers", []),
        "updated_at": global_data.get("updated_at") or today_data.get("timestamp"),
    }
