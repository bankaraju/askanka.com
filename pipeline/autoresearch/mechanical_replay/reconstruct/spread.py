"""Deterministic spread-book regeneration for the v2 mechanical replay.

For each (pair, date) in the window:
  1. Build the long-basket and short-basket close series (equal-weighted log
     levels of the leg tickers).
  2. Compute the log-spread = log(long_basket / short_basket).
  3. Z-score the spread over a rolling `lookback_days` window. The z-score
     uses bars strictly < target_date (no look-ahead).
  4. Apply the regime gate from `regime_by_date`.
  5. Record (date, pair_id, leg_long, leg_short, entry_z, regime, gate_status,
     direction).

The convention: a POSITIVE z means the long leg is rich vs the short leg
relative to its rolling mean — the mean-reversion play is to FADE that
divergence (REVERSE the named direction). A negative z means the named
direction (LONG long-leg, SHORT short-leg) is the trade — NORMAL.

§14 contamination note: pair definitions are read from the live config
(`pipeline/config.py::INDIA_SPREAD_PAIRS`); they do NOT have a per-D
versioning history, so pair add/drop events post-window leak backward.
For a 60-day window this is acceptable — pair definitions changed at most
twice in the window per `git log -- pipeline/config.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _basket_close_series(
    legs: list[str], universe_bars: dict[str, pd.DataFrame]
) -> Optional[pd.DataFrame]:
    """Equal-weighted log-level basket. Returns None when no leg has bars."""
    leg_frames: list[pd.DataFrame] = []
    for sym in legs:
        bars = universe_bars.get(sym)
        if bars is None or bars.empty:
            continue
        s = bars[["date", "close"]].copy()
        s["log_close"] = np.log(s["close"])
        leg_frames.append(s[["date", "log_close"]].rename(columns={"log_close": sym}))
    if not leg_frames:
        return None
    merged = leg_frames[0]
    for f in leg_frames[1:]:
        merged = merged.merge(f, on="date", how="inner")
    if merged.shape[0] == 0:
        return None
    leg_cols = [c for c in merged.columns if c != "date"]
    merged["basket_log"] = merged[leg_cols].mean(axis=1)
    return merged[["date", "basket_log"]]


def compute_spread_zscore(
    *,
    long_bars: pd.DataFrame,
    short_bars: pd.DataFrame,
    target_date: pd.Timestamp,
    lookback_days: int,
) -> float:
    """z-score of log(long/short) on target_date vs rolling mean+std on
    [target_date - lookback_days, target_date) (strictly before).
    """
    target_date = pd.Timestamp(target_date).normalize()
    long_log = long_bars.set_index(pd.to_datetime(long_bars["date"]))["close"].apply(np.log)
    short_log = short_bars.set_index(pd.to_datetime(short_bars["date"]))["close"].apply(np.log)
    spread = long_log - short_log
    spread = spread.sort_index()
    history = spread[spread.index < target_date].tail(lookback_days)
    if len(history) < max(20, lookback_days // 2):
        return float("nan")
    mu = history.mean()
    sigma = history.std(ddof=1)
    if sigma == 0 or pd.isna(sigma):
        return float("nan")
    today_value = spread[spread.index <= target_date]
    if today_value.empty:
        return float("nan")
    today_value = today_value.iloc[-1]
    return float((today_value - mu) / sigma)


def regenerate(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    pairs: list[dict],
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    entry_threshold: float = 2.0,
    lookback_days: int = 60,
    allowed_regimes: Optional[set[str]] = None,
) -> pd.DataFrame:
    """Re-run the pair-z spread engine against canonical bars.

    Parameters
    ----------
    pairs : list[dict]
        Each dict must have keys: name, long (list of tickers), short
        (list of tickers).
    entry_threshold : float
        |z| >= entry_threshold required to mark gate_status=OPEN.
    allowed_regimes : set[str] | None
        Regimes that pass the gate. None → all regimes allowed.

    Returns
    -------
    pd.DataFrame
        Columns: date, pair_id, leg_long, leg_short, entry_z, regime,
        gate_status, direction.
    """
    window_start = pd.Timestamp(window_start).normalize()
    window_end = pd.Timestamp(window_end).normalize()

    rows: list[dict] = []
    for pair in pairs:
        pair_name = pair.get("name", "UNKNOWN")
        long_legs: list[str] = list(pair.get("long", []))
        short_legs: list[str] = list(pair.get("short", []))
        long_basket = _basket_close_series(long_legs, universe_bars)
        short_basket = _basket_close_series(short_legs, universe_bars)
        if long_basket is None or short_basket is None:
            log.warning("spread regen: skipping %s — basket bars missing", pair_name)
            continue
        merged = long_basket.merge(short_basket, on="date", suffixes=("_long", "_short"))
        merged = merged.sort_values("date").reset_index(drop=True)
        merged["spread"] = merged["basket_log_long"] - merged["basket_log_short"]
        merged.set_index(pd.to_datetime(merged["date"]), inplace=True)

        from pipeline.autoresearch.mechanical_replay.reconstruct.phase_c import _trading_days
        for d in _trading_days(window_start, window_end):
            d_norm = pd.Timestamp(d).normalize()
            history = merged[merged.index < d_norm].tail(lookback_days)
            if len(history) < max(20, lookback_days // 2):
                continue
            today = merged[merged.index <= d_norm]
            if today.empty:
                continue
            mu = float(history["spread"].mean())
            sigma = float(history["spread"].std(ddof=1))
            if sigma == 0 or pd.isna(sigma):
                continue
            today_spread = float(today["spread"].iloc[-1])
            entry_z = (today_spread - mu) / sigma
            regime = regime_by_date.get(d_norm.strftime("%Y-%m-%d"))
            if regime is None:
                continue
            gate_open = abs(entry_z) >= entry_threshold and (
                allowed_regimes is None or regime in allowed_regimes
            )
            direction = "REVERSE" if entry_z > 0 else "NORMAL"
            rows.append({
                "date": d_norm,
                "pair_id": pair_name,
                "leg_long": ",".join(long_legs),
                "leg_short": ",".join(short_legs),
                "entry_z": round(entry_z, 3),
                "regime": regime,
                "gate_status": "OPEN" if gate_open else "BLOCKED",
                "direction": direction,
            })

    cols = ["date", "pair_id", "leg_long", "leg_short", "entry_z",
            "regime", "gate_status", "direction"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]
