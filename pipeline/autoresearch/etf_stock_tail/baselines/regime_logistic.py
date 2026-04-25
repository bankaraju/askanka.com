"""B1 — multinomial logistic on regime-one-hot."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

from pipeline.autoresearch.etf_stock_tail import constants as C


class RegimeLogisticBaseline:
    REGIMES: tuple[str, ...] = ("DEEP_PAIN", "PAIN", "NEUTRAL", "EUPHORIA", "MEGA_EUPHORIA")

    def __init__(self):
        self.encoder_ = OneHotEncoder(categories=[list(self.REGIMES)],
                                      handle_unknown="ignore", sparse_output=False)
        self.model_ = LogisticRegression(solver="lbfgs",
                                         max_iter=200, random_state=C.RANDOM_SEED)

    def fit(self, train_panel: pd.DataFrame) -> "RegimeLogisticBaseline":
        X = self.encoder_.fit_transform(train_panel[["regime"]])
        y = train_panel["label"].astype(int).values
        self.model_.fit(X, y)
        return self

    def predict_proba(self, panel: pd.DataFrame) -> np.ndarray:
        X = self.encoder_.transform(panel[["regime"]])
        raw = self.model_.predict_proba(X)
        # model_.classes_ may be a subset if some classes absent in training;
        # expand to full N_CLASSES columns ordered [0, 1, ..., N_CLASSES-1].
        if raw.shape[1] == C.N_CLASSES:
            return raw
        out = np.zeros((len(panel), C.N_CLASSES), dtype=float)
        for j, cls in enumerate(self.model_.classes_):
            out[:, int(cls)] = raw[:, j]
        # rows with missing-class probability mass: redistribute to present classes
        # (softmax-renormalise so rows sum to 1)
        row_sums = out.sum(axis=1, keepdims=True)
        return out / np.where(row_sums == 0, 1.0, row_sums)
