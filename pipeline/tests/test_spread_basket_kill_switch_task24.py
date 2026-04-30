"""Tests for the Task #24 surgical kill-list applied to INDIA_SPREAD_PAIRS.

Verifies the 4 confirmed-fail baskets are filtered out of the runtime list
(returned by `_india_spread_pairs()`) but remain present in the legacy
deprecated list (preserved for forensic reference).

Spec: docs/SYSTEM_FAQ.md §17, docs/research/india_spread_pairs_backtest/findings_2026-04-30.md
"""
from __future__ import annotations

import pytest

from pipeline import config


def _names(basket_list) -> set[str]:
    return {b["name"] for b in basket_list}


def test_killed_baskets_present_in_deprecated_list():
    """The legacy list keeps every basket — kills are filter-time, not source-time."""
    deprecated_names = _names(config.INDIA_SPREAD_PAIRS_DEPRECATED)
    for name in config.SPREAD_BASKETS_KILLED_BY_TASK24:
        assert name in deprecated_names, f"{name} missing from INDIA_SPREAD_PAIRS_DEPRECATED"


def test_killed_baskets_absent_from_runtime_list():
    """The runtime list (used by run_signals etc.) excludes all killed baskets."""
    runtime_names = _names(config.INDIA_SPREAD_PAIRS)
    for name in config.SPREAD_BASKETS_KILLED_BY_TASK24:
        assert name not in runtime_names, (
            f"{name} should be killed by Task #24 verdict but is still in INDIA_SPREAD_PAIRS"
        )


def test_runtime_list_size_equals_deprecated_minus_kills():
    expected = len(config.INDIA_SPREAD_PAIRS_DEPRECATED) - len(config.SPREAD_BASKETS_KILLED_BY_TASK24)
    assert len(config.INDIA_SPREAD_PAIRS) == expected


def test_unkilled_baskets_pass_through():
    """A handful of marginal baskets that did NOT get killed should still be present."""
    runtime_names = _names(config.INDIA_SPREAD_PAIRS)
    # These were promoted for re-registration as data-primary hypotheses or kept marginal
    for survivor in ("Defence vs IT", "Defence vs Auto", "PSU Commodity vs Banks", "Coal vs OMCs"):
        assert survivor in runtime_names, f"{survivor} should still be in runtime list"


def test_kill_list_size_is_4():
    assert len(config.SPREAD_BASKETS_KILLED_BY_TASK24) == 4
