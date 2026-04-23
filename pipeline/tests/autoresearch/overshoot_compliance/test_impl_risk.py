import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import impl_risk as IR


def _events(n=200, mean_ret=0.5, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ticker": ["A"] * n,
        "direction": ["UP"] * n,
        "date": pd.bdate_range("2024-01-01", periods=n),
        "next_ret": rng.normal(mean_ret, 1.0, size=n),
    })


def test_simulate_returns_perturbed_ledger_and_report():
    ev = _events(n=200, mean_ret=0.5)
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.08, seed=1)
    assert "perturbed_sharpe" in report
    assert "perturbed_max_dd" in report
    assert "perturbed_cum_pnl" in report
    assert report["n_events_input"] == 200


def test_pass_condition_combines_three_thresholds():
    ev = _events(n=200, mean_ret=0.6)
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.10, seed=1)
    assert report["pass_cumulative_pnl_positive"] == (report["perturbed_cum_pnl"] > 0)
    assert report["pass_max_dd"] == (report["perturbed_max_dd"] <= 1.4 * report["baseline_dd_s1"])
    assert report["pass_realised_sharpe"] == (report["perturbed_sharpe"] >= 0.6 * report["baseline_sharpe_s1"])
    assert report["verdict"] in {"IMPLEMENTATION-ROBUST", "IMPLEMENTATION-SENSITIVE"}


def test_missed_fraction_reduces_trade_count():
    ev = _events(n=1000, mean_ret=0.4)
    report = IR.simulate_combined(ev, baseline_sharpe_s1=1.0, baseline_dd_s1=0.10, seed=3)
    assert report["n_events_kept"] < report["n_events_input"]
    assert report["n_events_kept"] >= int(0.88 * report["n_events_input"])
