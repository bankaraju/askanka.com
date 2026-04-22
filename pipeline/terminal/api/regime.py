"""GET /api/regime — current market regime and eligible spreads."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_GLOBAL_REGIME_FILE = _HERE.parent.parent / "data" / "global_regime.json"
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"
_RECOMMENDATIONS_FILE = _HERE.parent / "data" / "recommendations.json"


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

    # Merge today's per-spread conviction into eligible_spreads so the dashboard
    # can show win-rate AND today's actionability side by side.
    eligible = dict(today_data.get("eligible_spreads", {}))
    recs_data = _read_json(_RECOMMENDATIONS_FILE)
    by_name = {r.get("name"): r for r in recs_data.get("recommendations", []) if r.get("name")}
    for name, stats in eligible.items():
        rec = by_name.get(name)
        if rec and isinstance(stats, dict):
            stats["conviction"] = rec.get("conviction", "NONE")
            stats["score"] = rec.get("score", 0)
            stats["action"] = rec.get("action", "INACTIVE")
            stats["z_score"] = rec.get("z_score")

    return {
        "zone": zone,
        "score": global_data.get("score", 0.0),
        "regime_source": global_data.get("regime_source", today_data.get("regime_source", "unknown")),
        "stable": stable,
        "consecutive_days": consecutive,
        "msi_score": today_data.get("msi_score", 0.0),
        "msi_regime": today_data.get("msi_regime", "UNAVAILABLE"),
        "msi_updated_at": today_data.get("msi_updated_at"),
        "trade_map_key": today_data.get("trade_map_key"),
        "eligible_spreads": eligible,
        "top_drivers": global_data.get("top_drivers", []),
        "updated_at": global_data.get("updated_at") or today_data.get("timestamp"),
    }
