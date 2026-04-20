"""Ablation variants for Phase C backtest.

Runs the same (symbols, regime, profile, actual_returns) through four
variants of the input signal surface to attribute where Phase C's edge
comes from:

- ``full``     — original PCR + OI inputs
- ``no_oi``    — OI anomaly forced to False for all symbols
- ``no_pcr``   — PCR forced to None (-> NEUTRAL class) for all symbols
- ``degraded`` — both PCR and OI suppressed (worst-case data outage)

The defense surface is that ``degraded`` must remain non-negative in
aggregate — if removing both inputs destroys edge, the classification
matrix is the source of edge, not the data.
"""
from __future__ import annotations

from .classifier import classify_universe


def run_all_variants(
    symbols: list[str],
    regime: str,
    profile: dict,
    actual_returns: dict[str, float],
    pcr_by_symbol: dict[str, float | None],
    oi_anomaly_by_symbol: dict[str, bool],
) -> dict[str, dict[str, dict]]:
    """Return ``{variant_name: {symbol: {label, action, z_score}}}``.

    The replacements cover every symbol in ``symbols`` (not just keys that
    happen to be present in the original dicts) so that downstream
    classification sees a uniformly-suppressed input surface.
    """
    no_oi = {sym: False for sym in symbols}
    no_pcr: dict[str, float | None] = {sym: None for sym in symbols}

    return {
        "full": classify_universe(
            symbols=symbols,
            regime=regime,
            profile=profile,
            actual_returns=actual_returns,
            pcr_by_symbol=pcr_by_symbol,
            oi_anomaly_by_symbol=oi_anomaly_by_symbol,
        ),
        "no_oi": classify_universe(
            symbols=symbols,
            regime=regime,
            profile=profile,
            actual_returns=actual_returns,
            pcr_by_symbol=pcr_by_symbol,
            oi_anomaly_by_symbol=no_oi,
        ),
        "no_pcr": classify_universe(
            symbols=symbols,
            regime=regime,
            profile=profile,
            actual_returns=actual_returns,
            pcr_by_symbol=no_pcr,
            oi_anomaly_by_symbol=oi_anomaly_by_symbol,
        ),
        "degraded": classify_universe(
            symbols=symbols,
            regime=regime,
            profile=profile,
            actual_returns=actual_returns,
            pcr_by_symbol=no_pcr,
            oi_anomaly_by_symbol=no_oi,
        ),
    }
