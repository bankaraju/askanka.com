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


def check_regime_coverage(holdout: pd.DataFrame, train: pd.DataFrame | None = None) -> None:
    """Holdout must cover the regimes the model was trained on.

    Per Amendment A1.5 (2026-04-25) — the original spec hardcoded the V5 zone
    taxonomy (DEEP_PAIN/PAIN/NEUTRAL/EUPHORIA/MEGA_EUPHORIA) but the live regime
    engine emits V4 labels (CAUTION/NEUTRAL/RISK-ON/EUPHORIA/RISK-OFF). The
    revised check is data-driven:

      * "Material" regimes are those that appear in train with >= MIN days.
      * UNKNOWN is excluded as a sentinel.
      * Each material regime must appear in holdout with >= MIN days too.

    If train is not provided, falls back to checking that the *holdout's own*
    most-frequent 3 regimes each have >= MIN days (lighter guard).
    """
    if "regime" not in holdout.columns:
        return  # caller chose not to enforce
    holdout_daily = holdout.drop_duplicates(subset=["date"])[["date", "regime"]]
    holdout_counts = holdout_daily["regime"].value_counts().to_dict()
    holdout_counts.pop("UNKNOWN", None)

    min_days = C.MIN_REGIME_DAYS_IN_HOLDOUT

    if train is not None and "regime" in train.columns:
        train_daily = train.drop_duplicates(subset=["date"])[["date", "regime"]]
        train_counts = train_daily["regime"].value_counts().to_dict()
        train_counts.pop("UNKNOWN", None)
        material = sorted(r for r, n in train_counts.items() if n >= min_days)
        if material:
            insufficient = [r for r in material if holdout_counts.get(r, 0) < min_days]
            if insufficient:
                raise InsufficientRegimeCoverage(
                    f"holdout missing regime coverage for material train regimes "
                    f"(need >={min_days} days each): {insufficient}; "
                    f"holdout_counts={holdout_counts}; train_counts={train_counts}"
                )
            return
        # No material train regimes — fall through to holdout-only fallback below.

    # Fallback when train not provided: require >=3 regimes meet MIN in holdout.
    n_material_in_holdout = sum(1 for n in holdout_counts.values() if n >= min_days)
    if n_material_in_holdout < 3:
        raise InsufficientRegimeCoverage(
            f"holdout has fewer than 3 regimes with >={min_days} days; "
            f"counts={holdout_counts}"
        )
