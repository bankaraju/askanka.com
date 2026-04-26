"""§14 contamination map — count event-channel hits per ticker per trade_date."""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def _count_per_ticker_date(events: pd.DataFrame, ticker: str, day: date) -> int:
    if events.empty:
        return 0
    mask = (events["ticker"] == ticker) & (events["trade_date"] == day)
    return int(mask.sum())


def build_contamination_map(
    tickers: list[str],
    dates: list[date],
    bulk_deals: pd.DataFrame,
    insider: pd.DataFrame,
    news: pd.DataFrame,
    earnings: pd.DataFrame,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {ticker: {date_iso: {channel: count}}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for ticker in tickers:
        out[ticker] = {}
        for day in dates:
            iso = day.isoformat()
            out[ticker][iso] = {
                "bulk_deals": _count_per_ticker_date(bulk_deals, ticker, day),
                "insider": _count_per_ticker_date(insider, ticker, day),
                "news": _count_per_ticker_date(news, ticker, day),
                "earnings": _count_per_ticker_date(earnings, ticker, day),
            }
    return out
