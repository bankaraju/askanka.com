"""Single accessor for canonical_fno_research_v1 + daily F&O CSVs + sectoral indices.

No second cache, no parallel fetcher — this is the only path through which
the replay sees the canonical dataset registered at
docs/superpowers/specs/2026-04-25-canonical-fno-research-dataset-audit.md.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C


class CanonicalLoader:
    def __init__(self, canonical_path: Path = C.CANONICAL_JSON):
        raw = json.loads(canonical_path.read_text(encoding="utf-8"))
        self._tickers: set[str] = set(raw["tickers"])
        self._valid_from: dict[str, str] = raw["per_ticker_valid_from"]
        self._valid_to: dict[str, str] = raw["per_ticker_valid_to"]
        self._adjustment_mode = raw["adjustment_mode"]
        self._dataset_id = raw["dataset_id"]
        self._bars_cache: dict[str, pd.DataFrame] = {}
        self._sector_cache: dict[str, pd.DataFrame] = {}

    @property
    def universe(self) -> set[str]:
        return self._tickers

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def adjustment_mode(self) -> dict:
        return self._adjustment_mode

    def is_in_universe(self, ticker: str, d: date) -> bool:
        if ticker not in self._tickers:
            return False
        vf = pd.to_datetime(self._valid_from[ticker]).date()
        vt = pd.to_datetime(self._valid_to[ticker]).date()
        return vf <= d <= vt

    def daily_bars(self, ticker: str) -> pd.DataFrame:
        if ticker in self._bars_cache:
            return self._bars_cache[ticker]
        path = C.FNO_DAILY_DIR / f"{ticker}.csv"
        df = pd.read_csv(path)
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values("date").reset_index(drop=True)
        self._bars_cache[ticker] = df
        return df

    def sector_bars(self, index_name: str) -> pd.DataFrame:
        if index_name in self._sector_cache:
            return self._sector_cache[index_name]
        path = C.SECTORAL_DIR / f"{index_name}_daily.csv"
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.sort_values("date").reset_index(drop=True)
        self._sector_cache[index_name] = df
        return df
