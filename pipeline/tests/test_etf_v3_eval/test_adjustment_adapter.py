from datetime import date
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.adjustment_adapter import (
    AdjustmentEvent,
    unadjust_eod_series,
)


def test_unadjust_applies_split_factor_backwards():
    """A 2-for-1 split on D=2025-06-15 means EOD CSV (auto-adjusted) shows pre-split
    closes scaled by 0.5. unadjust_eod_series multiplies pre-split rows by 2.0."""
    eod = pd.DataFrame({
        "trade_date": [date(2025, 6, 14), date(2025, 6, 15), date(2025, 6, 16)],
        "close": [100.0, 50.0, 52.0],
    })
    events = [AdjustmentEvent(symbol="X", event_date=date(2025, 6, 15), kind="split", ratio=2.0)]
    out = unadjust_eod_series(eod, events)
    # Pre-split row scaled back to unadjusted (200), event-day and post unchanged
    assert out["close"].tolist() == pytest.approx([200.0, 50.0, 52.0])


def test_unadjust_no_events_is_identity():
    eod = pd.DataFrame({"trade_date": [date(2025, 1, 1)], "close": [100.0]})
    out = unadjust_eod_series(eod, [])
    assert out["close"].tolist() == [100.0]


def test_unadjust_cumulative_events_compose_multiplicatively():
    """Two splits on the same ticker: pre-first-split rows must be scaled by both
    factors. e.g. a 2-for-1 on 06-15 then a 5-for-1 on 09-15 means a 06-14 close
    of 100 should land at 100 × 2 × 5 = 1000 unadjusted."""
    eod = pd.DataFrame({
        "trade_date": [date(2025, 6, 14), date(2025, 8, 1), date(2025, 9, 14), date(2025, 9, 15)],
        "close": [100.0, 50.0, 50.0, 10.0],
    })
    events = [
        AdjustmentEvent(symbol="X", event_date=date(2025, 6, 15), kind="split", ratio=2.0),
        AdjustmentEvent(symbol="X", event_date=date(2025, 9, 15), kind="split", ratio=5.0),
    ]
    out = unadjust_eod_series(eod, events)
    assert out["close"].tolist() == pytest.approx([1000.0, 250.0, 250.0, 10.0])


def test_unadjust_dividend_kind_is_no_op():
    eod = pd.DataFrame({
        "trade_date": [date(2025, 1, 1), date(2025, 1, 2)],
        "close": [100.0, 99.0],
    })
    events = [AdjustmentEvent(symbol="X", event_date=date(2025, 1, 2), kind="dividend", ratio=0.99)]
    out = unadjust_eod_series(eod, events)
    assert out["close"].tolist() == [100.0, 99.0]


def test_adjustment_event_rejects_non_positive_ratio():
    with pytest.raises(ValueError, match="must be > 0"):
        AdjustmentEvent(symbol="X", event_date=date(2025, 1, 1), kind="split", ratio=0.0)
    with pytest.raises(ValueError, match="must be > 0"):
        AdjustmentEvent(symbol="X", event_date=date(2025, 1, 1), kind="split", ratio=-1.0)
