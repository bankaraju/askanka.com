"""C5 — Earnings breadth.

Per-theme signal: % of theme members posting positive earnings momentum on the
most-recent quarter, normalized to [0, 1].

Spec definition: "% of members with QoQ EPS surprise > 0 over rolling 2
quarters" (TD-D9 canonical — actual EPS vs consensus).

v1.0 (2026-05-01) shipped a single-source proxy: Net Profit QoQ Growth % from
Trendlyne multigroup_curtailed_fundamentals_fno. That proxy is biased relative
to the spec target because it does NOT control for analyst expectations.

v1.0.1 (2026-05-02) — canonical-first with proxy fallback:

  Source A (canonical, preferred):
    Net Profit Surprise Qtr % from Trendlyne results_dashboard
    (`pipeline/data/trendlyne/raw_exports/results_dashboard/quarterly_results_*.csv`)
    — actual NP vs consensus, the spec metric. Coverage grows quarter-by-quarter
    as Trendlyne's covered universe expands and Q4 results print.

  Source B (proxy, fallback):
    Net Profit QoQ Growth % from multigroup_curtailed_fundamentals_fno —
    quarter-on-quarter accounting growth, available for ~2,000 stocks. Used
    only when canonical coverage for a theme is below MIN_CANONICAL_COVERAGE.

The signal returns a single breadth ratio in [0, 1]. The `notes` field always
records which source was used + per-source member counts so downstream
diagnostics can audit canonical coverage growth over time.

Returns None when:
- theme is rule_kind=B without members, OR
- BOTH canonical and proxy snapshots are missing, OR
- combined coverage is below MIN_MEMBERS_WITH_DATA.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C5)
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.data_loaders import (
    load_multigroup_curtailed,
    load_results_dashboard,
)
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

GROWTH_COL = "Net Profit QoQ Growth %"
NPS_COL = "Net Profit Surprise Qtr %"
MIN_MEMBERS_WITH_DATA = 2
MIN_CANONICAL_COVERAGE = 2  # require >= this many members with NPS to use canonical


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

        canonical_score, canonical_notes, canonical_n = self._try_canonical(
            members, run_date
        )
        if canonical_score is not None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=canonical_score,
                notes=canonical_notes,
            )

        proxy_df = load_multigroup_curtailed(run_date, "fundamentals_fno")
        if proxy_df is None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=(
                    "data_unavailable: results_dashboard insufficient "
                    f"({canonical_n} canonical) AND "
                    "multigroup_curtailed_fundamentals_fno missing"
                ),
            )
        if GROWTH_COL not in proxy_df.columns:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=f"schema_drift: column '{GROWTH_COL}' not in proxy snapshot",
            )

        present = [m for m in members if m in proxy_df.index]
        series = proxy_df.loc[present, GROWTH_COL].dropna() if present else None
        if series is None or len(series) < MIN_MEMBERS_WITH_DATA:
            n_with = 0 if series is None else len(series)
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=(
                    f"insufficient_coverage: canonical={canonical_n}, "
                    f"proxy={n_with}/{len(members)} (min={MIN_MEMBERS_WITH_DATA})"
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
                f"source=proxy_qoq_growth ({n_pos}/{n_total} positive, "
                f"members_used={n_total}/{len(members)}, canonical={canonical_n})"
            ),
        )

    def _try_canonical(
        self, members: list[str], run_date: date
    ) -> tuple[float | None, str | None, int]:
        """Attempt canonical Net Profit Surprise breadth.

        Returns (score, notes, canonical_n). When canonical coverage is below
        threshold, returns (None, None, n) so the caller can fall back to proxy
        and surface the canonical count in the proxy notes.
        """
        df = load_results_dashboard(run_date)
        if df is None or NPS_COL not in df.columns:
            return None, None, 0

        present = [m for m in members if m in df.index]
        if not present:
            return None, None, 0

        series = df.loc[present, NPS_COL].dropna()
        if len(series) < MIN_CANONICAL_COVERAGE:
            return None, None, int(len(series))

        n_pos = int((series > 0).sum())
        n_total = int(len(series))
        score = n_pos / n_total
        notes = (
            f"source=canonical_net_profit_surprise ({n_pos}/{n_total} positive, "
            f"members_used={n_total}/{len(members)})"
        )
        return float(score), notes, n_total
