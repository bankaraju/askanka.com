import json

from pipeline.autoresearch.etf_stock_tail.fragility import (
    PERTURBATIONS,
    fragility_verdict,
)


def test_six_perturbations_locked():
    assert len(PERTURBATIONS) == 6
    names = [p["name"] for p in PERTURBATIONS]
    assert "dropout_minus_10pct" in names
    assert "dropout_plus_10pct" in names
    assert "weight_decay_minus_20pct" in names
    assert "weight_decay_plus_20pct" in names
    assert "sigma_1_0" in names
    assert "sigma_2_0" in names


def test_stable_when_5_of_6_within_tolerance():
    base_ce = 1.000
    runs = [
        {"name": "dropout_minus_10pct",  "holdout_ce": 1.005, "passing": True},
        {"name": "dropout_plus_10pct",   "holdout_ce": 1.015, "passing": True},
        {"name": "weight_decay_minus_20pct", "holdout_ce": 1.010, "passing": True},
        {"name": "weight_decay_plus_20pct",  "holdout_ce": 0.995, "passing": True},
        {"name": "sigma_1_0", "holdout_ce": 0.992, "passing": True},
        {"name": "sigma_2_0", "holdout_ce": 1.080, "passing": False},  # outside tol
    ]
    v = fragility_verdict(base_ce, runs)
    assert v["verdict"] == "STABLE"
    assert v["n_passing"] == 5


def test_fragile_when_only_3_of_6():
    base_ce = 1.000
    runs = [
        {"name": "dropout_minus_10pct",  "holdout_ce": 1.005, "passing": True},
        {"name": "dropout_plus_10pct",   "holdout_ce": 1.080, "passing": False},
        {"name": "weight_decay_minus_20pct", "holdout_ce": 1.010, "passing": True},
        {"name": "weight_decay_plus_20pct",  "holdout_ce": 1.080, "passing": False},
        {"name": "sigma_1_0", "holdout_ce": 0.992, "passing": True},
        {"name": "sigma_2_0", "holdout_ce": 1.080, "passing": False},
    ]
    v = fragility_verdict(base_ce, runs)
    assert v["verdict"] == "FRAGILE"
    assert v["n_passing"] == 3
