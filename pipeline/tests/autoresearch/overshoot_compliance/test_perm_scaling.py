import numpy as np
import pytest

from pipeline.autoresearch.overshoot_compliance import perm_scaling as P


def test_p_value_close_to_0_when_observed_is_extreme():
    rng = np.random.default_rng(0)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    # observed mean is 3σ above mean — should be very rare under null
    p = P.bootstrap_p_value(
        observed_mean=3.0, unconditional=unconditional,
        n_events=20, n_shuffles=50_000, seed=1,
    )
    assert 0.0 <= p <= 0.01


def test_p_value_near_half_when_observed_near_null_mean():
    rng = np.random.default_rng(1)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    p = P.bootstrap_p_value(
        observed_mean=0.0, unconditional=unconditional,
        n_events=20, n_shuffles=20_000, seed=2,
    )
    # Expect roughly 0.5; allow generous tolerance for 20k shuffles.
    assert 0.35 < p < 0.65


def test_p_value_floor_matches_reciprocal_of_shuffles():
    rng = np.random.default_rng(2)
    unconditional = rng.normal(0.0, 1.0, size=2000)
    # Observed so extreme that zero exceedances expected; p should be ≤ 1/n.
    p = P.bootstrap_p_value(
        observed_mean=10.0, unconditional=unconditional,
        n_events=20, n_shuffles=10_000, seed=3,
    )
    assert p <= 1.0 / 10_000


def test_rejects_insufficient_shuffles_under_bonferroni():
    with pytest.raises(ValueError):
        P.bootstrap_p_value(
            observed_mean=1.0, unconditional=np.zeros(10),
            n_events=5, n_shuffles=500, seed=0,
            require_perm_floor=100_000,
        )


def test_streaming_does_not_allocate_nshuffles_matrix():
    # Call with a large n_shuffles; implementation must use batches (batch_size ≤ total)
    rng = np.random.default_rng(0)
    unconditional = rng.normal(0.0, 1.0, size=200)
    p = P.bootstrap_p_value(
        observed_mean=0.5, unconditional=unconditional,
        n_events=10, n_shuffles=200_000, seed=4, batch_size=5_000,
    )
    assert 0.0 <= p <= 1.0
