import datetime as dt

import pytest

from pipeline.earnings_calendar.classifier import (
    EventKind,
    classify_board_meeting,
    extract_earnings_events,
)


def test_quarterly_results_short_form():
    out = classify_board_meeting("16-01-2026", "Quarterly Results")
    assert out is not None
    assert out["event_date"] == dt.date(2026, 1, 16)
    assert out["kind"] == EventKind.QUARTERLY_EARNINGS
    assert out["has_dividend"] is False
    assert out["has_fundraise"] is False


def test_audited_results_with_dividend_and_fundraise():
    agenda = (
        "Reliance Industries Ltd... consider and approve "
        "the standalone and consolidated audited financial results for the quarter and year ended March 31 2026; "
        "and recommend dividend on equity shares; "
        "raising of funds by way of issuance of redeemable non-convertible debentures"
    )
    out = classify_board_meeting("24-04-2026", agenda)
    assert out["kind"] == EventKind.QUARTERLY_EARNINGS
    assert out["has_dividend"] is True
    assert out["has_fundraise"] is True


def test_non_earnings_meeting_returns_none():
    out = classify_board_meeting(
        "29-08-2025",
        "Disclosure under Regulation 30 of the Securities and Exchange Board of India",
    )
    assert out is None


def test_invalid_date_raises():
    with pytest.raises(ValueError):
        classify_board_meeting("not-a-date", "Quarterly Results")


def test_extract_earnings_events_dedupes_same_date():
    payload = {
        "board_meetings": {
            "data": [
                ["16-01-2026", "Quarterly Results"],
                ["16-01-2026", "Quarterly Results Please find attached unaudited..."],
                ["29-08-2025", "Disclosure under Regulation 30"],
            ]
        }
    }
    out = extract_earnings_events("RELIANCE", payload)
    assert len(out) == 1
    assert out[0]["event_date"] == dt.date(2026, 1, 16)
    assert out[0]["symbol"] == "RELIANCE"


def test_extract_handles_missing_board_meetings_gracefully():
    assert extract_earnings_events("X", {}) == []
    assert extract_earnings_events("X", {"board_meetings": {}}) == []
    assert extract_earnings_events("X", {"board_meetings": {"data": []}}) == []


def test_extract_skips_malformed_rows():
    payload = {
        "board_meetings": {
            "data": [
                "not-a-list",
                ["only-one-element"],
                None,
                ["16-01-2026", "Quarterly Results"],
            ]
        }
    }
    out = extract_earnings_events("X", payload)
    assert len(out) == 1
    assert out[0]["event_date"] == dt.date(2026, 1, 16)


def test_classify_rejects_epoch_sentinel_date():
    """IndianAPI uses 01-01-1970 as a missing-date sentinel — must be quarantined
    even when the agenda matches the earnings pattern."""
    out = classify_board_meeting("01-01-1970", "Quarterly Results")
    assert out is None


def test_extract_skips_sentinel_dates():
    payload = {
        "board_meetings": {
            "data": [
                ["16-01-2026", "Quarterly Results"],
                ["01-01-1970", "Quarterly Results"],
            ]
        }
    }
    out = extract_earnings_events("X", payload)
    assert len(out) == 1
    assert out[0]["event_date"] == dt.date(2026, 1, 16)


def test_extract_sorted_descending_by_date():
    payload = {
        "board_meetings": {
            "data": [
                ["18-07-2025", "Quarterly Results for the quarter ended June 30 2025"],
                ["16-01-2026", "Quarterly Results"],
                ["17-10-2025", "Quarterly Results"],
            ]
        }
    }
    out = extract_earnings_events("X", payload)
    dates = [e["event_date"] for e in out]
    assert dates == sorted(dates, reverse=True)
