"""
break_signal_generator.py — Convert Phase C correlation breaks into signal candidates.

Reads pipeline/data/correlation_breaks.json and emits signal-shaped dicts for every
actionable break meeting TWO criteria:
  1. trade_rec ∈ {LONG, SHORT}
  2. classification ∈ {OPPORTUNITY_LAG}

Breaks where trade_rec is None, or where classification is OPPORTUNITY_OVERSHOOT,
WARNING, CONFIRMED_WARNING, UNCERTAIN, or legacy bare OPPORTUNITY, are skipped.
These are informational — see docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md
for the compliance gate.

The returned dicts match the open_signals.json schema so they can be passed directly
to signal_tracker.save_signal() for enrichment and persistence.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from signal_enrichment import BREAKS_PATH
from atr_stops import compute_atr_stop
from config import TIER_EXPLORING

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
# Hard cutoff for opening NEW Phase C break positions. After 14:30 IST the
# mechanical TIME_STOP closes anything we'd open within minutes, so the trade
# is not realistically tradeable. Existing positions are still monitored.
NEW_SIGNAL_CUTOFF_IST = time(14, 30)


def _now_ist_time() -> time:
    """Return current IST wall-clock time. Indirection so tests can patch it."""
    return datetime.now(_IST).time()

_ACTIONABLE_DIRECTIONS = {"LONG", "SHORT"}
_ACTIONABLE_CLASSIFICATIONS = {"OPPORTUNITY_LAG"}
# OPPORTUNITY_OVERSHOOT and legacy bare OPPORTUNITY are informational only —
# see docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md
# §3.1 and §4.1. They become actionable only after H-2026-04-23-003 FADE
# hypothesis passes compliance.

# Backward compatibility alias (deprecated)
_ACTIONABLE = _ACTIONABLE_DIRECTIONS


def generate_break_candidates(breaks_path: Path = BREAKS_PATH) -> List[Dict[str, Any]]:
    """Return signal-shaped dicts for every actionable Phase C break.

    Only breaks meeting BOTH criteria are included:
      1. ``trade_rec`` ∈ {``"LONG"``, ``"SHORT"``}
      2. ``classification`` ∈ {``"OPPORTUNITY_LAG"``}

    Breaks not meeting either criterion (including ``trade_rec=None``,
    ``classification="OPPORTUNITY_OVERSHOOT"``, legacy bare ``"OPPORTUNITY"``, etc.)
    are skipped as informational.

    Args:
        breaks_path: Path to ``correlation_breaks.json``. Defaults to the
            canonical pipeline data location defined in ``signal_enrichment``.

    Returns:
        List of signal-shaped dicts ready for ``signal_tracker.save_signal()``,
        or ``[]`` when the file is missing, empty, or contains no actionable breaks.
    """
    # ------------------------------------------------------------------
    # 14:30 IST hard cutoff — defensive at the source.
    # ------------------------------------------------------------------
    now_t = _now_ist_time()
    if now_t >= NEW_SIGNAL_CUTOFF_IST:
        logger.info(
            "generate_break_candidates: skipping — current time %s past "
            "14:30 IST new-signal cutoff",
            now_t.strftime("%H:%M"),
        )
        return []

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
        if trade_rec not in _ACTIONABLE_DIRECTIONS:
            continue  # trade_rec missing or non-directional — skip

        classification: str = brk.get("classification", "")
        if classification not in _ACTIONABLE_CLASSIFICATIONS:
            continue  # classification not actionable (OVERSHOOT alert-only,
                      # WARNING defensive, legacy OPPORTUNITY deprecated)

        symbol: str = brk.get("symbol", "UNKNOWN")
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
            # Phase C tier is EXPLORING (research/forward-test) following the
            # H-2026-04-23-001 compliance FAIL (zero survivors at Bonferroni
            # 1.17e-4). These signals remain tracked at 0.5 unit sizing for
            # forward scorecarding; promotion to SIGNAL requires 20+ closed
            # trades with >=65% win rate per config.TIER_PROMOTION_*.
            "tier": TIER_EXPLORING,
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
                "event_geometry": brk.get("event_geometry"),
                "direction_intended": brk.get("direction_intended"),
                "direction_tested": brk.get("direction_tested"),
                "direction_consistent": brk.get("direction_consistent"),
                "z_score": z_score,
                "regime": regime,
                "oi_anomaly": oi_anomaly,
            },
        }
        # 2026-04-27: aligned with H-001 paper rules (mult=2.0, no cap) so the
        # broad open_signals ledger and the H-001 holdout produce comparable
        # P&L. Combined with the new 14:30 TIME_STOP in signal_tracker, this
        # gives Phase C correlation-break trades a single rule set across both
        # forward-test surfaces. Prior version (1×ATR + 3.5% cap) is preserved
        # in git history if a tighter intraday stop is wanted later.
        signal["_atr_stop"] = compute_atr_stop(
            symbol, direction=trade_rec, mult=2.0,
        )
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
