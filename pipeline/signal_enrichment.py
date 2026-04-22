"""
signal_enrichment.py — Load 4 rigour JSON files and expose per-ticker lookup helpers.

Loaders never raise on missing or corrupt files; they return an empty dict instead.
Task 1 of the signal-enrichment wiring initiative.
Tasks 2-3 add enrich_signal() and gate_signal() for conviction scoring.
"""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent

TRUST_PATH = _REPO_ROOT / "opus" / "artifacts" / "model_portfolio.json"
TRUST_SCORES_DIR = _REPO_ROOT / "opus" / "artifacts"
BREAKS_PATH = _REPO_ROOT / "pipeline" / "data" / "correlation_breaks.json"
REGIME_PROFILE_PATH = _REPO_ROOT / "pipeline" / "autoresearch" / "reverse_regime_profile.json"
OI_ANOMALIES_PATH = _REPO_ROOT / "pipeline" / "data" / "oi_anomalies.json"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_trust_scores(path: Path | None = None) -> Dict[str, Dict]:
    """
    Load OPUS Trust Scores from per-stock trust_score.json files.

    Primary source: opus/artifacts/{symbol}/trust_score.json (all scored stocks)
    Fallback: model_portfolio.json (for opus_side and thesis fields)

    Returns a dict keyed by symbol:
        {trust_grade, trust_score, opus_side, thesis}
    """
    # Resolve the default at call time, not def time, so tests that
    # monkeypatch TRUST_PATH actually take effect.
    if path is None:
        path = TRUST_PATH

    result: Dict[str, Dict] = {}

    # Prefer V2 scores if available (only when using the default path — not in tests)
    v2_path = _REPO_ROOT / "data" / "trust_scores_v2.json"
    if path == TRUST_PATH and v2_path.exists():
        try:
            v2 = json.loads(v2_path.read_text(encoding="utf-8"))
            if v2.get("version") == "2.0":
                for s in v2.get("stocks", []):
                    sym = s.get("symbol")
                    if not sym:
                        continue
                    grade = s.get("sector_grade", "?")
                    if grade in ("?", ""):
                        continue
                    result[sym] = {
                        "trust_grade": grade,
                        "trust_score": s.get("composite_score", 0),
                        "opus_side": None,
                        "thesis": s.get("grade_reason", ""),
                    }
                logger.info("load_trust_scores: loaded %d V2 scores", len(result))
        except Exception as exc:
            logger.warning("load_trust_scores: V2 load failed — %s, falling back", exc)

    # Primary: scan per-stock trust_score.json files
    try:
        for sym_dir in TRUST_SCORES_DIR.iterdir():
            if not sym_dir.is_dir() or sym_dir.name == "transcripts":
                continue
            ts_path = sym_dir / "trust_score.json"
            if not ts_path.exists():
                continue
            try:
                data = json.loads(ts_path.read_text(encoding="utf-8"))
                grade = data.get("trust_score_grade", "?")
                if grade in ("?", "INSUFFICIENT_DATA", ""):
                    continue
                result[sym_dir.name] = {
                    "trust_grade": grade,
                    "trust_score": data.get("trust_score_pct", 0),
                    "opus_side": None,
                    "thesis": data.get("biggest_strength", ""),
                }
            except Exception:
                continue
    except Exception as exc:
        logger.warning("load_trust_scores: scan failed — %s", exc)

    # Overlay model_portfolio.json for opus_side and thesis
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for pos in raw.get("positions", []):
            symbol = pos.get("symbol")
            if not symbol:
                continue
            if symbol in result:
                result[symbol]["opus_side"] = pos.get("side")
                if pos.get("thesis"):
                    result[symbol]["thesis"] = pos["thesis"]
            else:
                result[symbol] = {
                    "trust_grade": pos.get("trust_grade"),
                    "trust_score": pos.get("trust_score"),
                    "opus_side": pos.get("side"),
                    "thesis": pos.get("thesis"),
                }
    except Exception:
        pass

    return result


