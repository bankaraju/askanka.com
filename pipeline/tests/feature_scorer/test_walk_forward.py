import numpy as np
import pandas as pd


def _synthetic_ticker_history(n_days=1500):
    """5.5y of synthetic ticker data with features + labels."""
    rng = np.random.default_rng(7)
    dates = pd.date_range("2021-01-01", periods=n_days, freq="B")
    df = pd.DataFrame({
        "date": dates,
        "sector_5d_return": rng.normal(0, 0.02, n_days),
        "ticker_3d_momentum": rng.normal(0, 0.015, n_days),
        "nifty_breadth_5d": rng.uniform(0.3, 0.7, n_days),
        "regime_NEUTRAL": rng.integers(0, 2, n_days),
        "regime_RISK-OFF": 0,
        "regime_RISK-ON": 0,
        "regime_EUPHORIA": 0,
        "regime_CRISIS": 0,
        "pcr_z_score": rng.normal(0, 1, n_days),
        "trust_grade_ordinal": 4,
        "ticker_rs_10d": rng.normal(0, 0.02, n_days),
        "sector_20d_return": rng.normal(0, 0.04, n_days),
        "realized_vol_60d": rng.uniform(0.15, 0.40, n_days),
        "dte_0_5": 0, "dte_6_15": 1, "dte_16_plus": 0,
    })
    df["y"] = ((df["sector_5d_return"] > 0.005) & (df["regime_NEUTRAL"] == 1)).astype(int)
    return df


def test_walk_forward_generates_multiple_folds():
    from pipeline.feature_scorer.walk_forward import run_walk_forward
    df = _synthetic_ticker_history()
    result = run_walk_forward(df, train_years=2, test_months=3, as_of="2026-04-01")
    assert len(result["folds"]) >= 4
    for fold in result["folds"]:
        assert "auc" in fold and "n_train" in fold and "n_test" in fold


def test_walk_forward_emits_mean_and_min_auc():
    from pipeline.feature_scorer.walk_forward import run_walk_forward
    df = _synthetic_ticker_history()
    result = run_walk_forward(df, train_years=2, test_months=3, as_of="2026-04-01")
    assert "mean_auc" in result
    assert "min_fold_auc" in result
    assert result["min_fold_auc"] <= result["mean_auc"]


def test_walk_forward_health_green_on_strong_synth():
    from pipeline.feature_scorer.walk_forward import run_walk_forward
    df = _synthetic_ticker_history()
    result = run_walk_forward(df, train_years=2, test_months=3, as_of="2026-04-01")
    assert result["mean_auc"] > 0.7


def test_walk_forward_thin_history_returns_unavailable():
    """Only 100 days of history — can't form even one valid fold."""
    from pipeline.feature_scorer.walk_forward import run_walk_forward
    df = _synthetic_ticker_history(n_days=100)
    result = run_walk_forward(df, train_years=2, test_months=3, as_of="2026-04-01")
    assert result["health"] == "UNAVAILABLE"
    assert len(result["folds"]) == 0


def test_walk_forward_health_bands():
    """Direct test of the health-band classifier given mean + min AUC."""
    from pipeline.feature_scorer.walk_forward import classify_health
    assert classify_health(mean_auc=0.58, min_fold_auc=0.52, n_folds=4) == "GREEN"
    assert classify_health(mean_auc=0.53, min_fold_auc=0.51, n_folds=4) == "AMBER"
    assert classify_health(mean_auc=0.60, min_fold_auc=0.48, n_folds=4) == "AMBER"  # min below 0.50
    assert classify_health(mean_auc=0.50, min_fold_auc=0.48, n_folds=4) == "RED"
    assert classify_health(mean_auc=0.60, min_fold_auc=0.55, n_folds=2) == "RED"  # n_folds < 3
