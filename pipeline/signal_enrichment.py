"""
signal_enrichment.py — Load 4 rigour JSON files and expose per-ticker lookup helpers.

Loaders never raise on missing or corrupt files; they return an empty dict instead.
Task 1 of the signal-enrichment wiring initiative.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent

TRUST_PATH = _REPO_ROOT / "opus" / "artifacts" / "model_portfolio.json"
BREAKS_PATH = _REPO_ROOT / "pipeline" / "data" / "correlation_breaks.json"
REGIME_PROFILE_PATH = _REPO_ROOT / "pipeline" / "autoresearch" / "reverse_regime_profile.json"
OI_ANOMALIES_PATH = _REPO_ROOT / "pipeline" / "data" / "oi_anomalies.json"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_trust_scores(path: Path = TRUST_PATH) -> Dict[str, Dict]:
    """
    Load OPUS Trust Scores from model_portfolio.json.

    Returns a dict keyed by symbol:
        {trust_grade, trust_score, opus_side, thesis}
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        positions = raw.get("positions", [])
        result: Dict[str, Dict] = {}
        for pos in positions:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            result[symbol] = {
                "trust_grade": pos.get("trust_grade"),
                "trust_score": pos.get("trust_score"),
                "opus_side": pos.get("side"),
                "thesis": pos.get("thesis"),
            }
        return result
    except FileNotFoundError:
        logger.debug("load_trust_scores: file not found — %s", path)
        return {}
    except Exception as exc:
        logger.warning("load_trust_scores: failed to load %s — %s", path, exc)
        return {}


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
