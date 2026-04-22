"""Logistic regression with explicit interaction columns for TA scorer."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


_INTERACTIONS = [
    ("doji_x_dist200", "doji_flag", "dist_200dma_pct"),
    ("doji_x_rsi_oversold", "doji_flag", "rsi_oversold"),
    ("hammer_x_bb_pos", "hammer_flag", "bb_pos"),
    ("rsi14_x_sector5d", "rsi14", "sector_ret_5d"),
    ("dist20_x_ret3d", "dist_20dma_pct", "ret_3d"),
]


def build_interaction_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Build 6 interaction columns: 5 direct products + engulfing-OR x vol_spike."""
    out = df.copy()
    for name, a, b in _INTERACTIONS:
        if a in out.columns and b in out.columns:
            out[name] = out[a] * out[b]
    # OR-of-flags × vol_spike_flag for engulfing confirmation
    if all(c in out.columns for c in ("bullish_engulfing_flag", "bearish_engulfing_flag", "vol_spike_flag")):
        out["engulfing_x_vol_spike"] = (
            (out["bullish_engulfing_flag"] | out["bearish_engulfing_flag"]) * out["vol_spike_flag"]
        )
    return out


def fit_logistic(X: pd.DataFrame, y, C: float = 1.0, max_iter: int = 2000,
                 random_state: int = 42) -> LogisticRegression:
    """Fit logistic regression with specified regularization and solver."""
    clf = LogisticRegression(C=C, max_iter=max_iter, solver="lbfgs",
                             random_state=random_state)
    clf.fit(X.values, np.asarray(y))
    return clf


def predict_proba(clf: LogisticRegression, X: pd.DataFrame) -> np.ndarray:
    """Return positive-class probability from fitted logistic model."""
    return clf.predict_proba(X.values)[:, 1]


_INTERCEPT_KEY = "__intercept__"


def coefficients_dict(clf: LogisticRegression, columns: list[str]) -> dict[str, float]:
    """Extract coefficients as ordered dict keyed by column names. Includes the
    fitted intercept under the reserved key `__intercept__` so downstream
    scorers can reconstruct the logit without the sklearn estimator."""
    out = {c: float(v) for c, v in zip(columns, clf.coef_[0])}
    out[_INTERCEPT_KEY] = float(clf.intercept_[0])
    return out
