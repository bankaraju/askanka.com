"""C1 — Relative-strength breakout.

Per-theme signal: percentile rank of today's 90-day relative-strength change
(theme equal-weighted basket vs NIFTY-50) within the trailing 200-day
distribution.

Score in [0, 1]: 1.0 = strongest 90d outperformance vs own 200d history,
0.5 = at median, 0.0 = weakest.

Approach: theme equal-weighted basket from member fno_historical bars (avoids
needing a per-theme→sector_index mapping; works uniformly for custom themes
like DEFENCE_WAR_ECONOMY or IT_AI_TAILWIND_ER_AND_D that lack a matching
sectoral index).

Data sources:
- NIFTY-50: pipeline/data/india_historical/indices/NIFTY_daily.csv
- Members: pipeline/data/fno_historical/<SYMBOL>.csv

PIT cutoff: bar_date <= run_date - 1d.

Coverage handling:
- Returns None when fewer than 3 members have ≥290 days of bars (need 200d
  rank window over 90d slope = 290d minimum).
- Members are aligned on the union of their trading dates; missing dates are
  forward-filled by the basket aggregation.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C1)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from pipeline.research.theme_detector.data_loaders import (
    load_nifty_50,
    load_theme_member_bars,
)
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

SLOPE_WINDOW_DAYS = 90
RANK_WINDOW_DAYS = 200
MIN_REQUIRED_BARS = SLOPE_WINDOW_DAYS + RANK_WINDOW_DAYS  # 290
MIN_MEMBERS = 3


class RSBreakoutSignal(Signal):
    signal_id = "C1_rs_breakout"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        members = _extract_members(theme)
        if not members:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="rule_kind_b_filter_predicate_unsupported_at_v1",
            )

        cutoff = run_date - timedelta(days=1)
        bars = load_theme_member_bars(members, cutoff)
        deep_enough = {sym: df for sym, df in bars.items() if len(df) >= MIN_REQUIRED_BARS}
        if len(deep_enough) < MIN_MEMBERS:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes=(
                    f"insufficient_coverage: {len(deep_enough)}/{len(members)} "
                    f"members have >= {MIN_REQUIRED_BARS} bars"
                ),
            )

        nifty = load_nifty_50(cutoff)
        if nifty is None or len(nifty) < MIN_REQUIRED_BARS:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: NIFTY-50 baseline missing or thin",
            )

        score = _compute_rs_breakout_score(deep_enough, nifty)
        if score is None:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="alignment_failed: insufficient overlap between basket and NIFTY",
            )
        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=score,
            notes=f"members_used={len(deep_enough)}/{len(members)}",
        )


def _extract_members(theme: dict) -> list[str]:
    rule = theme.get("rule_definition", {})
    return list(rule.get("members", []))


def _compute_rs_breakout_score(
    bars: dict[str, pd.DataFrame], nifty: pd.DataFrame
) -> float | None:
    """Build basket, compute RS-vs-NIFTY series, then 90d-slope, then percentile
    rank of latest 90d-slope within trailing 200d.
    """
    basket = _build_basket_close(bars)
    if basket is None or len(basket) < MIN_REQUIRED_BARS:
        return None

    nifty_indexed = nifty.set_index(nifty["Date"].dt.date)["Close"]

    aligned = pd.DataFrame({"basket": basket, "nifty": nifty_indexed}).dropna()
    if len(aligned) < MIN_REQUIRED_BARS:
        return None

    rs = aligned["basket"] / aligned["nifty"]
    slope_90d = (rs - rs.shift(SLOPE_WINDOW_DAYS)) / rs.shift(SLOPE_WINDOW_DAYS)
    slope_90d = slope_90d.dropna()

    if len(slope_90d) < RANK_WINDOW_DAYS:
        return None

    today_slope = slope_90d.iloc[-1]
    history = slope_90d.iloc[-RANK_WINDOW_DAYS:]
    rank = (history < today_slope).sum() / (len(history) - 1)
    return float(max(0.0, min(1.0, rank)))


def _build_basket_close(bars: dict[str, pd.DataFrame]) -> pd.Series | None:
    """Equal-weighted basket of normalized closes, indexed by date.

    Each member is normalized to its first-day close (=1.0) so absolute price
    levels don't dominate the basket. Daily basket value = mean of normalized
    member values.
    """
    series = []
    for sym, df in bars.items():
        s = df.set_index(df["Date"].dt.date)["Close"]
        s = s / s.iloc[0]
        series.append(s.rename(sym))
    if not series:
        return None
    combined = pd.concat(series, axis=1).sort_index()
    basket = combined.mean(axis=1, skipna=True)
    return basket.dropna()
