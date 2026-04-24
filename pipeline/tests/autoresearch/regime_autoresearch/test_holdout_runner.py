"""BH-FDR q=0.1 batch correctness + whichever-first cadence trigger."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.holdout_runner import (
    bh_fdr_threshold, should_fire_batch,
)


def test_bh_fdr_threshold_known_case():
    # p-values sorted ascending, q=0.1, m=10
    pvals = [0.001, 0.004, 0.02, 0.035, 0.05, 0.08, 0.10, 0.15, 0.3, 0.5]
    thresh = bh_fdr_threshold(pvals, q=0.1)
    # Largest k s.t. p_(k) <= k/m * q: here k=5 → 0.05 <= 0.05 ✓; k=6 → 0.08 > 0.06 ✗
    assert thresh == pvals[4]


def test_bh_fdr_no_survivors():
    pvals = [0.5, 0.6, 0.7]
    assert bh_fdr_threshold(pvals, q=0.1) is None


def test_fire_cadence_on_calendar():
    assert should_fire_batch(days_since_last=31, count_accumulated=1) is True


def test_fire_cadence_on_accumulated():
    assert should_fire_batch(days_since_last=5, count_accumulated=10) is True


def test_no_fire_when_neither():
    assert should_fire_batch(days_since_last=5, count_accumulated=3) is False
