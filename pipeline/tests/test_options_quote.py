"""Unit tests for pipeline.options_quote — Phase C paired-shadow T2."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import math
import pytest

from pipeline.options_quote import (
    OptionsQuote,
    LIQUIDITY_SPREAD_THRESHOLD,
    fetch_mid_with_liquidity_check,
)


IST = timezone(timedelta(hours=5, minutes=30))


def _quote_payload(bid: float, ask: float, last: float = 120.0):
    """Construct a Kite-quote-shaped dict response."""
    return {
        "instrument_token": 12345678,
        "last_price": last,
        "timestamp": "2026-04-29 09:35:12",
        "depth": {
            "buy":  [{"price": bid, "quantity": 250, "orders": 1}],
            "sell": [{"price": ask, "quantity": 250, "orders": 1}],
        },
        "oi": 12345,
        "volume": 67890,
    }


def test_constant_is_five_percent():
    assert LIQUIDITY_SPREAD_THRESHOLD == 0.05


def test_normal_quote_passes_liquidity():
    kite = MagicMock()
    kite.quote.return_value = {12345678: _quote_payload(bid=119.5, ask=122.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.bid == 119.5
    assert out.ask == 122.0
    assert math.isclose(out.mid, 120.75)
    assert math.isclose(out.spread_pct, 2.5 / 120.75, rel_tol=1e-9)
    assert out.liquidity_passed is True
    assert out.skip_reason is None


def test_wide_spread_fails_liquidity():
    kite = MagicMock()
    kite.quote.return_value = {12345678: _quote_payload(bid=110.0, ask=130.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is False
    assert out.skip_reason == "WIDE_SPREAD"
    # Mid still computed
    assert math.isclose(out.mid, 120.0)


def test_no_bid_fails_liquidity():
    kite = MagicMock()
    kite.quote.return_value = {12345678: _quote_payload(bid=0.0, ask=122.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is False
    assert out.skip_reason == "NO_BID"
    assert out.bid == 0.0
    assert out.ask == 122.0


def test_no_ask_fails_liquidity():
    kite = MagicMock()
    kite.quote.return_value = {12345678: _quote_payload(bid=119.5, ask=0.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is False
    assert out.skip_reason == "NO_ASK"


def test_string_keyed_response_works():
    """Kite SDK sometimes returns string-keyed dict; we fall back."""
    kite = MagicMock()
    kite.quote.return_value = {"12345678": _quote_payload(bid=119.5, ask=122.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is True
    assert math.isclose(out.mid, 120.75)


def test_kite_exception_propagates():
    """Session / API errors must surface to caller."""
    kite = MagicMock()
    kite.quote.side_effect = RuntimeError("Token expired")
    with pytest.raises(RuntimeError, match="Token expired"):
        fetch_mid_with_liquidity_check(kite, 12345678)


def test_timestamp_is_tz_aware_ist():
    kite = MagicMock()
    kite.quote.return_value = {12345678: _quote_payload(bid=119.5, ask=122.0)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.timestamp.tzinfo is not None
    # IST = UTC+5:30
    assert out.timestamp.utcoffset() == timedelta(hours=5, minutes=30)


def test_threshold_boundary_exact_five_percent_passes():
    """At exactly 5.0% spread, liquidity_passed must remain True (≤ 5%)."""
    kite = MagicMock()
    # bid=97.5, ask=102.5 → mid=100, spread=5, spread_pct=0.05
    kite.quote.return_value = {12345678: _quote_payload(bid=97.5, ask=102.5)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is True
    assert math.isclose(out.spread_pct, 0.05)


def test_just_over_threshold_fails():
    """Spread 5.01% must fail."""
    kite = MagicMock()
    # bid=97.4, ask=102.6 → mid=100, spread=5.2, spread_pct=0.052
    kite.quote.return_value = {12345678: _quote_payload(bid=97.4, ask=102.6)}
    out = fetch_mid_with_liquidity_check(kite, 12345678)
    assert out.liquidity_passed is False
    assert out.skip_reason == "WIDE_SPREAD"


def test_options_quote_is_immutable():
    """OptionsQuote must be a frozen dataclass."""
    q = OptionsQuote(
        instrument_token=1, bid=1.0, ask=2.0, mid=1.5, spread_pct=0.5,
        last_price=1.5, timestamp=datetime.now(IST),
        liquidity_passed=False, skip_reason="WIDE_SPREAD",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        q.bid = 2.0  # type: ignore
