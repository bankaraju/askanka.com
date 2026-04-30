"""Sector pair divergence-reversion study — discovery-only research.

Spec: docs/research/sector_pair_divergence/2026-04-30-design.md

Tests whether days when normally-tight sector pairs diverge materially
are followed by a next-day pull-back trade with positive expectation.
Reads from the canonical sector panel; emits no trading rules.

If results survive the verdict bar in `run_study.py`, the next step is a
fresh single-touch hypothesis under backtesting-specs.txt §10.4 — NOT a
direct live shadow.
"""
