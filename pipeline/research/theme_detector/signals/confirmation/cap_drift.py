"""C2 — Market-cap drift.

Per-theme signal: directional drift of theme members' summed weight inside
the investable index (NIFTY 500), normalized to [0, 1].

Spec definition: "rolling 6m delta in summed free-float weight (Nifty 500)".

v1.0.2 (2026-05-02): canonical-first with proxy fallback.
  - canonical: 6-month delta in summed theme weight from
    `load_nifty500_weights_reconstructed` (anchored to today's NSE snapshot,
    walked backward via close-price ratio × today's ffmc; covers ~89.97% of
    NIFTY 500 weight). Maps to [0,1] via SATURATION_DELTA_PP.
  - proxy fallback (v1 path): mean of "Relative returns vs Nifty50 quarter%"
    over theme members in the multigroup_curtailed snapshot. Used when the
    reconstruction is missing OR has insufficient lookback (< MIN_LOOKBACK_DAYS).

Mapping to [0, 1] (canonical):
    delta_6m_pp >= +1.0 pp -> 1.0  (theme gained ≥1% of NIFTY-500 weight in 6m)
    delta_6m_pp ==     0   -> 0.5  (no drift)
    delta_6m_pp <= -1.0 pp -> 0.0  (theme lost ≥1% of NIFTY-500 weight in 6m)

Mapping to [0, 1] (proxy fallback):
    proxy >= +20%  -> 1.0
    proxy ==   0%  -> 0.5
    proxy <= -20%  -> 0.0

Returns None when:
- theme is rule_kind=B without members, OR
- both canonical reconstruction AND multigroup snapshot are missing, OR
- insufficient coverage on whichever path is selected.

Notes line always reports source + canonical_n / proxy_n for audit.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md §3.2 (C2)
"""
from __future__ import annotations

from datetime import date, timedelta

from pipeline.research.theme_detector.data_loaders import (
    load_multigroup_curtailed,
    load_nifty500_weights_reconstructed,
)
from pipeline.research.theme_detector.signals.base import Signal, SignalResult

# Proxy path (v1 fallback)
REL_RET_COL = "Relative returns vs Nifty50 quarter%"
PROXY_SATURATION_PCT = 20.0
MIN_MEMBERS_IN_SNAPSHOT = 2

# Canonical path (TD-D1 reconstruction)
LOOKBACK_DAYS = 180  # ~6 months of calendar days
MIN_LOOKBACK_DAYS = 90  # need at least 3 months of history for canonical
SATURATION_DELTA_PP = 1.0  # 1pp NIFTY-500 weight delta → score saturates


def _try_canonical(theme_id: str, members: list[str], run_date: date):
    """Returns (score, notes, canonical_n) — score is None when fallback needed."""
    df = load_nifty500_weights_reconstructed(run_date)
    if df is None:
        return None, "no_canonical_reconstruction", 0
    df_today = df[df.index == df.index.max()]
    if df_today.empty:
        return None, "canonical_no_anchor_row", 0
    today_d = df_today.index.max()
    target_d = today_d - timedelta(days=LOOKBACK_DAYS)
    df_past = df[df.index <= target_d]
    if df_past.empty:
        return None, "canonical_insufficient_lookback", 0
    past_d = df_past.index.max()
    if (today_d - past_d).days < MIN_LOOKBACK_DAYS:
        return (
            None,
            f"canonical_insufficient_lookback days={(today_d - past_d).days}",
            0,
        )

    today_slice = df_today.set_index("nse_symbol")["weight_pct"]
    past_slice = df[df.index == past_d].set_index("nse_symbol")["weight_pct"]
    members_in_today = [m for m in members if m in today_slice.index]
    members_in_past = [m for m in members if m in past_slice.index]
    canonical_n = len(set(members_in_today) & set(members_in_past))
    if canonical_n < MIN_MEMBERS_IN_SNAPSHOT:
        return (
            None,
            f"canonical_thin_coverage members={canonical_n}/{len(members)}",
            canonical_n,
        )

    today_sum = float(today_slice.reindex(members_in_today, fill_value=0).sum())
    past_sum = float(past_slice.reindex(members_in_past, fill_value=0).sum())
    delta_pp = today_sum - past_sum
    clamped = max(-SATURATION_DELTA_PP, min(SATURATION_DELTA_PP, delta_pp))
    score = (clamped + SATURATION_DELTA_PP) / (2 * SATURATION_DELTA_PP)
    notes = (
        f"source=canonical_nifty500_weight_delta_6m "
        f"delta={delta_pp:+.4f}pp today_sum={today_sum:.4f}% past_sum={past_sum:.4f}% "
        f"past_date={past_d} members_used={canonical_n}/{len(members)}"
    )
    return float(score), notes, canonical_n


def _try_proxy(theme_id: str, members: list[str], run_date: date, canonical_n: int):
    df = load_multigroup_curtailed(run_date, "returns_shareholding")
    if df is None:
        return SignalResult(
            theme_id=theme_id,
            signal_id="C2_cap_drift",
            score=None,
            notes=f"data_unavailable: canonical_n={canonical_n} proxy_unavailable",
        )
    if REL_RET_COL not in df.columns:
        return SignalResult(
            theme_id=theme_id,
            signal_id="C2_cap_drift",
            score=None,
            notes=f"schema_drift: column '{REL_RET_COL}' not in snapshot",
        )
    present = [m for m in members if m in df.index]
    if len(present) < MIN_MEMBERS_IN_SNAPSHOT:
        return SignalResult(
            theme_id=theme_id,
            signal_id="C2_cap_drift",
            score=None,
            notes=(
                f"insufficient_coverage: canonical_n={canonical_n} "
                f"proxy_n={len(present)}/{len(members)} (min={MIN_MEMBERS_IN_SNAPSHOT})"
            ),
        )
    series = df.loc[present, REL_RET_COL].dropna()
    if series.empty:
        return SignalResult(
            theme_id=theme_id,
            signal_id="C2_cap_drift",
            score=None,
            notes="all_member_values_null in cap-drift proxy column",
        )
    proxy_pct = float(series.mean())
    clamped = max(-PROXY_SATURATION_PCT, min(PROXY_SATURATION_PCT, proxy_pct))
    score = (clamped + PROXY_SATURATION_PCT) / (2 * PROXY_SATURATION_PCT)
    return SignalResult(
        theme_id=theme_id,
        signal_id="C2_cap_drift",
        score=float(score),
        notes=(
            f"source=proxy_rel_ret_qtr canonical_n={canonical_n} "
            f"proxy_pct={proxy_pct:+.2f}% members_used={len(series)}/{len(members)}"
        ),
    )


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

        score, notes, canonical_n = _try_canonical(theme_id, members, run_date)
        if score is not None:
            return SignalResult(
                theme_id=theme_id,
                signal_id=self.signal_id,
                score=score,
                notes=notes,
            )
        # Fallback to proxy. Append canonical reason to proxy notes for audit.
        result = _try_proxy(theme_id, members, run_date, canonical_n)
        if result.notes is not None and notes:
            result = SignalResult(
                theme_id=result.theme_id,
                signal_id=result.signal_id,
                score=result.score,
                notes=f"{result.notes} [canonical_skip={notes}]",
            )
        return result
