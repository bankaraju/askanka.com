"""Top-N stocks by 60-day mean traded value per sector.

Pure function over fno_historical CSVs and a sector map.
Used by `forward_shadow.cmd_basket_open` to pick reproducible top-2
stocks per sector at 11:00 IST.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

WINDOW_DAYS = 60


def top_n_by_traded_value(
    *,
    sector_target: str,
    sector_map: Mapping[str, str],
    fno_hist_dir: Path,
    universe: Iterable[str],
    n: int = 2,
    window_days: int = WINDOW_DAYS,
) -> list[str]:
    """Return up to n tickers in `sector_target` with highest mean
    traded value (Volume * Close) over the most recent `window_days`
    trading days available in fno_historical/<TICKER>.csv.

    A ticker is excluded if:
      - it's not in `universe`
      - it's not mapped to `sector_target`
      - its CSV is missing or has < window_days rows
      - any of Volume / Close is non-positive across the entire window
    """
    eligible = [t for t in universe if sector_map.get(t) == sector_target]
    scores: list[tuple[str, float]] = []
    for tkr in eligible:
        path = fno_hist_dir / f"{tkr}.csv"
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path, parse_dates=["Date"])
        except (ValueError, OSError):
            continue
        if df.empty or len(df) < window_days:
            continue
        df = df.sort_values("Date").tail(window_days)
        if (df["Volume"] <= 0).all() or (df["Close"] <= 0).all():
            continue
        traded_value = (df["Volume"] * df["Close"]).mean()
        if traded_value <= 0:
            continue
        scores.append((tkr, float(traded_value)))

    scores.sort(key=lambda kv: kv[1], reverse=True)
    return [tkr for tkr, _ in scores[:n]]
