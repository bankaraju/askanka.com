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


def test_eod_loader_calls_unadjuster(monkeypatch, tmp_path):
    """The run_reconciliation EOD loader, when an adjustment-event source is
    supplied, applies unadjust_eod_series to each ticker frame before merge.
    Asserts BOTH directions: pre-event row scaled, post-event row unchanged."""
    from pipeline.autoresearch.etf_v3_eval import run_reconciliation as rr

    csv = tmp_path / "X.csv"
    pd.DataFrame({"Date": ["2025-06-14", "2025-06-15"], "Close": [100.0, 50.0]}).to_csv(csv, index=False)
    monkeypatch.setattr(rr, "EOD_DIR", tmp_path)

    events_by_ticker = {"X": [AdjustmentEvent("X", date(2025, 6, 15), "split", 2.0)]}
    out = rr.load_eod_for_tickers(["X"], events_by_ticker=events_by_ticker)
    assert out.loc[out["trade_date"] == date(2025, 6, 14), "close"].iloc[0] == 200.0
    assert out.loc[out["trade_date"] == date(2025, 6, 15), "close"].iloc[0] == 50.0


def test_parse_ratio_split_uses_new_over_old():
    """A 5:1 split (5 new shares for every 1 old) should multiply pre-event by 5."""
    from pipeline.autoresearch.etf_v3_eval.run_reconciliation import _parse_ratio_from_text
    assert _parse_ratio_from_text("Stock Split 5:1", "split") == 5.0
    assert _parse_ratio_from_text("Sub-Division 10:2", "split") == 5.0


def test_parse_ratio_bonus_uses_total_over_old():
    """A 1:1 bonus DOUBLES share count, so pre-event prices ×2 not ×1.
    A 3:5 bonus → (3+5)/5 = 1.6, NOT 3/5 = 0.6 (which would invert direction)."""
    from pipeline.autoresearch.etf_v3_eval.run_reconciliation import _parse_ratio_from_text
    assert _parse_ratio_from_text("Bonus 1:1", "bonus") == 2.0
    assert _parse_ratio_from_text("Bonus issue 3:5", "bonus") == pytest.approx(1.6)
    assert _parse_ratio_from_text("Bonus 2:1", "bonus") == 3.0


def test_parse_ratio_returns_none_for_unparseable():
    from pipeline.autoresearch.etf_v3_eval.run_reconciliation import _parse_ratio_from_text
    assert _parse_ratio_from_text("Quarterly Results", "split") is None
    assert _parse_ratio_from_text("Stock Split From Rs 10 To Rs 2", "split") is None  # word-form, no m:n
    assert _parse_ratio_from_text("Bonus 1:1", "unknown_kind") is None  # unrecognised kind
