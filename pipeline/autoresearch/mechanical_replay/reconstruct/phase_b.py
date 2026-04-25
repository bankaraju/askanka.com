"""Deterministic Phase B basket regeneration for the v2 mechanical replay.

Phase B fires on regime TRANSITION days only — a day where today's regime
zone differs from yesterday's. On such a day, the ranker reads the frozen
Phase A profile (`pipeline/autoresearch/reverse_regime_profile.json`),
finds every (ticker, transition) pair where transition ends in today's
new regime, ranks them by `avg_drift_5d`, and emits top_n longs (positive
drift) and top_n shorts (negative drift).

Output is one row per (date, ticker, side) — a tidy basket.

§14 contamination notes:
  - Profile is the CURRENT on-disk snapshot, not "as-of-D". Transitions
    discovered post-window thus inform pre-window dates. Documented as
    contamination per the v2 spec.
  - HOLD_DAYS persistence (5 trading days from transition) is captured
    in the live engine's signal_tracker, not here. v2 only emits the
    transition-day basket; the simulator decides the exit horizon.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C

log = logging.getLogger(__name__)


_DEFAULT_PROFILE_PATH = (
    C._REPO / "pipeline" / "autoresearch" / "reverse_regime_profile.json"
)
DEFAULT_TOP_N = 5


def _load_profile(profile_path: Path) -> dict:
    return json.loads(Path(profile_path).read_text(encoding="utf-8"))


def _rank_for_transition(
    profile: dict, target_zone: str, top_n: int
) -> tuple[list[dict], list[dict]]:
    """Mirrors `reverse_regime_ranker.rank_stocks`. Returns (longs, shorts)."""
    stock_profiles = profile.get("stock_profiles", {})
    candidates: list[dict] = []
    target_upper = target_zone.upper()
    for symbol, data in stock_profiles.items():
        for transition_key, stats in (data.get("by_transition") or {}).items():
            parts = transition_key.split("->")
            if len(parts) != 2:
                continue
            to_zone = parts[1].strip().upper()
            if to_zone != target_upper:
                continue
            drift = stats.get("avg_drift_5d")
            if drift is None:
                continue
            candidates.append({
                "ticker": symbol,
                "transition": transition_key,
                "drift_5d": float(drift),
                "drift_1d": float(stats.get("avg_drift_1d") or 0.0),
                "hit_rate": float(stats.get("hit_rate") or 0.0),
                "episodes": int(stats.get("episode_count") or 0),
                "tradeable_rate": float(stats.get("tradeable_rate") or 0.0),
                "persistence_rate": float(stats.get("persistence_rate") or 0.0),
            })
    longs = [c for c in candidates if c["drift_5d"] > 0]
    shorts = [c for c in candidates if c["drift_5d"] < 0]
    longs.sort(key=lambda x: abs(x["drift_5d"]), reverse=True)
    shorts.sort(key=lambda x: abs(x["drift_5d"]), reverse=True)
    return longs[:top_n], shorts[:top_n]


def regenerate(
    *,
    regime_history: pd.DataFrame,
    profile_path: Optional[Path] = None,
    top_n: int = DEFAULT_TOP_N,
) -> pd.DataFrame:
    """Emit one row per (date, ticker, side) on every regime-transition day
    inside the regime_history window.

    Parameters
    ----------
    regime_history : pd.DataFrame
        Columns at minimum [date, regime_zone]. Sorted ascending by date.
    profile_path : Path | None
        Frozen Phase A profile. Defaults to the live engine's location.
    top_n : int
        Top-N longs and shorts to keep per transition day.

    Returns
    -------
    pd.DataFrame
        Columns: date, ticker, side, score, regime, transition,
                 hit_rate, episodes, tradeable_rate, persistence_rate.
        Empty when no transition days exist in the window.
    """
    if profile_path is None:
        profile_path = _DEFAULT_PROFILE_PATH
    df = regime_history.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.sort_values("date").reset_index(drop=True)
    df["prev_regime"] = df["regime_zone"].shift(1)
    transitions = df[
        df["prev_regime"].notna() & (df["regime_zone"] != df["prev_regime"])
    ].copy()
    if transitions.empty:
        return pd.DataFrame(columns=[
            "date", "ticker", "side", "score", "regime", "transition",
            "hit_rate", "episodes", "tradeable_rate", "persistence_rate",
        ])

    profile = _load_profile(profile_path)
    rows: list[dict] = []
    for _, t in transitions.iterrows():
        target_zone = t["regime_zone"]
        prev_zone = t["prev_regime"]
        longs, shorts = _rank_for_transition(profile, target_zone, top_n)
        for c in longs:
            rows.append({
                "date": t["date"], "ticker": c["ticker"], "side": "LONG",
                "score": c["drift_5d"], "regime": target_zone,
                "transition": c["transition"], "prev_regime": prev_zone,
                "hit_rate": c["hit_rate"], "episodes": c["episodes"],
                "tradeable_rate": c["tradeable_rate"],
                "persistence_rate": c["persistence_rate"],
            })
        for c in shorts:
            rows.append({
                "date": t["date"], "ticker": c["ticker"], "side": "SHORT",
                "score": c["drift_5d"], "regime": target_zone,
                "transition": c["transition"], "prev_regime": prev_zone,
                "hit_rate": c["hit_rate"], "episodes": c["episodes"],
                "tradeable_rate": c["tradeable_rate"],
                "persistence_rate": c["persistence_rate"],
            })
    return pd.DataFrame(rows)
