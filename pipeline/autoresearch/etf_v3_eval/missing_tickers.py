"""Identify F&O tickers in canonical universe but not yet in 60-day replay."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def list_canonical_fno_tickers(path: Path) -> list[str]:
    """Read canonical_fno_research_v3.json and return ticker list."""
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "tickers" in data:
        return [str(t).upper() for t in data["tickers"]]
    if isinstance(data, list):
        return [str(t).upper() for t in data]
    if isinstance(data, dict):
        return [str(t).upper() for t in data.keys()]
    raise ValueError(f"Unrecognized canonical universe format: {type(data)}")


def list_replay_tickers(path: Path) -> list[str]:
    """Read intraday-break replay parquet and return unique ticker list."""
    df = pd.read_parquet(path)
    return sorted({str(t).upper() for t in df["ticker"].unique()})


def compute_missing(canonical: list[str], replay: list[str]) -> list[str]:
    """Return tickers in canonical but not in replay, sorted."""
    return sorted(set(canonical) - set(replay))
