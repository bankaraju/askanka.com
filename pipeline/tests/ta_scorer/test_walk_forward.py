import numpy as np
import pandas as pd
from pipeline.ta_scorer import walk_forward


def test_classify_health_green():
    h = walk_forward.classify_health(mean_auc=0.58, min_fold_auc=0.53, n_folds=5)
    assert h == "GREEN"


def test_classify_health_amber_on_low_min_fold():
    h = walk_forward.classify_health(mean_auc=0.56, min_fold_auc=0.50, n_folds=4)
    assert h == "AMBER"


def test_classify_health_amber_on_mid_mean():
    h = walk_forward.classify_health(mean_auc=0.53, min_fold_auc=0.52, n_folds=3)
    assert h == "AMBER"


def test_classify_health_red_on_poor_mean():
    h = walk_forward.classify_health(mean_auc=0.48, min_fold_auc=0.45, n_folds=4)
    assert h == "RED"


def test_classify_health_unavailable_on_few_folds():
    h = walk_forward.classify_health(mean_auc=0.60, min_fold_auc=0.58, n_folds=2)
    assert h == "UNAVAILABLE"


def test_walk_forward_strong_signal_is_green():
    # Build synthetic strong signal over 3 years of business days
    rng = np.random.default_rng(11)
    n = 3 * 252
    dates = pd.date_range("2022-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    f1 = rng.normal(size=n)
    y = (f1 + rng.normal(size=n) * 0.3 > 0).astype(int)
    frame = pd.DataFrame({"date": dates, "f1": f1, "y": y})
    res = walk_forward.run_walk_forward(frame, train_years=2, test_months=3,
                                        as_of=dates[-1], max_folds=6)
    assert res["health"] == "GREEN"
    assert res["mean_auc"] >= 0.55
    assert res["n_folds"] >= 3
