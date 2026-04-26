# pipeline/tests/test_etf_v3_eval/test_implementation_risk.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.implementation_risk import (
    apply_missed_entries,
    apply_missed_exits_held_one_bar,
    apply_partial_fill,
    apply_delayed_fill_5min,
    apply_margin_shortage_block,
    apply_data_outage_once_per_month,
    run_full_scenario_set,
    pass_implementation_gate,
)


def test_missed_entries_drops_5pct_of_rows():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({"realized_pct": np.arange(1000)*0.001})
    out = apply_missed_entries(events, miss_pct=0.05, rng=rng)
    assert 940 <= len(out) <= 960   # 5% of 1000 = 50 ± noise


def test_partial_fill_halves_realized_pct():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = apply_partial_fill(events, fill_fraction=0.5)
    assert out["realized_pct"].tolist() == pytest.approx([0.005, -0.01, 0.015])


def test_pass_gate_requires_all_three_conditions():
    base = {"sharpe_s1": 1.0, "max_dd_s1": 0.20}
    stressed = {"cum_pnl": 0.05, "max_dd": 0.25, "realised_sharpe": 0.65}
    assert pass_implementation_gate(stressed, base) is True
    stressed_fail = {"cum_pnl": 0.05, "max_dd": 0.30, "realised_sharpe": 0.65}
    assert pass_implementation_gate(stressed_fail, base) is False  # DD > 1.4×0.20


# ----- Polish-guard tests (Step 4) -----

def test_missed_exits_raises_on_missing_next_bar_col():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({"realized_pct": [0.01, 0.02]})  # no open_to_close_pct
    with pytest.raises(ValueError, match="open_to_close_pct"):
        apply_missed_exits_held_one_bar(events, miss_pct=0.5, rng=rng)


def test_data_outage_raises_on_missing_trade_date():
    rng = np.random.default_rng(0)
    events = pd.DataFrame({"realized_pct": [0.01, 0.02, 0.03]})
    with pytest.raises(ValueError, match="trade_date"):
        apply_data_outage_once_per_month(events, rng=rng)


def test_margin_block_zeroes_returns_after_drawdown():
    events = pd.DataFrame({
        "trade_date": pd.date_range("2026-01-01", periods=5),
        "realized_pct": [0.05, -0.06, -0.06, 0.02, 0.03],   # cum: .05, -.01, -.07, -.05, -.02 — DD up to .12 from .05 peak
    })
    out = apply_margin_shortage_block(events, dd_threshold=0.10)
    # The third row crosses dd>0.10 (0.05 - (-0.07) = 0.12); subsequent rows zeroed
    # actually third row index=2 zeroes; index 3,4 also zero (cumulative does not recover)
    assert out["realized_pct"].iloc[2:].tolist() == [0.0, 0.0, 0.0]


def test_pass_gate_raises_on_missing_baseline_key():
    with pytest.raises(KeyError, match="sharpe_s1"):
        pass_implementation_gate(
            stressed={"cum_pnl": 0.05, "max_dd": 0.20, "realised_sharpe": 0.65},
            baseline={"max_dd_s1": 0.20}  # missing sharpe_s1
        )
