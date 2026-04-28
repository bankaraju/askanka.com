"""H-2026-04-29-intraday-data-driven-v1 — twin hypothesis package.

Pre-registration package for the data-driven intraday framework that
deprecates the news-driven spread system. Spec at
``docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md``.

Two hypotheses are registered as a twin pair:

- ``H-2026-04-29-intraday-data-driven-v1-stocks`` — NIFTY-50 pool
- ``H-2026-04-29-intraday-data-driven-v1-indices`` — options-liquid index
  futures pool

Both run a pooled-weight Karpathy random search over six intraday
features (delta-PCR, ORB, volume-Z, VWAP-deviation, intraday RS-vs-sector,
intraday-trend-slope), single-leg directional, single-touch holdout
2026-04-29 → 2026-06-27 per backtesting-specs.txt §10.4 strict.

Status: PRE_REGISTERED 2026-04-29. Engine modules are stubs in this
commit; TDD build follows in subsequent commits.
"""
from __future__ import annotations
