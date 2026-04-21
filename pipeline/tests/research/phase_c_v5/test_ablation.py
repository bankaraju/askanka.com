"""Tests for phase_c_v5.ablation (cross-variant comparison)."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.research.phase_c_v5 import ablation


def _ledger(n=100, winrate=0.60, seed=1):
    import numpy as np
    rng = np.random.default_rng(seed)
    returns = rng.choice([0.02, -0.015], size=n, p=[winrate, 1 - winrate])
    return pd.DataFrame({
        "notional_total_inr": [50_000] * n,
        "pnl_net_inr": returns * 50_000,
    })


def test_ablation_produces_row_per_ledger(tmp_path):
    (tmp_path / "v50_a.parquet")
    ledger_map = {"v50_a": _ledger(n=120, winrate=0.6),
                  "v51": _ledger(n=80, winrate=0.45, seed=2)}
    out = ablation.compute_comparison(ledger_map, n_tests=12, alpha_family=0.01)
    assert set(out["variant"]) == {"v50_a", "v51"}
    assert {"sharpe_point", "sharpe_lo", "hit_rate", "binomial_p",
            "alpha_per_test", "passes"}.issubset(out.columns)


def test_ablation_pass_when_hit_rate_high_and_p_low():
    ledger_map = {"winner": _ledger(n=500, winrate=0.65, seed=3),
                   "loser":  _ledger(n=500, winrate=0.48, seed=4)}
    out = ablation.compute_comparison(ledger_map, n_tests=12, alpha_family=0.01)
    # winner passes Bonferroni; loser fails
    assert out.set_index("variant").loc["winner", "passes"]
    assert not out.set_index("variant").loc["loser", "passes"]
