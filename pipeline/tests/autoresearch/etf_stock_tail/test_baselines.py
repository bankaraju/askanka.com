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
