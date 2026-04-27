"""SECRSI in-sample backtest — stub.

Trading-rule file under the strategy gate (matches ``*_backtest.py``).
Pre-registered as H-2026-04-27-003 in
``docs/superpowers/hypothesis-registry.jsonl``. Spec at
``docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md``.

Will replay the in-sample window 2024-04-27 -> 2026-04-26 mechanically:
each trading day, take 11:00 snapshot, build the 8-leg basket, simulate
ATR(14)*2 stops + 14:30 mechanical exit, accumulate per-basket P&L, and
emit the slippage grid (S0 / S1 / S2). Per backtesting-specs.txt §0-16.

PRE_REGISTERED 2026-04-27; implementation follows in TDD commits.
"""
from __future__ import annotations


def run_backtest(*args, **kwargs):
    raise NotImplementedError(
        "SECRSI secrsi_backtest.run_backtest — TDD build pending. "
        "See docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md §6."
    )
