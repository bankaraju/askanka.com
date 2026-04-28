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
    """Return the full track-record payload: KPIs + extended metrics +
    per-engine buckets + ALL closed trades. The exporter has done the heavy
    lifting; this endpoint just hands it through with sensible defaults."""
    raw = _read_json(_TRACK_FILE)
    # Prefer the full trades[] when the new exporter wrote it; fall back to
    # the legacy `recent` list so the endpoint still works on stale files.
    trades = raw.get("trades") or raw.get("recent", [])

    return {
        "total_closed": raw.get("total_closed", len(trades)),
        "win_rate_pct": raw.get("win_rate_pct", 0),
        "avg_pnl_pct": raw.get("avg_pnl_pct", 0),
        "cum_pnl_pct": raw.get("cum_pnl_pct", 0),
        "metrics": raw.get("metrics", {}),
        "by_engine": raw.get("by_engine", []),
        "trades": trades,
        "updated_at": raw.get("updated_at"),
    }


@router.get("/track-record/equity-curve")
def equity_curve():
    """Per-trade-average curve across all closed trades, chronological.

    Each trade is a standalone paper position, so we plot the *running mean*
    of per-trade returns rather than the sum (which would imply portfolio-
    sized exposure on every signal). The sum is also returned as
    `total_pnl_sum_pct` for the "if sized 1 unit per trade" view.
    """
    raw = _read_json(_TRACK_FILE)
    trades = raw.get("trades") or raw.get("recent", [])

    curve = []
    cumulative_sum = 0.0
    chrono = sorted(trades, key=lambda x: x.get("close_date", ""))
    for i, t in enumerate(chrono, start=1):
        pnl = t.get("final_pnl_pct", 0) or 0
        cumulative_sum += pnl
        curve.append({
            "time": t.get("close_date", ""),
            "value": round(cumulative_sum / i, 3),  # running per-trade average
            "engine": t.get("engine_key", ""),
        })

    return {
        "curve": curve,
        "avg_pnl_pct": round(cumulative_sum / len(chrono), 2) if chrono else 0.0,
        "total_pnl_sum_pct": round(cumulative_sum, 2),
        "n": len(chrono),
    }
