"""Rolling Phase A profile trainer with strict no-lookahead.

For a `cutoff_date`, computes per-(symbol, regime) statistics of next-day
% return using only bars dated < cutoff. Refits quarterly during the
backtest walk-forward.

Output schema:
  {symbol: {regime: {expected_return, std_return, hit_rate, n}}}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths

paths.ensure_cache()

_PROFILES_DIR = paths.PROFILES_DIR

log = logging.getLogger(__name__)


def _next_day_returns(bars: pd.DataFrame) -> pd.DataFrame:
    """Append a `next_ret` column = (close[t+1] - close[t]) / close[t]."""
    df = bars.sort_values("date").reset_index(drop=True).copy()
    df["next_ret"] = df["close"].shift(-1) / df["close"] - 1.0
    return df


def train_profile(
    symbol_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    cutoff_date: str,
    lookback_years: int = 2,
) -> dict:
    """Train per-(symbol, regime) profile on bars in [cutoff - lookback, cutoff).

    Returns: {symbol: {regime: {expected_return, std_return, hit_rate, n}}}
    """
    cutoff_ts = pd.Timestamp(cutoff_date)
    start_ts = cutoff_ts - pd.DateOffset(years=lookback_years)
    result: dict[str, dict[str, dict]] = {}

    for symbol, bars in symbol_bars.items():
        df = _next_day_returns(bars)
        df = df[df["date"] >= start_ts].copy()
        df = df.dropna(subset=["next_ret"])
        # Strict no-lookahead: drop the last bar in window because its next_ret
        # would be computed from the close on/after cutoff_date. Filtering on
        # the t+1 date (rather than `date < cutoff - 1 BD`) is robust to
        # weekend/holiday calendar quirks.
        df["next_date"] = df["date"].shift(-1)
        df = df[df["next_date"] < cutoff_ts]
        df["regime"] = df["date"].dt.strftime("%Y-%m-%d").map(regime_by_date)
        df = df.dropna(subset=["regime"])

        sym_profile: dict[str, dict] = {}
        for regime, group in df.groupby("regime"):
            rets = group["next_ret"].to_numpy()
            n = int(rets.size)
            if n < 5:
                continue
            mean_ret = float(np.mean(rets))
            sym_profile[regime] = {
                "expected_return": mean_ret,
                "std_return": float(np.std(rets, ddof=1)) if n > 1 else 0.0,
                "hit_rate": float(np.mean(np.sign(rets) == np.sign(mean_ret))),
                "n": n,
            }

        if sym_profile:
            result[symbol] = sym_profile

    return result


def train_and_cache(
    symbol_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    cutoff_date: str,
    lookback_years: int = 2,
) -> dict:
    """Train and write to phase_a_profiles/profile_<cutoff>.json. Cached."""
    cache = Path(_PROFILES_DIR) / f"profile_{cutoff_date}.json"
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("corrupt profile cache, re-training %s: %s", cache.name, exc)
            cache.unlink(missing_ok=True)

    prof = train_profile(symbol_bars, regime_by_date, cutoff_date, lookback_years)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(prof, indent=2), encoding="utf-8")
    log.info("trained Phase A profile: cutoff=%s, %d symbols", cutoff_date, len(prof))
    return prof


def cutoff_dates_for_walk_forward(
    start_date: str,
    end_date: str,
    refit_months: int = 3,
) -> list[str]:
    """Walk-forward refit cutoffs at month-start cadence.

    Returns the first calendar day of every ``refit_months``-th month within
    ``[start_date, end_date]`` (inclusive). Dates not on a month-start are
    snapped forward to the next month-start (pandas ``MS`` freq behaviour),
    so e.g. ``start_date="2024-01-15"`` yields cutoffs beginning at
    ``"2024-02-01"``.

    Returned dates may fall on weekends/holidays — the caller is responsible
    for snapping to a trading day if needed.
    """
    starts = pd.date_range(start=start_date, end=end_date, freq=f"{refit_months}MS")
    return [d.strftime("%Y-%m-%d") for d in starts]
