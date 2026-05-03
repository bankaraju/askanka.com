import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (
    expanding_quarter_folds,
    qualifier_check,
    bh_fdr,
    permutation_p_value,
)


def test_expanding_folds_count_and_disjoint():
    idx = pd.date_range("2021-05-04", "2025-10-31", freq="B")
    folds = expanding_quarter_folds(idx, n_folds=4)
    assert len(folds) == 4
    for tr_idx, va_idx in folds:
        assert len(set(tr_idx) & set(va_idx)) == 0  # disjoint
        assert max(tr_idx) < min(va_idx)  # train always before val


def test_bh_fdr_known_pvalues():
    p = np.array([0.001, 0.01, 0.04, 0.4])
    sig = bh_fdr(p, alpha=0.05)
    # 0.001 and 0.01 should pass; 0.04 borderline; 0.4 fails
    assert sig[0] and sig[1]
    assert not sig[3]


def test_qualifier_check_all_gates():
    # All-pass case
    fold_aucs = [0.58, 0.59, 0.57, 0.60]
    p_value = 0.01
    in_sample_holdout_auc = 0.57
    n_pred_pos_isho = 12
    perm_beat_pct = 0.97
    qualified, reasons = qualifier_check(
        fold_aucs=fold_aucs, p_value=p_value, p_threshold=0.05,
        in_sample_holdout_auc=in_sample_holdout_auc, n_pred_pos_isho=n_pred_pos_isho,
        perm_beat_pct=perm_beat_pct,
    )
    assert qualified is True
    assert reasons == []

    # Std too high
    qualified2, reasons2 = qualifier_check(
        fold_aucs=[0.58, 0.45, 0.70, 0.55], p_value=0.01, p_threshold=0.05,
        in_sample_holdout_auc=0.57, n_pred_pos_isho=12, perm_beat_pct=0.97,
    )
    assert qualified2 is False
    assert any("std" in r for r in reasons2)


def test_permutation_p_value_known_signal():
    rng = np.random.default_rng(0)
    n = 300
    p = rng.uniform(0, 1, n)
    y = (p > 0.5).astype(int)  # perfectly predictable
    p_val = permutation_p_value(y_true=y, y_score=p, n_permutations=200, random_state=0)
    assert p_val < 0.05
