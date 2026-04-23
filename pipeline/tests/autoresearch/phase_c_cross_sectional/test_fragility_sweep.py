import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.fragility_sweep import (
    neighborhood, evaluate_sweep,
)


def test_neighborhood_has_27_points():
    pts = neighborhood(base_alpha=0.01)
    assert len(pts) == 27
    for p in pts:
        assert {"alpha", "z_threshold_current", "z_threshold_prior"} <= set(p)


def test_neighborhood_uses_correct_prior_z_grid():
    pts = neighborhood(base_alpha=0.01)
    prior_zs = sorted({p["z_threshold_prior"] for p in pts})
    assert prior_zs == [1.5, 2.0, 2.5]


def test_neighborhood_uses_correct_current_z_grid():
    pts = neighborhood(base_alpha=0.01)
    current_zs = sorted({p["z_threshold_current"] for p in pts})
    assert current_zs == [2.5, 3.0, 3.5]


def test_neighborhood_alpha_scaling():
    pts = neighborhood(base_alpha=0.01)
    alphas = sorted({p["alpha"] for p in pts})
    # 0.8 * 0.01, 1.0 * 0.01, 1.2 * 0.01
    np.testing.assert_allclose(alphas, [0.008, 0.010, 0.012])


def test_evaluate_sweep_emits_verdict():
    rows = [{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
             "margin": 0.5} for _ in range(27)]
    result = evaluate_sweep(rows, base_margin_sign=1)
    assert result["verdict"] == "STABLE"
    assert result["n_same_sign"] == 27


def test_evaluate_sweep_flags_fragile_if_mixed():
    rows = ([{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
              "margin": 0.5}] * 10
            + [{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
                "margin": -0.5}] * 17)
    result = evaluate_sweep(rows, base_margin_sign=1)
    assert result["verdict"] == "PARAMETER-FRAGILE"
    assert result["n_same_sign"] == 10
