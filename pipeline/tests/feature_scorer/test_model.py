import numpy as np
import pandas as pd


def _toy_matrix(n=300, seed=42):
    """Synthetic data where y is a known linear function of x1 with some noise."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "sector_5d_return": rng.normal(0, 0.02, n),
        "ticker_3d_momentum": rng.normal(0, 0.015, n),
        "nifty_breadth_5d": rng.uniform(0.2, 0.8, n),
        "regime_NEUTRAL": rng.integers(0, 2, n),
        "regime_RISK-OFF": 1 - rng.integers(0, 2, n),
        "regime_RISK-ON": np.zeros(n, dtype=int),
        "regime_EUPHORIA": np.zeros(n, dtype=int),
        "regime_CRISIS": np.zeros(n, dtype=int),
        "pcr_z_score": rng.normal(0, 1, n),
        "trust_grade_ordinal": rng.integers(0, 6, n),
        "ticker_rs_10d": rng.normal(0, 0.02, n),
        "sector_20d_return": rng.normal(0, 0.04, n),
        "realized_vol_60d": rng.uniform(0.15, 0.40, n),
        "dte_0_5": rng.integers(0, 2, n),
        "dte_6_15": rng.integers(0, 2, n),
        "dte_16_plus": rng.integers(0, 2, n),
    })
    df["y"] = ((df["sector_5d_return"] > 0.005) & (df["regime_NEUTRAL"] == 1)).astype(int)
    return df


def test_build_interactions_adds_three_columns():
    from pipeline.feature_scorer.model import build_interaction_columns
    df = _toy_matrix(100)
    df2 = build_interaction_columns(df)
    assert "regime_NEUTRAL__x__trust_grade_ordinal" in df2.columns
    assert "regime_NEUTRAL__x__pcr_z_score" in df2.columns
    assert "sector_5d_return__x__ticker_rs_10d" in df2.columns


def test_fit_and_predict_beats_random_on_toy_data():
    from pipeline.feature_scorer.model import fit_logistic, predict_proba
    df = _toy_matrix(500)
    model = fit_logistic(df.drop(columns=["y"]), df["y"])
    probs = predict_proba(model, df.drop(columns=["y"]))
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(df["y"], probs)
    assert auc > 0.75


def test_fit_returns_reproducible_output():
    """Same seed → same coefficients."""
    from pipeline.feature_scorer.model import fit_logistic
    df = _toy_matrix(200, seed=1)
    m1 = fit_logistic(df.drop(columns=["y"]), df["y"])
    m2 = fit_logistic(df.drop(columns=["y"]), df["y"])
    np.testing.assert_allclose(m1["pipeline"].named_steps["lr"].coef_,
                                m2["pipeline"].named_steps["lr"].coef_)


def test_predict_single_row():
    from pipeline.feature_scorer.model import fit_logistic, predict_proba
    df = _toy_matrix(300)
    model = fit_logistic(df.drop(columns=["y"]), df["y"])
    x = df.drop(columns=["y"]).iloc[[0]].copy()
    x["regime_NEUTRAL"] = 1
    x["regime_RISK-OFF"] = 0
    x["sector_5d_return"] = 0.03
    p = predict_proba(model, x)
    assert len(p) == 1
    assert 0.0 <= float(p[0]) <= 1.0
