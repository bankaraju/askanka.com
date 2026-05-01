"""C2 — Market-cap drift.

Per-theme signal: directional drift of theme members' weight inside the
investable index, normalized to [0, 1].

The spec definition is "rolling 6m delta in summed free-float weight (Nifty
500)" but we do not have monthly free-float weight history at v1 — that is
TD-D1 (still pending acquisition).

v1 proxy (2026-05-01):
    proxy = mean of "Relative returns vs Nifty50 quarter%" over theme members
            present in the multigroup_curtailed_returns_shareholding snapshot

A member outperforming Nifty50 over the trailing quarter is gaining weight
inside the index (mathematically: a basket with higher returns rises in
free-float-weight relative to the benchmark, modulo capital-action noise).
Average across the theme = same logic at the basket level.

Mapping to [0, 1]:
    proxy >= +20%  -> 1.0  (strong basket cap-drift up)
    proxy ==   0%  -> 0.5  (neutral, drifting with index)
    proxy <= -20%  -> 0.0  (strong basket cap-drift down)
    linear in between.

Returns None when:
- theme is rule_kind=B without members (predicate-eval not in v1), OR
- multigroup snapshot is missing entirely, OR
- fewer than 2 members are present in the snapshot (insufficient breadth).

Coverage: snapshot is ~1,138 NSE-listed stocks (de-duped to non-null NSE Code).
Theme members not in snapshot are silently dropped from the proxy calculation;
the `notes` field reports `members_used / members_total`.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C2)
TD-D1 plan: replace this proxy with monthly free-float weight delta once
NIFTY-500 weight history is acquired.
"""
from __future__ import annotations

from datetime import date

from pipeline.research.theme_detector.data_loaders import load_multigroup_curtailed
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

REL_RET_COL = "Relative returns vs Nifty50 quarter%"
SATURATION_PCT = 20.0  # % outperformance at which proxy saturates to 1.0
MIN_MEMBERS_IN_SNAPSHOT = 2


class CapDriftSignal(Signal):
    signal_id = "C2_cap_drift"
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

        df = load_multigroup_curtailed(run_date, "returns_shareholding")
        if df is None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="data_unavailable: multigroup_curtailed_returns_shareholding missing",
            )
        if REL_RET_COL not in df.columns:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=f"schema_drift: column '{REL_RET_COL}' not in snapshot",
            )

        present = [m for m in members if m in df.index]
        if len(present) < MIN_MEMBERS_IN_SNAPSHOT:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes=(
                    f"insufficient_coverage: {len(present)}/{len(members)} members in snapshot "
                    f"(min={MIN_MEMBERS_IN_SNAPSHOT})"
                ),
            )

        series = df.loc[present, REL_RET_COL]
        series = series.dropna()
        if series.empty:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=None,
                notes="all_member_values_null in cap-drift proxy column",
            )

        proxy_pct = float(series.mean())
        clamped = max(-SATURATION_PCT, min(SATURATION_PCT, proxy_pct))
        score = (clamped + SATURATION_PCT) / (2 * SATURATION_PCT)

        return SignalResult(
            theme_id=theme_id,
            signal_id=self.signal_id,
            score=float(score),
            notes=(
                f"proxy=mean_rel_ret_qtr_pct={proxy_pct:+.2f}% "
                f"(members_used={len(series)}/{len(members)})"
            ),
        )
