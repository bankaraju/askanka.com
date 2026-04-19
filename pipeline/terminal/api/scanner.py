"""GET /api/scanner — filterable TA pattern scanner across all stocks."""
import json
import time
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"

_CACHE_TTL = 300
_cache: dict = {}


def _load_fingerprints() -> list[dict]:
    now = time.time()
    if _cache.get("data") and now - _cache.get("ts", 0) < _CACHE_TTL:
        return _cache["data"]

    stocks = []
    if not _FINGERPRINTS_DIR.exists():
        return stocks
    for f in _FINGERPRINTS_DIR.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            stocks.append(raw)
        except Exception:
            continue
    _cache["data"] = stocks
    _cache["ts"] = now
    return stocks


@router.get("/scanner")
def scanner(
    min_win: int = Query(60, ge=0, le=100),
    direction: str = Query("ALL"),
    min_occ: int = Query(10, ge=0),
    sort: str = Query("win_rate"),
    significance: str = Query("STRONG,MODERATE"),
):
    sig_set = {s.strip().upper() for s in significance.split(",")}
    direction_upper = direction.upper()
    threshold = min_win / 100.0

    all_stocks = _load_fingerprints()
    results = []

    for stock in all_stocks:
        symbol = stock.get("symbol", "")
        patterns = stock.get("fingerprint", stock.get("patterns", []))
        matched = []
        for p in patterns:
            if p.get("significance", "").upper() not in sig_set:
                continue
            if (p.get("win_rate_5d") or 0) < threshold:
                continue
            if direction_upper != "ALL" and p.get("direction", "").upper() != direction_upper:
                continue
            if (p.get("occurrences") or 0) < min_occ:
                continue
            matched.append(p)

        if not matched:
            continue

        best_win = max(p.get("win_rate_5d", 0) for p in matched)
        best_avg = max(abs(p.get("avg_return_5d", 0)) for p in matched)

        matched.sort(key=lambda p: p.get("win_rate_5d", 0), reverse=True)

        results.append({
            "symbol": symbol,
            "personality": stock.get("personality"),
            "best_win": best_win,
            "best_avg": best_avg,
            "pattern_count": len(matched),
            "patterns": matched,
        })

    sort_keys = {
        "win_rate": lambda s: s["best_win"],
        "avg_return": lambda s: s["best_avg"],
        "occurrences": lambda s: max((p.get("occurrences", 0) for p in s["patterns"]), default=0),
    }
    results.sort(key=sort_keys.get(sort, sort_keys["win_rate"]), reverse=True)

    total_patterns = sum(s["pattern_count"] for s in results)

    return {
        "stocks": results,
        "total_stocks": len(results),
        "total_patterns": total_patterns,
        "filters": {
            "min_win": min_win,
            "direction": direction_upper,
            "min_occ": min_occ,
            "sort": sort,
        },
    }
