"""§9.3 / §11B: cluster-robust SE for mean-return estimates.

Cluster level = trade_date (per Phase 0 catalog: same-day events share a regime
and are not independent observations).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm


def cluster_robust_mean_se(
    returns: Sequence[float],
    clusters: Sequence,
) -> dict:
    """Regress returns on intercept-only with cluster-robust SE.

    Returns dict ``{mean, se, t, p, n_obs, n_clusters}``. ``clusters`` is the
    cluster identifier for each observation (typically ``trade_date``).
    """
    y = np.asarray(returns, dtype=float)
    X = np.ones((len(y), 1))
    c = pd.Series(clusters)
    model = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": c.values})
    return {
        "mean": float(model.params[0]),
        "se": float(model.bse[0]),
        "t": float(model.tvalues[0]),
        "p": float(model.pvalues[0]),
        "n_obs": int(len(y)),
        "n_clusters": int(c.nunique()),
    }
