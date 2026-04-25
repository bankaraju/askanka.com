"""B2 — logistic regression with 4 hand-designed ETF × stock-context interactions.

Interactions are LOCKED in C.B2_INTERACTIONS — must not be modified after registration.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from pipeline.autoresearch.etf_stock_tail import constants as C


def _build_interactions(panel: pd.DataFrame) -> np.ndarray:
    """Compute the 4 hand-designed interactions from C.B2_INTERACTIONS."""
    out = np.zeros((len(panel), len(C.B2_INTERACTIONS)), dtype=float)
    for j, (a, b) in enumerate(C.B2_INTERACTIONS):
        a_col = a if a in panel.columns else f"stock_{a}"
        b_col = b if b in panel.columns else f"stock_{b}"
        out[:, j] = panel[a_col].values * panel[b_col].values
    return out


class InteractionsLogisticBaseline:
    def __init__(self):
        self.scaler_ = StandardScaler()
        self.model_ = LogisticRegression(
            solver="lbfgs", max_iter=500,
            C=1.0, random_state=C.RANDOM_SEED,
        )

    def _stack(self, panel: pd.DataFrame, base_cols: Sequence[str]) -> np.ndarray:
        base = panel[list(base_cols)].values
        inter = _build_interactions(panel)
        return np.hstack([base, inter])

    def fit(self, train_panel: pd.DataFrame, base_cols: Sequence[str]) -> "InteractionsLogisticBaseline":
        X = self._stack(train_panel, base_cols)
        X = self.scaler_.fit_transform(X)
        y = train_panel["label"].astype(int).values
        self.model_.fit(X, y)
        return self

    def predict_proba(self, panel: pd.DataFrame, base_cols: Sequence[str]) -> np.ndarray:
        X = self._stack(panel, base_cols)
        X = self.scaler_.transform(X)
        return self.model_.predict_proba(X)
