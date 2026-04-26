"""Tests for §14 contamination map."""
from __future__ import annotations

from datetime import date

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.contamination_map import build_contamination_map


def test_map_records_bulk_deals_per_ticker_per_date() -> None:
    tickers = ["RELIANCE", "TCS"]
    dates = [date(2026, 4, 23)]
    bulk_deals = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "qty": [100000],
        "client": ["FII-A"],
    })
    insider = pd.DataFrame(columns=["ticker", "trade_date", "value"])
    news = pd.DataFrame(columns=["ticker", "trade_date", "headline"])
    earnings = pd.DataFrame(columns=["ticker", "trade_date", "event"])

    cm = build_contamination_map(tickers, dates, bulk_deals, insider, news, earnings)
    rel = cm["RELIANCE"]["2026-04-23"]
    assert rel["bulk_deals"] == 1
    assert rel["insider"] == 0
    assert rel["news"] == 0
    assert rel["earnings"] == 0
    tcs = cm["TCS"]["2026-04-23"]
    assert tcs["bulk_deals"] == 0


def test_map_returns_empty_when_no_events() -> None:
    cm = build_contamination_map(
        ["RELIANCE"], [date(2026, 4, 23)],
        pd.DataFrame(columns=["ticker", "trade_date", "qty", "client"]),
        pd.DataFrame(columns=["ticker", "trade_date", "value"]),
        pd.DataFrame(columns=["ticker", "trade_date", "headline"]),
        pd.DataFrame(columns=["ticker", "trade_date", "event"]),
    )
    assert cm["RELIANCE"]["2026-04-23"] == {"bulk_deals": 0, "insider": 0, "news": 0, "earnings": 0}
