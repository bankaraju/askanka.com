"""GET /api/health — system health and data freshness."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

_HERE = Path(__file__).resolve().parent.parent
_DATA_DIR = _HERE.parent.parent / "data"
_PIPELINE_DATA_DIR = _HERE.parent / "data"

_CRITICAL_FILES = {
    "global_regime": _DATA_DIR / "global_regime.json",
    "today_recommendations": _DATA_DIR / "today_recommendations.json",
    "track_record": _DATA_DIR / "track_record.json",
    "trust_scores": _DATA_DIR / "trust_scores.json",
    "live_status": _DATA_DIR / "live_status.json",
    "today_regime": _PIPELINE_DATA_DIR / "today_regime.json",
}


def _check_file(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "stale": True}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        updated = raw.get("updated_at") or raw.get("timestamp") or raw.get("source_timestamp")
        return {"exists": True, "updated_at": updated, "stale": False}
    except Exception:
        return {"exists": True, "stale": True}


@router.get("/health")
def health():
    now = datetime.now(IST).isoformat()
    data_files = {name: _check_file(path) for name, path in _CRITICAL_FILES.items()}
    return {
        "status": "ok",
        "timestamp": now,
        "data_files": data_files,
    }
