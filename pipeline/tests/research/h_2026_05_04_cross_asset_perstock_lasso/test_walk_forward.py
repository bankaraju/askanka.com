import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.walk_forward import (
    expanding_quarter_folds,
    qualifier_check,
    bh_fdr,
    bh_fdr_per_direction,
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


def test_qualifier_check_revised_two_gate_pass():
    """Post-A2 amendment (§9C): only Gate A (fold-AUC) and Gate B (BH-FDR) gate."""
    qualified, reasons = qualifier_check(
        fold_aucs=[0.55, 0.54, 0.53, 0.56],
        bh_fdr_survivor=True,
    )
    assert qualified is True
    assert reasons == []


def test_qualifier_check_fails_gate_a_below_threshold():
    """Cell with mean fold-AUC 0.52 fails Gate A at default threshold 0.53."""
    qualified, reasons = qualifier_check(
        fold_aucs=[0.50, 0.52, 0.53, 0.53],
        bh_fdr_survivor=True,
    )
    assert qualified is False
    assert any("Gate A" in r for r in reasons)


def test_qualifier_check_fails_gate_b_when_not_bh_fdr_survivor():
    qualified, reasons = qualifier_check(
        fold_aucs=[0.55, 0.55, 0.55, 0.55],
        bh_fdr_survivor=False,
    )
    assert qualified is False
    assert any("Gate B" in r for r in reasons)


def test_qualifier_check_custom_threshold():
    """Threshold is overridable for hypothesis-specific tightening (with waiver per §9C.6)."""
    qualified, _ = qualifier_check(
        fold_aucs=[0.54, 0.54, 0.54, 0.54],
        bh_fdr_survivor=True,
        fold_auc_threshold=0.55,
    )
    assert qualified is False


def test_qualifier_check_does_not_gate_on_dropped_metrics():
    """fold-std, isho-AUC, n_pred_pos, perm_beat should NOT affect the gate decision
    after A2 (§9C.2 forbids them as gates). The new signature should not even accept them."""
    import inspect
    sig = inspect.signature(qualifier_check)
    forbidden = {"fold_auc_std", "in_sample_holdout_auc", "n_pred_pos_isho", "perm_beat_pct"}
    assert not (forbidden & set(sig.parameters)), (
        f"qualifier_check signature must not accept dropped gate args: "
        f"{forbidden & set(sig.parameters)}"
    )


def test_bh_fdr_per_direction_separate_families():
    """LONG and SHORT cells form separate BH-FDR families per §9C.3."""
    # 4 LONG cells with one strong p-value, 4 SHORT cells with all weak
    cells = [
        {"ticker": "A", "direction": "LONG", "perm_p_value": 0.001},
        {"ticker": "B", "direction": "LONG", "perm_p_value": 0.5},
        {"ticker": "C", "direction": "LONG", "perm_p_value": 0.6},
        {"ticker": "D", "direction": "LONG", "perm_p_value": 0.7},
        {"ticker": "A", "direction": "SHORT", "perm_p_value": 0.1},
        {"ticker": "B", "direction": "SHORT", "perm_p_value": 0.2},
        {"ticker": "C", "direction": "SHORT", "perm_p_value": 0.3},
        {"ticker": "D", "direction": "SHORT", "perm_p_value": 0.4},
    ]
    surv = bh_fdr_per_direction(cells, alpha=0.05)
    # In LONG family of n=4, rank-1 threshold is 0.0125; p=0.001 passes
    assert surv[("A", "LONG")] is True
    assert surv[("B", "LONG")] is False
    # SHORT family has no significant p-values
    assert surv[("A", "SHORT")] is False
    assert surv[("D", "SHORT")] is False


def test_bh_fdr_per_direction_pooled_would_have_been_stricter():
    """Demonstrates why per-direction is more permissive than pooled BH-FDR
    (the rationale for §9C.3): same set of cells, smaller family denominator."""
    cells = [{"ticker": f"T{i}", "direction": "LONG" if i < 50 else "SHORT",
              "perm_p_value": 0.0008 if i == 0 else 0.5}
             for i in range(100)]
    surv = bh_fdr_per_direction(cells, alpha=0.05)
    # Per-direction LONG family n=50: rank-1 threshold = 0.001; 0.0008 passes
    assert surv[("T0", "LONG")] is True
    # Pooled n=100: rank-1 threshold = 0.0005; 0.0008 would fail
    pooled = bh_fdr(np.array([c["perm_p_value"] for c in cells]), alpha=0.05)
    assert pooled[0] is np.False_ or bool(pooled[0]) is False


def test_permutation_p_value_known_signal():
    rng = np.random.default_rng(0)
    n = 300
    p = rng.uniform(0, 1, n)
    y = (p > 0.5).astype(int)  # perfectly predictable
    p_val = permutation_p_value(y_true=y, y_score=p, n_permutations=200, random_state=0)
    assert p_val < 0.05
