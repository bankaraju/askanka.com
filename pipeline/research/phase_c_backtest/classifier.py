"""Phase C decision-matrix replay using historical inputs.

Reuses pipeline.autoresearch.reverse_regime_breaks.classify_break exactly
so the backtest can never drift from the live engine's logic.
"""
from __future__ import annotations

from pipeline.autoresearch.reverse_regime_breaks import classify_break, classify_pcr


def _z_score(actual: float, expected: float, std: float) -> float:
    """Z-score with noise-floor guard.

    Mirrors `reverse_regime_breaks.py:370` which uses `expected_std > 0.1` in
    PERCENT space. Our profile stores returns in fractional space, so the
    unit-equivalent threshold here is 0.001 (= 0.1% = 10 bps daily std).
    """
    if std <= 0.001:
        return 0.0
    return (actual - expected) / std


def classify_at_date(
    symbol: str,
    regime: str,
    actual_return: float,
    profile: dict,
    pcr: float | None,
    oi_anomaly: bool,
) -> tuple[str, str, float]:
    """Classify a single (symbol, date) using point-in-time inputs.

    Returns (label, action, z_score). For symbols absent from the profile,
    returns ('UNCERTAIN', 'HOLD', 0.0).
    """
    sym_prof = profile.get(symbol, {})
    reg_prof = sym_prof.get(regime)
    if reg_prof is None:
        return ("UNCERTAIN", "HOLD", 0.0)
    expected = float(reg_prof["expected_return"])
    std = float(reg_prof.get("std_return", 0.0))
    z = _z_score(actual_return, expected, std)
    pcr_class = classify_pcr(pcr) if pcr is not None else "NEUTRAL"
    label, action = classify_break(
        expected_return=expected,
        actual_return=actual_return,
        z_score=z,
        pcr_class=pcr_class,
        oi_anomaly=oi_anomaly,
    )
    return (label, action, z)


def classify_universe(
    symbols: list[str],
    regime: str,
    profile: dict,
    actual_returns: dict[str, float],
    pcr_by_symbol: dict[str, float | None],
    oi_anomaly_by_symbol: dict[str, bool],
) -> dict[str, dict]:
    """Classify every symbol in the universe for a single date.

    Symbols missing from ``actual_returns`` are skipped (no label emitted).
    Symbols missing from ``pcr_by_symbol`` / ``oi_anomaly_by_symbol`` are
    treated as PCR=None (-> NEUTRAL) and oi_anomaly=False respectively.
    """
    out: dict[str, dict] = {}
    for sym in symbols:
        if sym not in actual_returns:
            continue
        label, action, z = classify_at_date(
            symbol=sym,
            regime=regime,
            actual_return=actual_returns[sym],
            profile=profile,
            pcr=pcr_by_symbol.get(sym),
            oi_anomaly=oi_anomaly_by_symbol.get(sym, False),
        )
        out[sym] = {"label": label, "action": action, "z_score": z}
    return out
