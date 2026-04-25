# pipeline/autoresearch/etf_stock_tail/splits.py
"""Train / validation / holdout split + regime coverage check."""
from __future__ import annotations

import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


class InsufficientRegimeCoverage(RuntimeError):
    pass


def split_panel(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partition panel by date into (train, val, holdout)."""
    d = pd.to_datetime(panel["date"])
    train_mask = (d >= C.TRAIN_START) & (d <= C.TRAIN_END)
    val_mask   = (d >= C.VAL_START)   & (d <= C.VAL_END)
    holdout_mask = (d >= C.HOLDOUT_START) & (d <= C.HOLDOUT_END)
    return (
        panel[train_mask].reset_index(drop=True),
        panel[val_mask].reset_index(drop=True),
        panel[holdout_mask].reset_index(drop=True),
    )


def check_regime_coverage(holdout: pd.DataFrame) -> None:
    """Each of 5 regimes must have >= MIN_REGIME_DAYS_IN_HOLDOUT distinct dates in holdout."""
    if "regime" not in holdout.columns:
        return  # caller chose not to enforce
    daily = holdout.drop_duplicates(subset=["date"])[["date", "regime"]]
    counts = daily["regime"].value_counts().to_dict()
    expected = ["DEEP_PAIN", "PAIN", "NEUTRAL", "EUPHORIA", "MEGA_EUPHORIA"]
    insufficient = [r for r in expected if counts.get(r, 0) < C.MIN_REGIME_DAYS_IN_HOLDOUT]
    if insufficient:
        raise InsufficientRegimeCoverage(
            f"holdout missing regime coverage (need >={C.MIN_REGIME_DAYS_IN_HOLDOUT} days each): "
            f"{insufficient}; counts={counts}"
        )
