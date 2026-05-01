"""H-2026-05-01-NEUTRAL-001 — Neutral Intraday Fair-Value Reversion (NIFR) v1.

Spec: docs/superpowers/specs/neutral_intraday_fair_value_reversion_spec.md

This package is in EXPLORATION phase. Track 1 (dispersion_explorer.py) runs a
forensic 5y replay to characterise the NIFR setup distribution across NEUTRAL
days BEFORE registration. The single-touch holdout slot is NOT consumed by
exploration — it is consumed only when the engine package is built and the
Karpathy search runs at registration freeze.

Track 2 (the engine: feature_library.py + fair_value_trigger.py + ...) is
deferred until Track 1 dispersion analysis confirms the setup is separable
from noise in NEUTRAL.
"""

HYPOTHESIS_ID = "H-2026-05-01-NEUTRAL-001"
HOLDOUT_OPEN = "2026-05-11"
HOLDOUT_CLOSE = "2026-08-29"
HOLDOUT_EXTEND_TO = "2026-10-31"
MIN_HOLDOUT_N = 120
