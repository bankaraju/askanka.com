"""SECRSI forward shadow paper-trade ledger — stub.

Will run on the schedule (11:00 IST OPEN, 14:30 IST CLOSE) to write paper
trades to ``pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv``
mirroring the ``H-2026-04-26-001`` ledger schema. Used during the
holdout window 2026-04-28 -> 2026-07-31. Spec §8.

PRE_REGISTERED 2026-04-27; implementation follows after the in-sample
backtest establishes feasibility.
"""
from __future__ import annotations


def open_basket(*args, **kwargs):
    raise NotImplementedError("SECRSI forward_shadow.open_basket — pending")


def close_basket(*args, **kwargs):
    raise NotImplementedError("SECRSI forward_shadow.close_basket — pending")
