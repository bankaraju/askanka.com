"""B0 — always predict training-set class priors."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


class AlwaysPriorBaseline:
    def __init__(self):
        self.priors_: np.ndarray | None = None

    def fit(self, train_panel: pd.DataFrame) -> "AlwaysPriorBaseline":
        counts = np.zeros(C.N_CLASSES, dtype=float)
        for c in range(C.N_CLASSES):
            counts[c] = float((train_panel["label"] == c).sum())
        self.priors_ = counts / counts.sum()
        return self

    def predict_proba(self, panel: pd.DataFrame) -> np.ndarray:
        assert self.priors_ is not None
        return np.tile(self.priors_, (len(panel), 1))
