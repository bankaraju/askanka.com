"""C5 — Earnings breadth.

Per-theme signal: % of theme members posting positive earnings momentum on the
most-recent quarter, normalized to [0, 1].

Spec definition is "% of members with QoQ EPS surprise > 0 over rolling 2
quarters." We do not have a clean EPS-vs-consensus surprise stream at v1 —
TD-D9 (IndianAPI quarterly stats + Screener consensus) is still pending
acquisition.

v1 proxy (2026-05-01):
    proxy_share = (# members with Net Profit QoQ Growth % > 0)
                  / (# members in snapshot with non-null growth)

The Trendlyne fundamentals_fno multigroup snapshot exposes "Net Profit QoQ
Growth %" computed off the latest reported quarter. Positive QoQ profit growth
is a defensible v1 proxy for "post-earnings beat" because:
- it directly measures the quarter that just printed
- it is normalized within the company (vs annual seasonality)
- breadth (share, not magnitude) matches the spec semantics

The proxy is biased relative to the spec target:
- it does NOT control for analyst expectations (a beat-vs-consensus may still
  print negative QoQ growth, and a miss may still print positive QoQ growth)
- it is single-quarter, not 2-quarter rolling

v2 fix is to plug the IndianAPI consensus stream once TD-D9 is acquired.

Returns None when:
- theme is rule_kind=B without members, OR
- multigroup snapshot is missing, OR
- fewer than 2 members have non-null Net Profit QoQ Growth %.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C5)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.data_loaders import load_multigroup_curtailed
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

GROWTH_COL = "Net Profit QoQ Growth %"
MIN_MEMBERS_WITH_DATA = 2


class EarningsBreadthSignal(Signal):
    signal_id = "C5_earnings_breadth"
    bucket = "confirmation"

    def compute_for_theme(self, theme: dict, run_date: date) -> SignalResult:
        members = list(theme.get("rule_definition", {}).get("members", []))
        theme_id = theme["theme_id"]

        if not members:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="rule_kind_b_filter_predicate_unsupported_at_v1",
            )

        df = load_multigroup_curtailed(run_date, "fundamentals_fno")
        if df is None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: multigroup_curtailed_fundamentals_fno missing",
            )
        if GROWTH_COL not in df.columns:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=f"schema_drift: column '{GROWTH_COL}' not in snapshot",
            )

        present = [m for m in members if m in df.index]
        series = df.loc[present, GROWTH_COL].dropna() if present else None
        if series is None or len(series) < MIN_MEMBERS_WITH_DATA:
            n_with = 0 if series is None else len(series)
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=(
                    f"insufficient_coverage: {n_with}/{len(members)} members have "
                    f"non-null QoQ profit growth (min={MIN_MEMBERS_WITH_DATA})"
                ),
            )

        n_pos = int((series > 0).sum())
        n_total = int(len(series))
        score = n_pos / n_total

        return SignalResult(
            theme_id=theme_id,
            signal_id=self.signal_id,
            score=float(score),
            notes=(
                f"proxy=share_QoQ_profit_growth_positive {n_pos}/{n_total} "
                f"(members_used={n_total}/{len(members)})"
            ),
        )
