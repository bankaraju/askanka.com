# pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.baselines.always_prior import AlwaysPriorBaseline


def test_always_prior_predicts_training_priors():
    train = pd.DataFrame({"label": [0]*10 + [1]*80 + [2]*10})
    val = pd.DataFrame({"label": [0, 1, 2, 1, 1]})
    b = AlwaysPriorBaseline().fit(train)
    probs = b.predict_proba(val)
    expected = np.array([[0.10, 0.80, 0.10]] * 5)
    np.testing.assert_allclose(probs, expected, atol=1e-9)


from pipeline.autoresearch.etf_stock_tail.baselines.regime_logistic import RegimeLogisticBaseline


def test_regime_logistic_learns_regime_priors():
    """If only NEUTRAL → up_tail and only DEEP_PAIN → down_tail in training,
    the baseline should reflect that on holdout."""
    rng = np.random.default_rng(0)
    n = 600
    regimes = rng.choice(["DEEP_PAIN", "NEUTRAL"], size=n)
    labels = np.where(regimes == "NEUTRAL", 2, 0)  # NEUTRAL → up_tail, DEEP_PAIN → down
    train = pd.DataFrame({"regime": regimes, "label": labels})
    val = pd.DataFrame({"regime": ["NEUTRAL", "DEEP_PAIN"], "label": [2, 0]})
    b = RegimeLogisticBaseline().fit(train)
    probs = b.predict_proba(val)
    assert int(np.argmax(probs[0])) == 2
    assert int(np.argmax(probs[1])) == 0


from pipeline.autoresearch.etf_stock_tail.baselines.interactions_logistic import InteractionsLogisticBaseline


def test_interactions_logistic_runs_end_to_end():
    rng = np.random.default_rng(2)
    n = 400
    cols = (
        ["etf_brazil_ret_1d", "etf_dollar_ret_1d", "etf_india_vix_daily_ret_1d", "etf_india_etf_ret_1d",
         "stock_sector_id", "stock_vol_z_60d", "stock_dist_from_52w_high_pct"]
    )
    df = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    df["label"] = rng.integers(0, 3, size=n)
    df["regime"] = "NEUTRAL"
    feature_cols = [c for c in cols if c not in ("stock_sector_id",)]
    base_cols = cols
    b = InteractionsLogisticBaseline().fit(df, base_cols=base_cols)
    probs = b.predict_proba(df, base_cols=base_cols)
    assert probs.shape == (n, 3)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)