def load_correlation_breaks(path: Path = BREAKS_PATH) -> Dict[str, Dict]:
    """
    Load Phase C correlation breaks from correlation_breaks.json.

    Returns a dict keyed by symbol:
        {classification, action, z_score, expected_return, actual_return, oi_anomaly, trade_rec}
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        breaks = raw.get("breaks", [])
        result: Dict[str, Dict] = {}
        for brk in breaks:
            symbol = brk.get("symbol")
            if not symbol:
                continue
            result[symbol] = {
                "classification": brk.get("classification"),
                "action": brk.get("action"),
                "z_score": brk.get("z_score"),
                "expected_return": brk.get("expected_return"),
                "actual_return": brk.get("actual_return"),
                "oi_anomaly": brk.get("oi_anomaly"),
                "trade_rec": brk.get("trade_rec"),
            }
        return result
    except FileNotFoundError:
        logger.debug("load_correlation_breaks: file not found — %s", path)
        return {}
    except Exception as exc:
        logger.warning("load_correlation_breaks: failed to load %s — %s", path, exc)
        return {}


def load_regime_profile(path: Path = REGIME_PROFILE_PATH) -> Dict[str, Dict]:
    """
    Load Phase A regime profile from reverse_regime_profile.json.

    Returns a dict keyed by symbol:
        {episode_count, tradeable_rate, persistence_rate, hit_rate, avg_drift_1d}
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        stock_profiles = raw.get("stock_profiles", {})
        result: Dict[str, Dict] = {}
        for symbol, profile in stock_profiles.items():
            summary = profile.get("summary", {})
            result[symbol] = {
                "episode_count": summary.get("episode_count"),
                "tradeable_rate": summary.get("tradeable_rate"),
                "persistence_rate": summary.get("persistence_rate"),
                "hit_rate": summary.get("hit_rate"),
                "avg_drift_1d": summary.get("avg_drift_1d"),
            }
        return result
    except FileNotFoundError:
        logger.debug("load_regime_profile: file not found — %s", path)
        return {}
    except Exception as exc:
        logger.warning("load_regime_profile: failed to load %s — %s", path, exc)
        return {}


