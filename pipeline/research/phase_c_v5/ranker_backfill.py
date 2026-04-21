"""Synthesise what the reverse-regime ranker would have emitted for any
historical day given the Phase A profile and a daily regime series.

Phase A profile is a per-regime map of symbol → {drift_5d_mean, hit_rate_5d,
episodes}. The ranker each day picks the top-N LONG-side (drift > 0) and
top-N SHORT-side (drift < 0) symbols filtered by hit_rate and episodes,
sorted by ``abs(drift_5d_mean)`` descending.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd


def _regime_age_series(regime_history: pd.DataFrame) -> pd.Series:
    """For each row, how many consecutive prior rows shared the same zone."""
    zones = regime_history["zone"].tolist()
    ages = []
    for i, z in enumerate(zones):
        age = 1
        j = i - 1
        while j >= 0 and zones[j] == z:
            age += 1
            j -= 1
        ages.append(age)
    return pd.Series(ages, index=regime_history.index, name="regime_age_days")


def backfill_daily_top_n(
    profile_path: Path,
    regime_history: pd.DataFrame,
    top_n: int = 3,
    min_episodes: int = 4,
    min_hit_rate: float = 0.6,
) -> pd.DataFrame:
    """Emit one row per (date, side, rank) for the synthesised ranker output.

    Args:
        profile_path: Phase A profile JSON.
        regime_history: DataFrame with ``date`` and ``zone`` columns.
        top_n: candidates per side per day.
        min_episodes: filter out symbols with fewer historical episodes.
        min_hit_rate: filter out symbols with hit rate below this.

    Returns:
        DataFrame with columns
        ``[date, zone, regime_age_days, side, rank, symbol, drift_5d_mean, hit_rate_5d, episodes]``.
    """
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    history = regime_history.copy()
    history["date"] = pd.to_datetime(history["date"])
    history = history.sort_values("date").reset_index(drop=True)
    history["regime_age_days"] = _regime_age_series(history)

    rows: list[dict] = []
    for _, day in history.iterrows():
        zone = day["zone"]
        zone_symbols = profile.get(zone, {}).get("symbols", {})
        eligible = []
        for sym, stats in zone_symbols.items():
            if stats.get("episodes", 0) < min_episodes:
                continue
            if stats.get("hit_rate_5d", 0.0) < min_hit_rate:
                continue
            eligible.append({
                "symbol": sym,
                "drift_5d_mean": stats["drift_5d_mean"],
                "hit_rate_5d": stats["hit_rate_5d"],
                "episodes": stats["episodes"],
            })
        longs = sorted([e for e in eligible if e["drift_5d_mean"] > 0],
                       key=lambda x: abs(x["drift_5d_mean"]), reverse=True)[:top_n]
        shorts = sorted([e for e in eligible if e["drift_5d_mean"] < 0],
                        key=lambda x: abs(x["drift_5d_mean"]), reverse=True)[:top_n]
        for rank, e in enumerate(longs, start=1):
            rows.append({"date": day["date"], "zone": zone,
                         "regime_age_days": int(day["regime_age_days"]),
                         "side": "LONG", "rank": rank, **e})
        for rank, e in enumerate(shorts, start=1):
            rows.append({"date": day["date"], "zone": zone,
                         "regime_age_days": int(day["regime_age_days"]),
                         "side": "SHORT", "rank": rank, **e})
    return pd.DataFrame(rows, columns=[
        "date", "zone", "regime_age_days", "side", "rank",
        "symbol", "drift_5d_mean", "hit_rate_5d", "episodes",
    ])
