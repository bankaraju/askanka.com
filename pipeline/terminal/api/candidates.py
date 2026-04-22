"""GET /api/candidates — composed tradeable_candidates[] + signals[]."""
import json
import sys
from pathlib import Path
from fastapi import APIRouter

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_TODAY_REGIME_FILE = _HERE.parent / "data" / "today_regime.json"
_RECOMMENDATIONS_FILE = _HERE.parent.parent / "data" / "today_recommendations.json"
_BREAKS_FILE = _HERE.parent / "data" / "correlation_breaks.json"
_FINGERPRINTS_DIR = _HERE.parent / "data" / "ta_fingerprints"
_DYNAMIC_PAIRS_FILE = _HERE.parent / "data" / "dynamic_pairs.json"  # forward-compat: Project B
_NEWS_VERDICTS_FILE = _HERE.parent / "data" / "news_verdicts.json"
_TRUST_SCORES_FILE = _HERE.parent.parent / "data" / "trust_scores.json"


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
            "score": stats.get("best_win", 0),
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
        p = {**p, "source": p.get("source", "dynamic_pair_engine")}
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
    from pipeline.terminal.api import scanner as scanner_mod
    out = []
    for raw in scanner_mod._load_fingerprints():
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
        ticker = b.get("ticker") or b.get("symbol")
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
                "action": b.get("action"),
                "regime": b.get("regime"),
            },
            "suggests_pair_with": None,
        })
    return out


def _load_news_verdicts() -> list:
    """Load today's news verdicts (read-only). Returns [] on any error."""
    raw = _read_json(_NEWS_VERDICTS_FILE, default=[])
    if isinstance(raw, list):
        return raw
    return []


def _load_trust_scores() -> dict:
    """
    Load trust scores from data/trust_scores.json.

    Returns a dict keyed by UPPER symbol → sector_grade string.
    Handles v2 format ({"version":"2.0","stocks":[...]}) and empty/corrupt files.
    """
    raw = _read_json(_TRUST_SCORES_FILE, default={})
    result: dict = {}
    stocks = raw.get("stocks") if isinstance(raw, dict) else None
    if not isinstance(stocks, list):
        return result
    for s in stocks:
        sym = (s.get("symbol") or "").upper()
        grade = s.get("sector_grade") or ""
        if sym and grade:
            result[sym] = grade
    return result


def _attach_trust_grades(candidates: list, trust_scores: dict) -> list:
    """
    Attach trust_grade to each candidate's legs (or top-level for single-ticker).

    Mutates in-place for efficiency (candidates are already deepcopied by
    apply_news_modifier at the prior stage).
    """
    for c in candidates:
        long_legs = c.get("long_legs") or []
        short_legs = c.get("short_legs") or []
        ticker = (c.get("ticker") or "").upper()

        if long_legs or short_legs:
            for leg in long_legs:
                if isinstance(leg, dict):
                    sym = (leg.get("ticker") or "").upper()
                    if sym and "trust_grade" not in leg:
                        leg["trust_grade"] = trust_scores.get(sym, "")
            for leg in short_legs:
                if isinstance(leg, dict):
                    sym = (leg.get("ticker") or "").upper()
                    if sym and "trust_grade" not in leg:
                        leg["trust_grade"] = trust_scores.get(sym, "")
        elif ticker and "trust_grade" not in c:
            c["trust_grade"] = trust_scores.get(ticker, "")
    return candidates


@router.get("/candidates")
def candidates():
    from pipeline.signal_enrichment import apply_news_modifier, apply_trust_modifier

    today_regime = _read_json(_TODAY_REGIME_FILE, default={})
    today_recs = _read_json(_RECOMMENDATIONS_FILE, default={})
    news_verdicts = _load_news_verdicts()
    trust_scores = _load_trust_scores()

    raw_candidates = (
        _build_static_spreads(today_regime)
        + _build_regime_picks(today_recs)
        + _build_dynamic_pairs()
    )
    enriched_candidates = [
        apply_news_modifier(c, news_verdicts) for c in raw_candidates
    ]
    # Attach trust grades to legs/tickers then apply the trust modifier.
    # Trust modifier is regime-conditional: only fires in NEUTRAL zone.
    _attach_trust_grades(enriched_candidates, trust_scores)
    enriched_candidates = [
        apply_trust_modifier(c, today_regime) for c in enriched_candidates
    ]

    return {
        "tradeable_candidates": enriched_candidates,
        "signals": (
            _build_ta_signals()
            + _build_correlation_break_signals()
        ),
        "regime_zone": today_regime.get("regime"),
        "updated_at": today_regime.get("timestamp"),
    }
