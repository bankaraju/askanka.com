import pandas as pd
import numpy as np
import pytest

from pipeline.autoresearch.overshoot_compliance import fragility as F


def _events(n, mean_ret, z_start=3.0):
    return pd.DataFrame([
        {"ticker": "A", "direction": "UP", "z": z_start + i * 0.01,
         "next_ret": mean_ret + (i - n / 2) * 0.01}
        for i in range(n)
    ])


def test_neighborhood_grid_is_27_points():
    assert len(F.neighborhood_grid()) == 27


def test_fragility_report_has_stability_flags():
    ev_by_window = {
        15: _events(40, mean_ret=0.5),
        20: _events(40, mean_ret=0.6),
        25: _events(40, mean_ret=0.55),
    }
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    for k in ("chosen_sharpe", "neighbor_rows",
              "pct_positive_pnl", "median_sharpe_ratio", "sign_flip_pct",
              "stable_positive", "stable_sharpe", "stable_sign",
              "verdict"):
        assert k in report
    assert len(report["neighbor_rows"]) == 27


def test_fragility_verdict_pass_when_all_three_stable():
    ev_by_window = {w: _events(40, mean_ret=0.5) for w in (15, 20, 25)}
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    assert report["verdict"] in {"STABLE", "PARAMETER-FRAGILE"}


def test_fragility_verdict_fail_when_majority_sign_flip():
    ev_by_window = {w: _events(20, mean_ret=-0.4) for w in (15, 20, 25)}
    chosen = {"min_z": 3.0, "roll_window": 20, "cost_pct": 0.30}
    report = F.evaluate(ev_by_window, chosen)
    assert report["verdict"] == "PARAMETER-FRAGILE"