def load_oi_anomalies(path: Path = OI_ANOMALIES_PATH) -> Dict[str, Dict]:
    """
    Load OI anomalies from oi_anomalies.json.

    Handles both bare-list format (``[{...}]``) and dict-wrapped format
    (``{"anomalies": [{...}]}``).

    Returns a dict keyed by symbol:
        {anomaly_type, pcr, sentiment, oi_change, pcr_flip}
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))

        # Normalise to a list regardless of wrapping
        if isinstance(raw, list):
            anomalies = raw
        elif isinstance(raw, dict):
            anomalies = raw.get("anomalies", [])
        else:
            logger.warning("load_oi_anomalies: unexpected top-level type %s in %s", type(raw), path)
            return {}

        result: Dict[str, Dict] = {}
        for item in anomalies:
            symbol = item.get("symbol")
            if not symbol:
                continue
            result[symbol] = {
                "anomaly_type": item.get("anomaly_type"),
                "pcr": item.get("pcr"),
                "sentiment": item.get("sentiment"),
                "oi_change": item.get("oi_change"),
                "pcr_flip": item.get("pcr_flip"),
            }
        return result
    except FileNotFoundError:
        logger.debug("load_oi_anomalies: file not found — %s", path)
        return {}
    except Exception as exc:
        logger.warning("load_oi_anomalies: failed to load %s — %s", path, exc)
        return {}


# ---------------------------------------------------------------------------
# Thin get_* helpers (cache lookup only — never load from disk)
# ---------------------------------------------------------------------------

def get_trust(symbol: str, cache: Dict) -> Optional[Dict]:
    """Return trust data for symbol, or None if not present."""
    return cache.get(symbol)


def get_break(symbol: str, cache: Dict) -> Optional[Dict]:
    """Return correlation break data for symbol, or None if not present."""
    return cache.get(symbol)


def get_rank(symbol: str, cache: Dict) -> Optional[Dict]:
    """Return regime profile data for symbol, or None if not present."""
    return cache.get(symbol)


def get_oi(symbol: str, cache: Dict) -> Optional[Dict]:
    """Return OI anomaly data for symbol, or None if not present."""
    return cache.get(symbol)


# ---------------------------------------------------------------------------
# Provenance helper
# ---------------------------------------------------------------------------

def _provenance(path: Path) -> Dict[str, Any]:
    """
    Record file provenance metadata for the rigour trail.

    Returns a dict with:
        path       — relative to _REPO_ROOT if possible, else absolute str
        exists     — bool
        mtime      — ISO UTC string if file exists, else None
        size_bytes — int if file exists, else None
    """
    try:
        rel = str(path.relative_to(_REPO_ROOT))
    except ValueError:
        rel = str(path)

    if path.exists():
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        size = stat.st_size
        exists = True
    else:
        mtime = None
        size = None
        exists = False

    return {
        "path": rel,
        "exists": exists,
        "mtime": mtime,
        "size_bytes": size,
    }


# ---------------------------------------------------------------------------
# Task 2: enrich_signal
# ---------------------------------------------------------------------------

def enrich_signal(
    signal: Dict[str, Any],
    trust_cache: Dict,
    breaks_cache: Dict,
    profile_cache: Dict,
    oi_cache: Dict,
    trust_path: Path = TRUST_PATH,
    breaks_path: Path = BREAKS_PATH,
    profile_path: Path = REGIME_PROFILE_PATH,
    oi_path: Path = OI_ANOMALIES_PATH,
) -> Dict[str, Any]:
    """
    Attach rigour data from the four caches to a signal dict.

    Returns a NEW dict (does not mutate input) with original fields plus:
      - trust_scores:       {ticker: {trust_grade, trust_score, opus_side, thesis} | None}
      - regime_rank:        {ticker: {hit_rate, tradeable_rate, ...} | None}
      - correlation_breaks: {ticker: {classification, z_score, ...} | None}
      - oi_anomalies:       {ticker: {anomaly_type, pcr, sentiment, ...} | None}
      - rigour_trail:       {enriched_at, sources: {trust, breaks, regime_profile, oi_anomalies}}
    """
    enriched = copy.deepcopy(signal)

    # Collect all tickers from long and short legs
    tickers: List[str] = []
    for leg in signal.get("long_legs", []):
        t = leg.get("ticker")
        if t:
            tickers.append(t)
    for leg in signal.get("short_legs", []):
        t = leg.get("ticker")
        if t:
            tickers.append(t)

    # Build per-ticker enrichment dicts
    trust_scores: Dict[str, Optional[Dict]] = {}
    regime_rank: Dict[str, Optional[Dict]] = {}
    correlation_breaks: Dict[str, Optional[Dict]] = {}
    oi_anomalies: Dict[str, Optional[Dict]] = {}

    for ticker in tickers:
        trust_scores[ticker] = get_trust(ticker, trust_cache)
        regime_rank[ticker] = get_rank(ticker, profile_cache)
        correlation_breaks[ticker] = get_break(ticker, breaks_cache)
        oi_anomalies[ticker] = get_oi(ticker, oi_cache)

    enriched["trust_scores"] = trust_scores
    enriched["regime_rank"] = regime_rank
    enriched["correlation_breaks"] = correlation_breaks
    enriched["oi_anomalies"] = oi_anomalies

    # Build rigour trail
    enriched["rigour_trail"] = {
        "enriched_at": datetime.now(tz=timezone.utc).isoformat(),
        "sources": {
            "trust": _provenance(trust_path),
            "breaks": _provenance(breaks_path),
            "regime_profile": _provenance(profile_path),
            "oi_anomalies": _provenance(oi_path),
        },
    }

    return enriched


# ---------------------------------------------------------------------------
# Task 3: gate_signal — conviction scoring with hard-block rules
# ---------------------------------------------------------------------------

# Grade order (index = rank, 0 = lowest/F, 7 = highest/A+)
_GRADE_ORDER: List[str] = ["F", "D", "C", "C+", "B", "B+", "A", "A+"]


def _grade_rank(grade: Optional[str]) -> Optional[int]:
    """Return 0-based rank for a trust grade, or None if unknown."""
    if grade is None:
        return None
    try:
        return _GRADE_ORDER.index(grade)
    except ValueError:
        return None


def gate_signal(
    enriched: Dict[str, Any],
) -> Tuple[bool, Optional[str], float]:
    """
    Evaluate conviction for an enriched signal.

    Hard rules (blocking):
      - Long a name with trust_grade C or worse (rank <= 2) → blocked
      - Short a name with trust_grade A or A+ (rank >= 6) → blocked

    Soft adjustments (score +/-):
      - Phase C break trade_rec matches leg direction: +8
      - Phase C break trade_rec opposes: -8
      - OI CALL_BUILDUP / BULLISH sentiment on long leg: +5
      - OI PUT_BUILDUP / BEARISH sentiment on long leg: -5
      - Short legs: PUT_BUILDUP confirms short → +5; CALL_BUILDUP opposes → -5
      - regime_rank hit_rate > 0.55: +min(10, (hr-0.5)*50)
      - regime_rank hit_rate < 0.45: -min(10, (0.5-hr)*50)

    Returns (blocked, reason, score) where score is clamped to [0, 100].
    Fail-open: missing enrichment data → no penalty, no bonus.
    """
    trust_scores = enriched.get("trust_scores", {})
    regime_rank = enriched.get("regime_rank", {})
    correlation_breaks = enriched.get("correlation_breaks", {})
    oi_anomalies = enriched.get("oi_anomalies", {})

    long_tickers = [leg["ticker"] for leg in enriched.get("long_legs", []) if "ticker" in leg]
    short_tickers = [leg["ticker"] for leg in enriched.get("short_legs", []) if "ticker" in leg]

    score = 50.0

    # ---- Hard rules ----
    for ticker in long_tickers:
        trust = trust_scores.get(ticker)
        if trust is None:
            continue
        grade = trust.get("trust_grade")
        rank = _grade_rank(grade)
        if rank is not None and rank <= 2:  # F, D, C
            return True, f"BLOCKED: long leg {ticker} has trust_grade {grade} (rank {rank} <= 2)", score

    for ticker in short_tickers:
        trust = trust_scores.get(ticker)
        if trust is None:
            continue
        grade = trust.get("trust_grade")
        rank = _grade_rank(grade)
        if rank is not None and rank >= 6:  # A, A+
            return True, f"BLOCKED: short leg {ticker} has trust_grade {grade} (rank {rank} >= 6)", score

    # ---- Soft adjustments ----

    # Phase C correlation break alignment
    for ticker in long_tickers:
        brk = correlation_breaks.get(ticker)
        if brk is None:
            continue
        trade_rec = (brk.get("trade_rec") or "").upper()
        if trade_rec in ("BUY", "LONG"):
            score += 8
        elif trade_rec in ("SELL", "SHORT"):
            score -= 8

    for ticker in short_tickers:
        brk = correlation_breaks.get(ticker)
        if brk is None:
            continue
        trade_rec = (brk.get("trade_rec") or "").upper()
        if trade_rec in ("SELL", "SHORT"):
            score += 8
        elif trade_rec in ("BUY", "LONG"):
            score -= 8

    # OI anomaly alignment
    for ticker in long_tickers:
        oi = oi_anomalies.get(ticker)
        if oi is None:
            continue
        anomaly_type = (oi.get("anomaly_type") or "").upper()
        sentiment = (oi.get("sentiment") or "").upper()
        if "CALL" in anomaly_type or sentiment == "BULLISH":
            score += 5
        elif "PUT" in anomaly_type or sentiment == "BEARISH":
            score -= 5

    for ticker in short_tickers:
        oi = oi_anomalies.get(ticker)
        if oi is None:
            continue
        anomaly_type = (oi.get("anomaly_type") or "").upper()
        sentiment = (oi.get("sentiment") or "").upper()
        if "PUT" in anomaly_type or sentiment == "BEARISH":
            score += 5
        elif "CALL" in anomaly_type or sentiment == "BULLISH":
            score -= 5

    # Regime hit_rate adjustment (applies to all tickers)
    all_tickers = long_tickers + short_tickers
    for ticker in all_tickers:
        rank_data = regime_rank.get(ticker)
        if rank_data is None:
            continue
        hr = rank_data.get("hit_rate")
        if hr is None:
            continue
        if hr > 0.55:
            score += min(10.0, (hr - 0.5) * 50)
        elif hr < 0.45:
            score -= min(10.0, (0.5 - hr) * 50)

    # Clamp
    score = max(0.0, min(100.0, score))

    return False, None, score


# ---------------------------------------------------------------------------
# Task 4: rescore_signal — live recompute for open signals (thesis-decay exit)
# ---------------------------------------------------------------------------

def rescore_signal(
    signal: Dict[str, Any],
    trust: Dict,
    breaks: Dict,
    profile: Dict,
    oi: Dict,
) -> Dict[str, Any]:
    """Recompute the conviction score for an already-open signal using
    today's enrichment inputs. Returns a rescore payload without mutating
    the input signal.

    Use case: every 15 min intraday, compare the live score to the frozen
    entry score to detect thesis decay (conviction-decay auto-exit).
    """
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    # Work on a copy so no mutation leaks back
    working = {**signal}
    working.pop("rescore", None)  # drop any prior rescore so enrich sees a clean slate

    try:
        enriched = enrich_signal(working, trust, breaks, profile, oi)
        blocked, reason, score = gate_signal(enriched)
    except Exception as exc:
        return {
            "current_score": None,
            "score_delta": None,
            "gate_reason_current": f"rescore_failed: {exc.__class__.__name__}",
            "gate_blocked_current": False,
            "rescored_at": datetime.now(ist).isoformat(),
        }

    entry_score = signal.get("entry_score") or signal.get("conviction_score") or 0
    return {
        "current_score": int(round(score)),
        "score_delta": int(round(entry_score - score)),
        "gate_reason_current": reason,
        "gate_blocked_current": blocked,
        "rescored_at": datetime.now(ist).isoformat(),
    }


# ---------------------------------------------------------------------------
# Task B7: apply_news_modifier — news verdict score delta
# ---------------------------------------------------------------------------

_IMPACT_MAGNITUDE: Dict[str, int] = {
    "HIGH_IMPACT": 10,
    "MODERATE": 5,
}

_SPREAD_CAP = 15


def _ticker_modifier(
    ticker: str,
    category: str,
    direction: str,
    verdicts: List[Dict[str, Any]],
) -> Tuple[int, Optional[str]]:
    """
    Return (delta, event_title) for a single ticker/category/direction triplet.

    Aligned:  ADD+LONG or CUT+SHORT  →  +magnitude
    Opposite: ADD+SHORT or CUT+LONG  →  -magnitude
    Everything else                  →  0
    """
    for v in verdicts:
        if v.get("symbol") != ticker:
            continue
        if v.get("category") != category:
            continue
        recommendation = (v.get("recommendation") or "").upper()
        impact = (v.get("impact") or "").upper()
        magnitude = _IMPACT_MAGNITUDE.get(impact, 0)
        if magnitude == 0:
            return 0, v.get("event_title")

        direction_up = direction.upper()
        if recommendation == "ADD":
            if direction_up == "LONG":
                return magnitude, v.get("event_title")
            elif direction_up == "SHORT":
                return -magnitude, v.get("event_title")
        elif recommendation == "CUT":
            if direction_up == "SHORT":
                return magnitude, v.get("event_title")
            elif direction_up == "LONG":
                return -magnitude, v.get("event_title")
        # NO_ACTION or other → 0
        return 0, v.get("event_title")
    return 0, None


def apply_news_modifier(
    signal: Dict[str, Any],
    verdicts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Annotate a signal dict with news_modifier and adjust entry_score.

    Returns a NEW dict (does not mutate input).  Works for both single-ticker
    signals (field ``ticker``) and spread signals (fields ``long_legs`` /
    ``short_legs``).

    Fields added to the returned signal:
      news_modifier         int   — net score delta (capped at ±15 for spreads)
      entry_score           num   — original + news_modifier
      news_context          str   — event_title for ticker signals (if matched)
      news_contributing_legs list — for spread signals, each matched leg's metadata
    """
    out = copy.deepcopy(signal)

    # --- Spread signal path ---
    long_legs: List[Dict] = signal.get("long_legs") or []
    short_legs: List[Dict] = signal.get("short_legs") or []

    is_spread = bool(long_legs or short_legs)

    if is_spread:
        total_delta = 0
        contributing: List[Dict[str, Any]] = []

        for leg in long_legs:
            # leg may be a plain string ticker OR a dict with "ticker" key
            if isinstance(leg, str):
                ticker = leg
                leg_category = signal.get("category") or ""
            else:
                ticker = leg.get("ticker") or ""
                leg_category = leg.get("category") or signal.get("category") or ""
            if not ticker:
                continue
            delta, title = _ticker_modifier(ticker, leg_category, "LONG", verdicts)
            if delta != 0:
                contributing.append({
                    "ticker": ticker,
                    "category": leg_category,
                    "direction": "LONG",
                    "delta": delta,
                    "event_title": title,
                })
            total_delta += delta

        for leg in short_legs:
            if isinstance(leg, str):
                ticker = leg
                leg_category = signal.get("category") or ""
            else:
                ticker = leg.get("ticker") or ""
                leg_category = leg.get("category") or signal.get("category") or ""
            if not ticker:
                continue
            delta, title = _ticker_modifier(ticker, leg_category, "SHORT", verdicts)
            if delta != 0:
                contributing.append({
                    "ticker": ticker,
                    "category": leg_category,
                    "direction": "SHORT",
                    "delta": delta,
                    "event_title": title,
                })
            total_delta += delta

        # Cap spread aggregate
        total_delta = max(-_SPREAD_CAP, min(_SPREAD_CAP, total_delta))

        out["news_modifier"] = total_delta
        out["entry_score"] = (out.get("entry_score") or 0) + total_delta
        out["news_contributing_legs"] = contributing
        return out

    # --- Single-ticker path ---
    ticker = signal.get("ticker") or ""
    category = signal.get("category") or ""
    direction = signal.get("direction") or ""

    if not ticker:
        out["news_modifier"] = 0
        return out

    delta, title = _ticker_modifier(ticker, category, direction, verdicts)
    out["news_modifier"] = delta
    out["entry_score"] = (out.get("entry_score") or 0) + delta
    if title:
        out["news_context"] = f"{ticker}: {title}"
    else:
        out.setdefault("news_context", "")
    return out
