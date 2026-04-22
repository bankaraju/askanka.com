import numpy as np
import pandas as pd
from pipeline.ta_scorer import model


def test_interactions_added():
    df = pd.DataFrame({
        "doji_flag": [1, 0, 1],
        "dist_200dma_pct": [0.01, -0.02, 0.03],
        "rsi_oversold": [1, 0, 0],
        "bullish_engulfing_flag": [0, 1, 0],
        "bearish_engulfing_flag": [0, 0, 1],
        "vol_spike_flag": [1, 0, 1],
        "hammer_flag": [0, 1, 0],
        "bb_pos": [0.2, 0.8, 0.5],
        "rsi14": [45, 72, 28],
        "sector_ret_5d": [0.01, -0.005, 0.02],
        "dist_20dma_pct": [0.01, -0.01, 0.02],
        "ret_3d": [0.005, -0.01, 0.015],
    })
    out = model.build_interaction_columns(df)
    assert "doji_x_dist200" in out.columns
    assert "doji_x_rsi_oversold" in out.columns
    assert "engulfing_x_vol_spike" in out.columns
    assert "hammer_x_bb_pos" in out.columns
    assert "rsi14_x_sector5d" in out.columns
    assert "dist20_x_ret3d" in out.columns


def test_logistic_fits_separable_synthetic():
    rng = np.random.default_rng(7)
    n = 200
    x = rng.normal(size=n)
    y = (x + rng.normal(size=n) * 0.3 > 0).astype(int)
    X = pd.DataFrame({"f1": x})
    clf = model.fit_logistic(X, y)
    assert hasattr(clf, "predict_proba")
    p = model.predict_proba(clf, X)
    assert p.shape == (n,)


def test_coefficients_dict_roundtrip():
    rng = np.random.default_rng(3)
    X = pd.DataFrame({"f1": rng.normal(size=50), "f2": rng.normal(size=50)})
    y = (X["f1"] + X["f2"] > 0).astype(int)
    clf = model.fit_logistic(X, y)
    d = model.coefficients_dict(clf, ["f1", "f2"])
    assert set(d.keys()) == {"f1", "f2", "__intercept__"}
    assert d["__intercept__"] == float(clf.intercept_[0])
