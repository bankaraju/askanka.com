import json
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.canonical_event_paths import (
    load_news_events_history,
    load_earnings_history,
)


def test_load_news_events_history_emits_per_ticker_per_date(tmp_path):
    src = tmp_path / "news.json"
    src.write_text(json.dumps([
        {"matched_stocks": ["RELIANCE", "TCS"], "published": "Tue, 23 Apr 2026 13:26:31 +0530"},
        {"matched_stocks": ["RELIANCE"],        "published": "Wed, 24 Apr 2026 09:00:00 +0530"},
        {"matched_stocks": [],                   "published": "Thu, 25 Apr 2026 10:00:00 +0530"},
    ]), encoding="utf-8")
    out = load_news_events_history(src)
    assert set(out.columns) == {"ticker", "trade_date"}
    assert len(out) == 3   # 2 tickers from row 1 + 1 ticker from row 2 + 0 from row 3
    assert (out["ticker"] == "RELIANCE").sum() == 2
    assert out[out["ticker"] == "TCS"]["trade_date"].iloc[0] == date(2026, 4, 23)


def test_load_earnings_history_renames_to_canonical(tmp_path):
    src = tmp_path / "earnings.parquet"
    pd.DataFrame({
        "symbol": ["ABB"],
        "event_date": [date(2026, 4, 21)],
        "kind": ["results"],
        "has_dividend": [False],
        "has_fundraise": [False],
        "agenda_raw": ["x"],
        "asof": [date(2026, 4, 25)],
    }).to_parquet(src)
    out = load_earnings_history(src)
    assert {"ticker", "trade_date", "kind"}.issubset(out.columns)
    assert out["ticker"].iloc[0] == "ABB"
    assert out["trade_date"].iloc[0] == date(2026, 4, 21)


def test_load_news_events_history_missing_file_returns_empty():
    out = load_news_events_history(Path("/nonexistent/path/news.json"))
    assert list(out.columns) == ["ticker", "trade_date"]
    assert len(out) == 0


def test_load_earnings_history_missing_file_returns_empty():
    out = load_earnings_history(Path("/nonexistent/path/earnings.parquet"))
    assert {"ticker", "trade_date", "kind"}.issubset(out.columns)
    assert len(out) == 0
