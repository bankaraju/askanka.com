"""Daily Top-10 ranker. Joins today's flags against pattern_stats.parquet,
filters by minimum-N + fold-stability gates, ranks by composite score.

Per spec section 6.3.
"""
import math
from dataclasses import dataclass
from datetime import date as _date
from typing import Literal

import pandas as pd

from pipeline.pattern_scanner.constants import MIN_N, MIN_FOLD_STABILITY, TOP_N
from pipeline.pattern_scanner.detect import PatternFlag


@dataclass
class ScannerSignal:
    signal_id: str
    date: _date
    ticker: str
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    composite_score: float
    n_occurrences: int
    win_rate: float
    z_score: float
    mean_pnl_pct: float
    fold_stability: float
    last_seen: _date


def _composite(z: float, n: int, mean_pnl: float) -> float:
    if n <= 0 or pd.isna(z) or pd.isna(mean_pnl):
        return float("-inf")
    return z * math.log1p(n) * abs(mean_pnl)


def rank_today(
    flags: list[PatternFlag],
    stats: pd.DataFrame,
    min_n: int = MIN_N,
    min_fold_stability: float = MIN_FOLD_STABILITY,
    top_n: int = TOP_N,
) -> list[ScannerSignal]:
    if not flags:
        return []
    if stats is None or stats.empty:
        return []

    indexed = stats.set_index(["ticker", "pattern_id"])
    out: list[ScannerSignal] = []
    for f in flags:
        try:
            row = indexed.loc[(f.ticker, f.pattern_id)]
        except KeyError:
            continue
        n = int(row["n_occurrences"]) if not pd.isna(row["n_occurrences"]) else 0
        if n < min_n:
            continue
        fs = float(row["fold_stability"])
        if fs < min_fold_stability:
            continue
        z = float(row["z_score"])
        mean_pnl = float(row["mean_pnl_pct"])
        composite = _composite(z, n, mean_pnl)
        if not math.isfinite(composite):
            continue
        last_seen = row["last_seen"]
        if hasattr(last_seen, "date"):
            last_seen = last_seen.date()
        out.append(ScannerSignal(
            signal_id=f"{f.date.isoformat()}_{f.ticker}_{f.pattern_id}",
            date=f.date,
            ticker=f.ticker,
            pattern_id=f.pattern_id,
            direction=f.direction,
            composite_score=composite,
            n_occurrences=n,
            win_rate=float(row["win_rate"]),
            z_score=z,
            mean_pnl_pct=mean_pnl,
            fold_stability=fs,
            last_seen=last_seen,
        ))
    out.sort(key=lambda s: s.composite_score, reverse=True)
    return out[:top_n]
