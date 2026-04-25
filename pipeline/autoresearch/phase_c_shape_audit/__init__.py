"""Phase C intraday shape audit (SP1) — descriptive forensics only.

See docs/superpowers/specs/2026-04-25-phase-c-intraday-shape-audit-design.md
for the design spec. This package produces NO trade rule, NO live signal,
and triggers NO kill-switch. It only describes properties of trades that
already happened (or should have) in the live shadow ledger.
"""
