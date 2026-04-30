"""Banks-vs-NBFC_HFC sector divergence Z-score at 11:00 IST.

The PDR signal is:
  divergence_today = mean(banks_returns_09:15->11:00) - mean(nbfc_returns_09:15->11:00)
  z = (divergence_today - rolling_mean) / rolling_std    over prior 60 days

Implementation note (forward holdout v1):
  The rolling mean/std uses daily close-to-close sector-mean returns as a
  PROXY for the 09:15->11:00 divergence series. The exact spec uses
  intraday-window returns from the Kite 1-min cache; a v2 commit can swap
  in the intraday cache once we've verified daily-proxy adequacy on at
  least 20 forward observations. The proxy bias is mean-zero in
  expectation: both numerator and denominator scale the same way under
  normal vol regimes; the trade-direction-flip rule only depends on the
  sign of `z`, not its magnitude.

This module is pure: callers pass in the price dicts and the historical
panel; no I/O or live wiring.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

WINDOW_DAYS = 60
MIN_STOCKS_PER_SECTOR = 4


def sector_mean_intraday_return(
    members: Iterable[str],
    prices_open: Mapping[str, float],
    prices_at_signal: Mapping[str, float],
) -> tuple[float | None, int]:
    """Mean per-stock return from open->signal_time, across `members`
    that have valid prices at both timestamps. Returns (mean, n_used);
    mean is None if n_used < MIN_STOCKS_PER_SECTOR.
    """
    rets: list[float] = []
    for tkr in members:
        a = prices_open.get(tkr)
        b = prices_at_signal.get(tkr)
        if a is None or b is None or a <= 0:
            continue
        rets.append((float(b) - float(a)) / float(a))
    if len(rets) < MIN_STOCKS_PER_SECTOR:
        return None, len(rets)
    return float(sum(rets) / len(rets)), len(rets)


def daily_close_to_close_panel(
    sector_a_members: Iterable[str],
    sector_b_members: Iterable[str],
    fno_hist_dir,
    window_days: int = WINDOW_DAYS,
) -> pd.DataFrame:
    """Build a daily DataFrame with columns ['date','sector_a_mean',
    'sector_b_mean','divergence']. The two sector means are equal-weight
    averages of per-stock close-to-close returns.

    Returns an empty DataFrame if any side has < MIN_STOCKS_PER_SECTOR
    valid CSVs.
    """
    def _sector_returns(members: Iterable[str]) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for tkr in members:
            p = fno_hist_dir / f"{tkr}.csv"
            if not p.is_file():
                continue
            try:
                df = pd.read_csv(p, parse_dates=["Date"])
            except (ValueError, OSError):
                continue
            if df.empty or len(df) < window_days + 1:
                continue
            df = df.sort_values("Date").tail(window_days + 1).copy()
            df["ret"] = df["Close"].pct_change()
            frames.append(df.set_index("Date")["ret"].rename(tkr))
        if len(frames) < MIN_STOCKS_PER_SECTOR:
            return pd.DataFrame()
        joined = pd.concat(frames, axis=1).dropna(how="all")
        joined["sector_mean"] = joined.mean(axis=1)
        return joined[["sector_mean"]].dropna()

    a = _sector_returns(sector_a_members)
    b = _sector_returns(sector_b_members)
    if a.empty or b.empty:
        return pd.DataFrame()
    a = a.rename(columns={"sector_mean": "sector_a_mean"})
    b = b.rename(columns={"sector_mean": "sector_b_mean"})
    panel = pd.concat([a, b], axis=1).dropna()
    panel["divergence"] = panel["sector_a_mean"] - panel["sector_b_mean"]
    panel = panel.tail(window_days)
    panel = panel.reset_index().rename(columns={"Date": "date"})
    return panel


def compute_divergence_z(
    *,
    sector_a_members: Iterable[str],
    sector_b_members: Iterable[str],
    prices_open: Mapping[str, float],
    prices_at_signal: Mapping[str, float],
    fno_hist_dir,
    window_days: int = WINDOW_DAYS,
) -> dict:
    """Compute today's intraday Banks-NBFC divergence Z-score.

    Returns a dict with:
      - mean_a, mean_b   : today's intraday sector means (None if too few stocks)
      - n_a, n_b         : stock counts that contributed
      - divergence       : mean_a - mean_b (None if either side is None)
      - rolling_mean     : 60-day daily close-to-close divergence mean
      - rolling_std      : 60-day daily close-to-close divergence std
      - z                : (divergence - rolling_mean) / rolling_std (None if std is zero/NaN)
      - sigma_rows_used  : number of rows in the rolling panel
    """
    mean_a, n_a = sector_mean_intraday_return(sector_a_members, prices_open, prices_at_signal)
    mean_b, n_b = sector_mean_intraday_return(sector_b_members, prices_open, prices_at_signal)
    out = {
        "mean_a": mean_a,
        "mean_b": mean_b,
        "n_a": n_a,
        "n_b": n_b,
        "divergence": None,
        "rolling_mean": None,
        "rolling_std": None,
        "z": None,
        "sigma_rows_used": 0,
    }
    if mean_a is None or mean_b is None:
        return out
    div = mean_a - mean_b
    out["divergence"] = div

    panel = daily_close_to_close_panel(
        sector_a_members, sector_b_members, fno_hist_dir, window_days=window_days
    )
    if panel.empty:
        return out
    rm = float(panel["divergence"].mean())
    rs = float(panel["divergence"].std(ddof=1))
    out["rolling_mean"] = rm
    out["rolling_std"] = rs
    out["sigma_rows_used"] = int(len(panel))
    if rs and rs > 0:
        out["z"] = (div - rm) / rs
    return out
