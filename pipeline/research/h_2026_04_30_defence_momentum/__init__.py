"""H-2026-04-30-DEFENCE-* forward-only paper engine bundle.

Two hypotheses share this package:
- H-2026-04-30-DEFENCE-IT-NEUTRAL    (LONG HAL+BEL+BDL / SHORT TCS+INFY+WIPRO, NEUTRAL at T-1, 5d)
- H-2026-04-30-DEFENCE-AUTO-RISKON   (LONG HAL+BEL / SHORT TMPV+MARUTI, RISK-ON at T-1, 5d)

Both use ATR(14)-scaled per-leg sizing — the design improvement over the
failing equal-notional in-sample mode. The IT-NEUTRAL variant has no
per-leg vol cap; the AUTO-RISKON variant caps each leg at 2x the
equal-notional baseline weight to prevent single-leg blowups.

Spec: docs/superpowers/specs/2026-04-30-defence-momentum-design.md
Registry: docs/superpowers/hypothesis-registry.jsonl
"""
