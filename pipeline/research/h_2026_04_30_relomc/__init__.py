"""H-2026-04-30-RELOMC-EUPHORIA forward-only paper engine.

Spec: docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md
Registry: docs/superpowers/hypothesis-registry.jsonl

Trade rule:
- T-1 close: V3 CURATED-30 regime label = EUPHORIA
- T-day 09:15 IST: open LONG RELIANCE / SHORT (BPCL+IOC), equal-notional dollar-neutral
- Hold 5 trading days; exit at T+5 14:25 IST OR if basket pnl <= -3.0% (whichever first)

Holdout window: 2026-05-01 -> 2027-04-30. Single-touch locked.
"""
