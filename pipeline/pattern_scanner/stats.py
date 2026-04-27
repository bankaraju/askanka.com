"""Historical pattern-occurrence stats. Reads daily bars per ticker, finds every
pattern fire over the lookback window, computes T+1 open-to-close return per
fire, aggregates per (ticker, pattern). Walk-forward fold stability via 4
contiguous folds.

Per spec section 6.2 + 10.
"""
import math
from collections.abc import Callable
from datetime import date as _date
from typing import Literal

import numpy as np
import pandas as pd

from pipeline.pattern_scanner.constants import PATTERNS, WIN_THRESHOLD
from pipeline.pattern_scanner.detect import detect_patterns_for_ticker


def compute_z_score(win_rate: float, n: int) -> float:
    """Binomial test against H0=50/50."""
    if n <= 0:
        return float("nan")
    se = math.sqrt(0.25 / n)
    return (win_rate - 0.5) / se


def walk_forward_fold_stability(fold_win_rates: list[float]) -> float:
    """1 - (max - min) / max(0.01, mean). Bounded [0, 1]; higher = more stable."""
    if not fold_win_rates:
        return 0.0
    mean = float(np.mean(fold_win_rates))
    if mean <= 0:
        return 0.0
    spread = max(fold_win_rates) - min(fold_win_rates)
    ratio = 1.0 - spread / max(0.01, mean)
    return max(0.0, min(1.0, ratio))


def aggregate_pattern_cell(
    ticker: str,
    pattern_id: str,
    direction: Literal["LONG", "SHORT"],
    fire_dates: list[_date],
    returns: list[float],
    win_threshold: float = WIN_THRESHOLD,
) -> dict:
    """Aggregate one (ticker, pattern) cell from a list of fire dates and their
    T+1 returns. Returns are RAW (not signed). For SHORT patterns, P&L = -return.
    """
    if len(fire_dates) != len(returns):
        raise ValueError("fire_dates and returns must be the same length")

    pnl = np.array(returns, dtype=float)
    if direction == "SHORT":
        pnl = -pnl

    n = len(pnl)
    if n == 0:
        return {
            "ticker": ticker, "pattern_id": pattern_id, "direction": direction,
            "n_occurrences": 0, "wins": 0, "losses": 0,
            "win_rate": float("nan"), "mean_pnl_pct": float("nan"),
            "stddev_pnl_pct": float("nan"), "z_score": float("nan"),
            "fold_win_rates": [], "fold_stability": 0.0,
            "first_seen": None, "last_seen": None,
        }

    wins_mask = pnl >= win_threshold
    wins = int(wins_mask.sum())
    losses = n - wins
    win_rate = wins / n
    mean_pnl = float(np.mean(pnl))
    std_pnl = float(np.std(pnl, ddof=1)) if n > 1 else 0.0
    z = compute_z_score(win_rate, n)

    df = pd.DataFrame({"date": fire_dates, "win": wins_mask}).sort_values("date").reset_index(drop=True)
    fold_win_rates: list[float] = []
    if len(df) >= 4:
        for i in range(4):
            lo = i * len(df) // 4
            hi = (i + 1) * len(df) // 4
            chunk = df.iloc[lo:hi]
            if len(chunk) > 0:
                fold_win_rates.append(float(chunk["win"].mean()))
    fold_stability = walk_forward_fold_stability(fold_win_rates)

    return {
        "ticker": ticker, "pattern_id": pattern_id, "direction": direction,
        "n_occurrences": n, "wins": wins, "losses": losses,
        "win_rate": win_rate, "mean_pnl_pct": mean_pnl,
        "stddev_pnl_pct": std_pnl, "z_score": z,
        "fold_win_rates": fold_win_rates, "fold_stability": fold_stability,
        "first_seen": df["date"].min(), "last_seen": df["date"].max(),
    }


def fit_universe(
    universe: list[str],
    bars_loader: Callable[[str], pd.DataFrame],
    start: _date,
    end: _date,
    win_threshold: float = WIN_THRESHOLD,
) -> pd.DataFrame:
    """Per (ticker, pattern), find every fire over [start, end], compute T+1
    open-to-close return, aggregate. Returns a DataFrame with one row per cell.
    """
    rows: list[dict] = []
    for ticker in universe:
        bars = bars_loader(ticker)
        if bars is None or bars.empty:
            continue
        per_pattern: dict[str, dict] = {p.pattern_id: {"dates": [], "returns": [],
                                                       "direction": p.direction}
                                        for p in PATTERNS}
        idx = bars.index
        for i in range(len(idx) - 1):
            d_i = idx[i]
            d_next = idx[i + 1]
            scan_date = d_i.date()
            if scan_date < start or scan_date > end:
                continue
            flags = detect_patterns_for_ticker(ticker, bars, scan_date)
            if not flags:
                continue
            o = bars.loc[d_next, "open"]
            c = bars.loc[d_next, "close"]
            if o == 0 or pd.isna(o) or pd.isna(c):
                continue
            ret = (c - o) / o
            for f in flags:
                per_pattern[f.pattern_id]["dates"].append(scan_date)
                per_pattern[f.pattern_id]["returns"].append(ret)
        for p in PATTERNS:
            cell = aggregate_pattern_cell(
                ticker=ticker, pattern_id=p.pattern_id, direction=p.direction,
                fire_dates=per_pattern[p.pattern_id]["dates"],
                returns=per_pattern[p.pattern_id]["returns"],
                win_threshold=win_threshold,
            )
            rows.append(cell)

    return pd.DataFrame(rows)
