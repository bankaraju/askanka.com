"""Deterministic Phase C roster regeneration for the v2 mechanical replay.

For each trading day D in the window:
  1. Take the regenerated regime tag from `reconstruct.regime`.
  2. Look up the active walk-forward Phase A profile (per (symbol, regime)
     next-day return statistics, computed using only bars dated < cutoff).
  3. For every ticker in the universe, compute today's actual fractional
     return and its z-score against the profiled (expected, std) for the
     regime.
  4. Run the canonical `classify_break` decision matrix from
     `pipeline.autoresearch.reverse_regime_breaks`.
  5. Apply the geometric LAG/OVERSHOOT split + direction enrichment to
     derive `trade_rec` per the live engine's post-2026-04-23 logic.

§14 contamination notes (recorded explicitly because they are inherent to
v1+v2 with current archives):
  - Profile is trained from canonical bars + reconstructed regime tags.
    The live engine's profile (`reverse_regime_profile.json`) uses a
    transition-episode schema that we do NOT replicate here. The classifier
    in this module mirrors `pipeline.research.phase_c_backtest.classifier`
    exactly — it shares the same `classify_break` decision matrix as the
    live engine, but trains profiles via per-(symbol, regime) next-day
    return statistics (the canonical historical replay convention).
  - Trust scores are out-of-scope for Phase C entry decisions.
  - PCR is treated as NEUTRAL when not provided. Future v3 work could
    wire bhavcopy PCR per (symbol, date) here.

Output columns:
  date, ticker, classification, z_score, trade_rec, regime, sector,
  signal_id, expected_return, actual_return.

This module is "out-of-the-box" deterministic: given identical canonical
bars + identical regime tags, the output is bit-stable.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from pipeline.autoresearch.reverse_regime_breaks import (
    classify_break,
    classify_pcr,
    classify_event_geometry,
)
from pipeline.research.phase_c_backtest import profile as profile_mod
from pipeline.research.phase_c_backtest.regime import _daily_return_at

log = logging.getLogger(__name__)


def _z_score(actual: float, expected: float, std: float) -> float:
    """Mirrors pipeline.research.phase_c_backtest.classifier._z_score."""
    if std <= 0.001:
        return 0.0
    return (actual - expected) / std


def _select_active_cutoff(cutoffs: list[str], target_date: str) -> Optional[str]:
    """Most recent cutoff <= target_date. None when no cutoff predates the date."""
    eligible = [c for c in cutoffs if c <= target_date]
    if not eligible:
        return None
    return max(eligible)


def _direction_enrichment(
    classification: str,
    expected_return_pct: float,
) -> str | None:
    """Mirrors `enrich_break_with_direction` from reverse_regime_breaks.py
    post-2026-04-23 logic. Returns trade_rec ∈ {LONG, SHORT, None}.

    OPPORTUNITY_LAG: trade in the expected direction (FOLLOW-the-peer logic).
    OPPORTUNITY_OVERSHOOT: alert-only — None.
    All other labels: None.
    """
    if classification == "OPPORTUNITY_LAG":
        return "LONG" if expected_return_pct > 0 else "SHORT"
    return None


def regenerate(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    refit_months: int = 3,
    lookback_years: int = 2,
    pcr_by_date: Optional[dict[str, dict[str, float]]] = None,
    oi_anomaly_by_date: Optional[dict[str, dict[str, bool]]] = None,
    sector_by_ticker: Optional[dict[str, str]] = None,
    actionable_only: bool = False,
) -> pd.DataFrame:
    """Re-run Phase C decision logic against canonical historical bars.

    Parameters
    ----------
    window_start, window_end : pd.Timestamp
        Inclusive bounds of the replay window.
    universe_bars : dict[ticker -> DataFrame]
        Each frame has at least [date, close]. Date is normalised to midnight.
    regime_by_date : dict[date_str -> regime_zone]
        Keys are ISO date strings (YYYY-MM-DD). Dates missing from this map
        are silently skipped.
    refit_months : int
        Walk-forward profile refit cadence. Default 3 months — matches
        the historical Phase C backtest convention.
    lookback_years : int
        Profile training lookback. Default 2 years.
    pcr_by_date : dict[date_str -> dict[ticker -> pcr_value]] | None
        Optional per-day PCR map. Missing entries → NEUTRAL.
    oi_anomaly_by_date : dict[date_str -> dict[ticker -> bool]] | None
        Optional per-day OI-anomaly flag. Missing → False.
    sector_by_ticker : dict[ticker -> sector] | None
        Optional sector tagging carried into the output frame.
    actionable_only : bool
        If True, drop everything except OPPORTUNITY_LAG with a non-null
        trade_rec — the only labels the live engine treats as tradeable.

    Returns
    -------
    pd.DataFrame
        Columns: date, ticker, classification, z_score, trade_rec, regime,
        sector, signal_id, expected_return, actual_return.
    """
    window_start = pd.Timestamp(window_start).normalize()
    window_end = pd.Timestamp(window_end).normalize()
    if window_start > window_end:
        raise ValueError(f"window_start {window_start} > window_end {window_end}")

    pcr_by_date = pcr_by_date or {}
    oi_anomaly_by_date = oi_anomaly_by_date or {}
    sector_by_ticker = sector_by_ticker or {}

    cutoffs = profile_mod.cutoff_dates_for_walk_forward(
        window_start.strftime("%Y-%m-%d"),
        window_end.strftime("%Y-%m-%d"),
        refit_months=refit_months,
    )
    profiles_by_cutoff: dict[str, dict] = {}
    for cutoff in cutoffs:
        profiles_by_cutoff[cutoff] = profile_mod.train_profile(
            symbol_bars=universe_bars,
            regime_by_date=regime_by_date,
            cutoff_date=cutoff,
            lookback_years=lookback_years,
        )

    rows: list[dict] = []
    for d in pd.bdate_range(window_start, window_end):
        date_str = d.strftime("%Y-%m-%d")
        regime = regime_by_date.get(date_str)
        if regime is None:
            continue
        active_cutoff = _select_active_cutoff(list(profiles_by_cutoff.keys()), date_str)
        if active_cutoff is None:
            continue
        prof = profiles_by_cutoff[active_cutoff]
        pcr_today = pcr_by_date.get(date_str, {})
        oi_today = oi_anomaly_by_date.get(date_str, {})

        for ticker, bars in universe_bars.items():
            sym_prof = prof.get(ticker)
            if not sym_prof:
                continue
            reg_prof = sym_prof.get(regime)
            if reg_prof is None:
                continue
            actual = _daily_return_at(bars, date_str)
            if actual is None:
                continue
            expected = float(reg_prof["expected_return"])
            std = float(reg_prof.get("std_return", 0.0))
            z = _z_score(actual, expected, std)
            pcr_class = classify_pcr(pcr_today[ticker]) if ticker in pcr_today else "NEUTRAL"
            oi_anom = bool(oi_today.get(ticker, False))

            classification, _action = classify_break(
                expected_return=expected * 100,
                actual_return=actual * 100,
                z_score=z,
                pcr_class=pcr_class,
                oi_anomaly=oi_anom,
            )
            trade_rec = _direction_enrichment(classification, expected * 100)

            rows.append({
                "date": d,
                "ticker": ticker,
                "classification": classification,
                "z_score": z,
                "trade_rec": trade_rec,
                "regime": regime,
                "sector": sector_by_ticker.get(ticker),
                "signal_id": f"BRK-{date_str}-{ticker}",
                "expected_return": expected,
                "actual_return": actual,
                "event_geometry": classify_event_geometry(expected * 100, actual * 100),
            })

    out = pd.DataFrame(rows)
    if actionable_only and not out.empty:
        out = out[
            (out["classification"] == "OPPORTUNITY_LAG")
            & out["trade_rec"].isin({"LONG", "SHORT"})
        ].reset_index(drop=True)
    return out
