"""Auto Spread Discovery Engine (ASDE).

v0: pair enumeration + cardinality bookkeeping for BH-FDR multiplicity.
v1+: full 5y backtest of the enumerated family + ranked candidate report.

See `docs/superpowers/specs/2026-04-30-auto-spread-discovery-engine-design.md`
for the design lock and verdict bar.

Module names avoid the strategy-gate kill-switch regex
(`*_engine.py` / `*_backtest.py` / `*_signal_generator.py`) — discovery
modules use `proposer.py` / `validator.py` / `enumerator.py`.
"""
