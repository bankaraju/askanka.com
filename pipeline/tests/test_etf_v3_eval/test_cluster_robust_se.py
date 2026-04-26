import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.cluster_robust_se import (
    cluster_robust_mean_se,
)


def test_cluster_robust_se_collapses_within_cluster():
    """If all observations within a cluster are identical, SE depends on n_clusters,
    not n_observations. statsmodels reference: 100 obs in 5 clusters of 20 should
    have SE ≈ between-cluster SE / sqrt(5)."""
    np.random.seed(0)
    n_clusters, per = 5, 20
    cluster_means = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    rets = np.repeat(cluster_means, per)
    clusters = np.repeat(np.arange(n_clusters), per)
    out = cluster_robust_mean_se(rets, clusters)
    expected_se = np.std(cluster_means, ddof=1) / np.sqrt(n_clusters)
    assert out["mean"] == pytest.approx(3.0)
    assert out["se"] == pytest.approx(expected_se, rel=1e-2)
    assert out["n_clusters"] == 5
    assert out["n_obs"] == 100
