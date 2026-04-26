"""Tests for missing-ticker identification."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.missing_tickers import (
    list_canonical_fno_tickers,
    list_replay_tickers,
    compute_missing,
)


def test_list_canonical_fno_tickers_returns_strings(tmp_path: Path) -> None:
    canon_file = tmp_path / "canon.json"
    canon_file.write_text('{"tickers": ["RELIANCE", "TCS", "INFY"]}', encoding="utf-8")
    result = list_canonical_fno_tickers(canon_file)
    assert result == ["RELIANCE", "TCS", "INFY"]


def test_list_replay_tickers_returns_unique_set(tmp_path: Path) -> None:
    parquet = tmp_path / "replay.parquet"
    pd.DataFrame({"ticker": ["TCS", "TCS", "INFY"], "trade_date": ["2026-01-01"] * 3}).to_parquet(parquet)
    result = list_replay_tickers(parquet)
    assert sorted(result) == ["INFY", "TCS"]


def test_compute_missing_returns_canon_minus_replay() -> None:
    canon = ["RELIANCE", "TCS", "INFY"]
    replay = ["TCS", "INFY"]
    assert compute_missing(canon, replay) == ["RELIANCE"]
