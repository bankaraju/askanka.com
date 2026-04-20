"""GET /api/candidates — composed tradeable_candidates[] + signals[]."""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"
_RECOMMENDATIONS_FILE = _HERE.parent.parent / "data" / "today_recommendations.json"
_BREAKS_FILE = _HERE.parent / "data" / "correlation_breaks.json"
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"
_DYNAMIC_PAIRS_FILE = _HERE.parent / "data" / "dynamic_pairs.json"  # forward-compat: Project B


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _build_static_spreads(today_regime: dict) -> list:
    out = []
    for name, stats in (today_regime.get("eligible_spreads") or {}).items():
        if not isinstance(stats, dict):
            continue
        out.append({
            "source": "static_config",
            "name": name,
            "long_legs": list(stats.get("long_legs") or []),
            "short_legs": list(stats.get("short_legs") or []),
            "conviction": stats.get("conviction", "NONE"),
            "score": stats.get("score", 0),
            "horizon_days": stats.get("best_period", 5),
            "horizon_basis": "mean_reversion",
            "sizing_basis": None,
            "reason": stats.get("reason") or f"win_rate={stats.get('best_win', 0)}%",
        })
    return out


def _build_dynamic_pairs() -> list:
    """Forward-compat loader for Project B output. Returns [] until B lands."""
    raw = _read_json(_DYNAMIC_PAIRS_FILE, default={})
    pairs = raw.get("tradeable_candidates") if isinstance(raw, dict) else raw
    if not isinstance(pairs, list):
        return []
    out = []
    for p in pairs:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        p.setdefault("source", "dynamic_pair_engine")
        out.append(p)
    return out


def _build_regime_picks(today_recs: dict) -> list:
    out = []
    for s in today_recs.get("stocks") or []:
        ticker = s.get("ticker")
        if not ticker:
            continue
        direction = (s.get("direction") or "").upper()
        long_legs = [ticker] if direction == "LONG" else []
        short_legs = [ticker] if direction == "SHORT" else []
        out.append({
            "source": "regime_engine",
            "name": f"Phase B: {ticker}",
            "long_legs": long_legs,
            "short_legs": short_legs,
            "conviction": s.get("conviction", "NONE"),
            "score": s.get("score") or 0,
            "horizon_days": s.get("horizon_days", 3),
            "horizon_basis": "event_decay",
            "sizing_basis": None,
            "reason": s.get("reason") or f"hit_rate={s.get('hit_rate', 0)}",
        })
    return out


def _build_ta_signals() -> list:
    out = []
    if not _FINGERPRINTS_DIR.exists():
        return out
    for f in _FINGERPRINTS_DIR.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ticker = raw.get("symbol")
        if not ticker:
            continue
        for p in raw.get("patterns") or raw.get("fingerprint") or []:
            if (p.get("significance") or "").upper() != "STRONG":
                continue
            out.append({
                "source": "ta_scanner",
                "name": f"{ticker} {p.get('pattern')}",
                "ticker": ticker,
                "event_type": p.get("pattern"),
                "fired_at": p.get("last_occurrence"),
                "context": {
                    "win_rate_5d": p.get("win_rate_5d"),
                    "occurrences": p.get("occurrences"),
                    "direction": p.get("direction"),
                },
                "suggests_pair_with": None,
            })
    return out


def _build_correlation_break_signals() -> list:
    raw = _read_json(_BREAKS_FILE, default=[])
    if isinstance(raw, dict):
        raw = raw.get("breaks", [])
    out = []
    for b in raw:
        ticker = b.get("ticker")
        if not ticker:
            continue
        out.append({
            "source": "correlation_break",
            "name": f"{ticker} divergence",
            "ticker": ticker,
            "event_type": b.get("classification"),
            "fired_at": b.get("timestamp"),
            "context": {
                "z_score": b.get("z_score"),
                "oi_confirmation": b.get("oi_confirmation"),
            },
            "suggests_pair_with": None,
        })
    return out


@router.get("/candidates")
def candidates():
    today_regime = _read_json(_TODAY_REGIME_FILE, default={})
    today_recs = _read_json(_RECOMMENDATIONS_FILE, default={})
    return {
        "tradeable_candidates": (
            _build_static_spreads(today_regime)
            + _build_regime_picks(today_recs)
            + _build_dynamic_pairs()
        ),
        "signals": (
            _build_ta_signals()
            + _build_correlation_break_signals()
        ),
        "regime_zone": today_regime.get("regime"),
    }
