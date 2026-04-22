"""Logistic regression model with explicit interaction terms.

Pipeline: StandardScaler → LogisticRegression(l2, C=1.0). The three
hand-crafted interactions are added as new feature columns before fitting,
per the design spec §4.
"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_INTERACTIONS = [
    ("regime_NEUTRAL", "trust_grade_ordinal"),
    ("regime_NEUTRAL", "pcr_z_score"),
    ("sector_5d_return", "ticker_rs_10d"),
]


def build_interaction_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with interaction-term columns appended."""
    out = df.copy()
    for a, b in _INTERACTIONS:
        if a in out.columns and b in out.columns:
            out[f"{a}__x__{b}"] = out[a] * out[b]
    return out


def _prepare(X: pd.DataFrame) -> pd.DataFrame:
    return build_interaction_columns(X).fillna(0.0)


def fit_logistic(X: pd.DataFrame, y: pd.Series, random_state: int = 42) -> dict[str, Any]:
    """Fit logistic regression; return model metadata dict."""
    X_prep = _prepare(X)
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(
            C=1.0, max_iter=500, random_state=random_state,
            solver="lbfgs",
        )),
    ])
    pipeline.fit(X_prep, y)
    return {
        "pipeline": pipeline,
        "feature_names": list(X_prep.columns),
        "n_train": len(X_prep),
    }


def predict_proba(model: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    X_prep = _prepare(X)[model["feature_names"]].fillna(0.0)
    return model["pipeline"].predict_proba(X_prep)[:, 1]


def coefficients_dict(model: dict[str, Any]) -> dict[str, float]:
    """Return {feature_name: coefficient} for serialization."""
    lr = model["pipeline"].named_steps["lr"]
    return {name: float(coef) for name, coef in zip(model["feature_names"], lr.coef_[0])}
