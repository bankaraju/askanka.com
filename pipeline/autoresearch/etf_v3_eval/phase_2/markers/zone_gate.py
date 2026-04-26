"""§6.3 marker: NEUTRAL band sweep at ±band_sigma σ around the signal mean.

Events whose date's v3 signal falls inside the band are gated OUT. The sweep
rolls band ∈ {0.25, 0.5, 1.0} per spec.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ZoneGateConfig:
    band_sigma: float = 0.5


def apply_zone_gate(
    events: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: ZoneGateConfig,
) -> pd.DataFrame:
    """Return events whose date's signal is OUTSIDE the ±band_sigma neutral band.

    Joins ``events`` to ``signals`` on ``trade_date``; drops rows whose signal_z
    is inside [mean − band·σ, mean + band·σ]. Population σ (ddof=0) is used so
    the band is invariant to rolling window size.

    Edge cases:
    - Empty signals frame: returns empty events frame (no signals → no outside-band dates).
    - Constant-signal series (σ=0): the band collapses to a single point and every event
      whose signal equals the mean (i.e. all of them) is dropped — yields an empty frame.
      Callers should detect σ=0 upstream.
    """
    if signals.empty or events.empty:
        return events.iloc[0:0].copy()

    s = signals.copy()
    mu = float(s["signal_z"].mean())
    sd = float(s["signal_z"].std(ddof=0))
    if sd == 0.0:
        warnings.warn(
            "apply_zone_gate: signal series has zero variance; band degenerates and all events drop",
            RuntimeWarning,
            stacklevel=2,
        )
    lo, hi = mu - cfg.band_sigma * sd, mu + cfg.band_sigma * sd
    out_band = s[(s["signal_z"] < lo) | (s["signal_z"] > hi)]
    return events.merge(out_band[["trade_date"]], on="trade_date", how="inner")
