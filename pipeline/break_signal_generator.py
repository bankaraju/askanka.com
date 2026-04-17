"""
break_signal_generator.py — Convert Phase C correlation breaks into signal candidates.

Reads pipeline/data/correlation_breaks.json and emits signal-shaped dicts for every
actionable break (trade_rec == "LONG" or "SHORT"). Breaks where trade_rec is None
are informational and are silently skipped.

The returned dicts match the open_signals.json schema so they can be passed directly
to signal_tracker.save_signal() for enrichment and persistence.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from signal_enrichment import BREAKS_PATH

logger = logging.getLogger(__name__)

_ACTIONABLE = {"LONG", "SHORT"}


def generate_break_candidates(breaks_path: Path = BREAKS_PATH) -> List[Dict[str, Any]]:
    """Return signal-shaped dicts for every actionable Phase C break.

    Only breaks where ``trade_rec`` is ``"LONG"`` or ``"SHORT"`` are included.
    Breaks with ``trade_rec=None`` (informational) are skipped.

    Args:
        breaks_path: Path to ``correlation_breaks.json``. Defaults to the
            canonical pipeline data location defined in ``signal_enrichment``.

    Returns:
        List of signal-shaped dicts ready for ``signal_tracker.save_signal()``,
        or ``[]`` when the file is missing, empty, or contains no actionable breaks.
    """
    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    if not breaks_path.exists():
        logger.debug("generate_break_candidates: file not found — %s", breaks_path)
        return []

    try:
        payload = json.loads(breaks_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("generate_break_candidates: failed to parse %s — %s", breaks_path, exc)
        return []

    breaks: List[Dict[str, Any]] = payload.get("breaks", [])
    scan_date: str = payload.get("date", "")
    scan_time: str = payload.get("scan_time", "")

    if not breaks:
        return []

    # ------------------------------------------------------------------
    # Convert
    # ------------------------------------------------------------------
    candidates: List[Dict[str, Any]] = []

    for brk in breaks:
        raw_rec = brk.get("trade_rec")
        # trade_rec can be a string ("LONG"/"SHORT"), a dict ({"direction": "SHORT", ...}), or None
        if isinstance(raw_rec, dict):
            trade_rec = raw_rec.get("direction")
        else:
            trade_rec = raw_rec
        if trade_rec not in _ACTIONABLE:
            continue  # informational — skip

        symbol: str = brk.get("symbol", "UNKNOWN")
        classification: str = brk.get("classification", "")
        z_score: float = brk.get("z_score", 0.0)
        expected_return: float = brk.get("expected_return", 0.0)
        actual_return: float = brk.get("actual_return", 0.0)
        regime: str | None = brk.get("regime")
        oi_anomaly: bool = bool(brk.get("oi_anomaly", False))

        yf_ticker = f"{symbol}.NS"
        leg = {"ticker": symbol, "yf": yf_ticker, "price": 0.0, "weight": 1.0}

        signal: Dict[str, Any] = {
            "signal_id": f"BRK-{scan_date}-{symbol}",
            "source": "CORRELATION_BREAK",
            "open_timestamp": scan_time,
            "status": "OPEN",
            "spread_name": f"Phase C: {symbol} {classification}",
            "category": "phase_c",
            "tier": "SIGNAL",
            "event_headline": (
                f"Phase C break on {symbol}: z={z_score}, "
                f"expected={expected_return}, actual={actual_return}"
            ),
            "hit_rate": None,
            "expected_1d_spread": expected_return,
            "long_legs": [leg] if trade_rec == "LONG" else [],
            "short_legs": [leg] if trade_rec == "SHORT" else [],
            "_break_metadata": {
                "symbol": symbol,
                "classification": classification,
                "z_score": z_score,
                "regime": regime,
                "oi_anomaly": oi_anomaly,
            },
        }
        candidates.append(signal)
        logger.debug(
            "generate_break_candidates: %s %s → signal %s",
            trade_rec,
            symbol,
            signal["signal_id"],
        )

    logger.info(
        "generate_break_candidates: %d actionable / %d total breaks",
        len(candidates),
        len(breaks),
    )
    return candidates
