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
