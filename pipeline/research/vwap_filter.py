"""VWAP-deviation filter — display-only tag for sigma-break entries.

At 09:30 IST signal time, fetch the first ~15 minutes of 1-min bars,
compute VWAP and price-at-09:30, signed by trade direction:

    vwap_dev_signed = (price@0930 - vwap_first15) / vwap_first15
                       × (+1 if LONG else -1)

A high positive value means the stock has already extended past VWAP
in the trade's intended direction — a "late" entry. The 2026-04-29
NEUTRAL cohort tracker showed:

    bottom tertile (LO):    77% wins (n=35)  ← EARLY (took position before/early in the move)
    middle tertile (MID):   63% wins (n=35)  ← EARLY
    top tertile (HI):       37% wins (n=35)  ← LATE  (took position after rally already started)

Cut points are FROZEN here so live entry tagging is reproducible. They
were derived from the 105-row 2026-04-27..29 NEUTRAL forward sample.
The cohort tracker re-fits cuts on growing sample for evidence; this
module's cuts only update on a pre-registered hypothesis swap.

2026-04-30 LABEL RENAME (commercial-readability):
    KEEP → EARLY
    DROP → LATE
    WATCH → N/A
The old labels read like P&L verdicts ("DROP = drop this trade"). The new
labels describe WHEN you entered relative to the move. Cut points and
tertile assignments are unchanged — this is a metadata-only rename per
backtesting-specs §14, not a §10.4 parameter change. Old CSV rows tagged
KEEP/DROP/WATCH are still readable and the UI normalizes them at display
time so historical and live rows show consistent vocabulary.

Per backtesting-specs §10.4 strict, the filter is DISPLAY-ONLY during
the H-001 holdout window (until 2026-05-26). It tags every row but
does not gate trade entry.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("anka.vwap_filter")

_IST = timezone(timedelta(hours=5, minutes=30))

# Frozen tertile cuts from 2026-04-29 NEUTRAL cohort sample (n=105).
# vwap_dev_signed in raw units (e.g. +0.0036 = price 0.36% past VWAP in trade direction).
VWAP_DEV_SIGNED_LO_CUT = -0.0008
VWAP_DEV_SIGNED_HI_CUT = +0.0036

EARLY = "EARLY"    # LO + MID tertiles — entered before/early in the move
LATE = "LATE"      # HI tertile — entered after rally already extended
NA = "N/A"         # data unavailable — neither EARLY nor LATE

# Backward-compat aliases for the on-disk values written by code paths that
# pre-date this rename. Anything reading the CSV ledgers should normalize
# via normalize_legacy_tag() before display. Do not remove until every row
# in every active ledger has been written under the new vocabulary (estimate
# 2026-05-26, end of H-001 holdout window).
_LEGACY_TO_NEW = {
    "KEEP": EARLY,
    "DROP": LATE,
    "WATCH": NA,
}


def normalize_legacy_tag(tag: Optional[str]) -> Optional[str]:
    """Map any legacy KEEP/DROP/WATCH value to the new EARLY/LATE/N/A label.

    Called at the API boundary so historical CSV rows display consistently
    with newly-written rows. New labels pass through unchanged.
    """
    if not tag:
        return tag
    return _LEGACY_TO_NEW.get(tag, tag)


def classify(vwap_dev_signed: Optional[float]) -> str:
    if vwap_dev_signed is None:
        return NA
    if vwap_dev_signed >= VWAP_DEV_SIGNED_HI_CUT:
        return LATE
    return EARLY


# ---------------------------------------------------------------------------
# Legacy export aliases — kept so any out-of-tree caller importing
# `KEEP/DROP/WATCH` continues to work. Internal callers should use the new
# names directly.
# ---------------------------------------------------------------------------
KEEP = EARLY
DROP = LATE
WATCH = NA


def compute_vwap_dev_signed(
    symbol: str,
    side: str,
    as_of_dt: Optional[datetime] = None,
    n_minutes: int = 15,
) -> Optional[float]:
    """Compute VWAP-deviation signed by side for ``symbol``.

    Returns None if minute bars are unavailable or insufficient (<n_minutes).
    Otherwise returns vwap_dev_signed in raw decimal (not percent).

    Pulls today's minute bars via ``pipeline.kite_client.fetch_historical``
    with interval='minute', days=1. For the live 09:30 OPEN call, this
    yields bars from 09:15 → present, of which we use the first
    ``n_minutes``.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")

    from pipeline.kite_client import fetch_historical

    try:
        bars = fetch_historical(symbol, interval="minute", days=1)
    except Exception as exc:
        log.warning("fetch_historical failed for %s: %s", symbol, exc)
        return None

    if not bars:
        log.warning("no minute bars returned for %s", symbol)
        return None

    today = (as_of_dt or datetime.now(_IST)).date().isoformat()
    today_bars = [b for b in bars if str(b.get("date", ""))[:10] == today]
    if len(today_bars) < n_minutes:
        log.info(
            "only %d of %d required minute bars for %s on %s — WATCH",
            len(today_bars), n_minutes, symbol, today,
        )
        return None

    first15 = today_bars[:n_minutes]
    total_pv = 0.0
    total_v = 0.0
    last_close = None
    for b in first15:
        close = float(b["close"])
        vol = float(b["volume"])
        total_pv += close * vol
        total_v += vol
        last_close = close

    if total_v <= 0 or last_close is None:
        log.info("zero volume or missing close for %s — WATCH", symbol)
        return None

    vwap = total_pv / total_v
    if vwap <= 0:
        return None

    raw_dev = (last_close - vwap) / vwap
    sign = 1.0 if side == "LONG" else -1.0
    return raw_dev * sign


def compute_filter_tag(
    symbol: str,
    side: str,
    as_of_dt: Optional[datetime] = None,
) -> tuple[Optional[float], str]:
    """Return (vwap_dev_signed, tag) for live OPEN tagging.

    tag is one of KEEP, DROP, WATCH. WATCH means data unavailable —
    callers should treat as "no decision," not as "skip."
    """
    dev = compute_vwap_dev_signed(symbol, side, as_of_dt=as_of_dt)
    return dev, classify(dev)
