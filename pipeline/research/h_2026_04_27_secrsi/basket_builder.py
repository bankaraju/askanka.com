"""SECRSI basket builder — stub.

Will rank sectors by snapshot score, pick top-2 / bottom-2 sectors, then
the 2 best/worst stocks within each. Returns the 8-leg market-neutral
basket. Spec §3.2 + §3.3.

PRE_REGISTERED 2026-04-27; implementation follows in TDD commits.
"""
from __future__ import annotations


def build_basket(*args, **kwargs):
    raise NotImplementedError("SECRSI basket_builder.build_basket — TDD build pending")
