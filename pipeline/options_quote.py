"""Options-quote fetch + liquidity gate for Phase C paired-shadow sidecar.

One Kite quote() call → OptionsQuote with bid/ask/mid/spread_pct and a
liquidity_passed flag (5% spread floor). Skip reasons enumerated:
WIDE_SPREAD / NO_BID / NO_ASK.

Spec: docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md §6.3
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))
LIQUIDITY_SPREAD_THRESHOLD: float = 0.05


@dataclass(frozen=True)
class OptionsQuote:
    instrument_token: int
    bid: float
    ask: float
    mid: float
    spread_pct: float
    last_price: float
    timestamp: datetime
    liquidity_passed: bool
    skip_reason: Optional[str]


def _parse_kite_timestamp(ts) -> datetime:
    """Kite timestamp arrives as 'YYYY-MM-DD HH:MM:SS' (IST, naive) or as a
    datetime already. Always return a tz-aware IST datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=IST)
        return ts
    if isinstance(ts, str):
        try:
            naive = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return naive.replace(tzinfo=IST)
        except ValueError:
            pass
    return datetime.now(IST)


def fetch_mid_with_liquidity_check(
    kite_client, instrument_token: int
) -> OptionsQuote:
    raw = kite_client.quote([instrument_token])
    payload = raw.get(instrument_token)
    if payload is None:
        payload = raw.get(str(instrument_token))
    if payload is None:
        raise KeyError(
            f"Kite quote response missing key {instrument_token!r}; "
            f"keys returned: {list(raw.keys())}"
        )

    last_price = float(payload.get("last_price", 0.0) or 0.0)
    timestamp = _parse_kite_timestamp(payload.get("timestamp"))
    depth = payload.get("depth", {}) or {}
    buy = depth.get("buy", []) or []
    sell = depth.get("sell", []) or []
    bid = float(buy[0].get("price", 0.0)) if buy else 0.0
    ask = float(sell[0].get("price", 0.0)) if sell else 0.0

    if bid <= 0:
        # mid best-effort: last_price if available
        mid = last_price if last_price > 0 else (
            (bid + ask) / 2 if ask > 0 else float("nan")
        )
        return OptionsQuote(
            instrument_token=instrument_token, bid=bid, ask=ask, mid=mid,
            spread_pct=float("nan"), last_price=last_price,
            timestamp=timestamp, liquidity_passed=False, skip_reason="NO_BID",
        )
    if ask <= 0:
        mid = last_price if last_price > 0 else bid
        return OptionsQuote(
            instrument_token=instrument_token, bid=bid, ask=ask, mid=mid,
            spread_pct=float("nan"), last_price=last_price,
            timestamp=timestamp, liquidity_passed=False, skip_reason="NO_ASK",
        )

    mid = (bid + ask) / 2.0
    spread_pct = (ask - bid) / mid if mid > 0 else float("nan")
    if spread_pct > LIQUIDITY_SPREAD_THRESHOLD:
        return OptionsQuote(
            instrument_token=instrument_token, bid=bid, ask=ask, mid=mid,
            spread_pct=spread_pct, last_price=last_price,
            timestamp=timestamp, liquidity_passed=False, skip_reason="WIDE_SPREAD",
        )
    return OptionsQuote(
        instrument_token=instrument_token, bid=bid, ask=ask, mid=mid,
        spread_pct=spread_pct, last_price=last_price,
        timestamp=timestamp, liquidity_passed=True, skip_reason=None,
    )
