"""C6 — Sector breadth.

Per-theme signal: % of theme members trading above 200d MA, averaged over the
last 4 weeks (~20 trading days).

Score IS the breadth ratio in [0, 1] — no normalization needed.

Data source: pipeline/data/fno_historical/<SYMBOL>.csv (daily bars, existing).
PIT cutoff: bar_date <= run_date.

Coverage handling:
- Members whose CSV is missing are omitted; if fewer than 3 members have bars,
  signal returns None (insufficient coverage).
- Members with fewer than 200 bars before cutoff cannot anchor a 200d MA;
  they're omitted from the daily snapshot for the days they can't anchor.
- If no day in the 4w window has at least 3 anchorable members, signal returns
  None.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C6)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from pipeline.research.theme_detector.data_loaders import load_theme_member_bars
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

MA_WINDOW_DAYS = 200
LOOKBACK_TRADING_DAYS = 20  # ~4 weeks
MIN_MEMBERS_FOR_SIGNAL = 3


class SectorBreadthSignal(Signal):
    signal_id = "C6_sector_breadth"
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

        cutoff = run_date - timedelta(days=1)  # PIT: bar_date <= run_date - 1d
        bars = load_theme_member_bars(members, cutoff)

        if len(bars) < MIN_MEMBERS_FOR_SIGNAL:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes=f"insufficient_coverage: {len(bars)}/{len(members)} members have bars",
            )

        score = _compute_breadth_score(bars)
        if score is None:
            return SignalResult(
                theme_id=theme["theme_id"],
                signal_id=self.signal_id,
                score=None,
                notes="insufficient_history_for_200d_ma_in_lookback_window",
            )

        return SignalResult(
            theme_id=theme["theme_id"],
            signal_id=self.signal_id,
            score=score,
            notes=f"members_with_bars={len(bars)}/{len(members)}",
        )


def _extract_members(theme: dict) -> list[str]:
    """Extract members from a Rule kind A theme. Rule B/C handled in v2."""
    rule = theme.get("rule_definition", {})
    return list(rule.get("members", []))


def _compute_breadth_score(bars: dict[str, pd.DataFrame]) -> float | None:
    """% above 200d MA, averaged over last 20 trading days, across members."""
    daily_shares: list[float] = []

    common_dates = _common_trading_dates(bars)
    if not common_dates:
        return None

    last_n = sorted(common_dates)[-LOOKBACK_TRADING_DAYS:]
    if len(last_n) == 0:
        return None

    for d in last_n:
        anchorable = []
        for sym, df in bars.items():
            sub = df[df["Date"].dt.date <= d]
            if len(sub) < MA_WINDOW_DAYS:
                continue
            ma = sub["Close"].iloc[-MA_WINDOW_DAYS:].mean()
            close = sub["Close"].iloc[-1]
            anchorable.append(close > ma)
        if len(anchorable) >= MIN_MEMBERS_FOR_SIGNAL:
            daily_shares.append(sum(anchorable) / len(anchorable))

    if not daily_shares:
        return None
    return float(sum(daily_shares) / len(daily_shares))


def _common_trading_dates(bars: dict[str, pd.DataFrame]) -> list:
    """Union of trading dates across members (caps at most-recent member's last)."""
    all_dates: set = set()
    for df in bars.values():
        all_dates.update(df["Date"].dt.date.tolist())
    return sorted(all_dates)
