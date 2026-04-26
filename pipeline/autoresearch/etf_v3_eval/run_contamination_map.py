"""Phase 2 contamination-map runner — join Kite-backfilled tickers with bulk-deals/insider/news/earnings.

Phase 2 wires news and earnings to their canonical on-disk paths (§14 caveat-b fix):
- News:     pipeline/data/news_events_history.json
- Earnings: pipeline/data/earnings_calendar/history.parquet
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.contamination_map import build_contamination_map
from pipeline.autoresearch.etf_v3_eval.phase_2.canonical_event_paths import (
    load_news_events_history,
    load_earnings_history,
    NEWS_HISTORY_PATH,
    EARNINGS_HISTORY_PATH,
)

logger = logging.getLogger(__name__)

MINUTE_PARQUET = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")
OUT = Path("pipeline/data/research/etf_v3_evaluation/phase_2_backtest/contamination_map_full.json")
BULK_DIR = Path("pipeline/data/bulk_deals")
INSIDER_DIR = Path("pipeline/data/insider_trades")


def _load_dir_parquets(dir_path: Path) -> pd.DataFrame:
    if not dir_path.exists():
        return pd.DataFrame()
    frames = [pd.read_parquet(p) for p in dir_path.glob("*.parquet")]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _normalize_event_frame(df: pd.DataFrame, ticker_col: str | None, date_col: str | None) -> pd.DataFrame:
    """Rename to canonical (ticker, trade_date); coerce date to datetime.date."""
    if df.empty:
        return df
    if ticker_col and ticker_col in df.columns and ticker_col != "ticker":
        df = df.rename(columns={ticker_col: "ticker"})
    if date_col and date_col in df.columns and date_col != "trade_date":
        df = df.rename(columns={date_col: "trade_date"})
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df = df.dropna(subset=["trade_date"])
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper()
    return df


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    minute = pd.read_parquet(MINUTE_PARQUET)
    tickers = sorted(minute["ticker"].unique())
    dates = sorted({d for d in minute["trade_date"].unique()})

    bulk = _normalize_event_frame(_load_dir_parquets(BULK_DIR), ticker_col="symbol", date_col="date")
    insider = _normalize_event_frame(_load_dir_parquets(INSIDER_DIR), ticker_col="symbol", date_col="intimation_date")
    news = _normalize_event_frame(load_news_events_history(NEWS_HISTORY_PATH), None, None)
    earnings = _normalize_event_frame(load_earnings_history(EARNINGS_HISTORY_PATH), None, None)
    logger.info("event-frame rows — bulk:%d insider:%d news:%d earnings:%d",
                len(bulk), len(insider), len(news), len(earnings))

    cm = build_contamination_map(tickers, list(dates), bulk, insider, news, earnings)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cm, indent=2, default=str), encoding="utf-8")
    n_hits = sum(1 for t in cm.values() for d in t.values() if any(d.values()))
    print(f"contamination map written: {OUT}")
    print(f"ticker-date pairs with >=1 channel hit: {n_hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
