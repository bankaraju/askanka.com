import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.slippage_grid import (
    SlippageLevel,
    apply_slippage,
    evaluate_pass_fail,
)


def test_slippage_s1_subtracts_30_bps_round_trip():
    """S1 = base + 10 bps per side ⇒ ~30 bps total round-trip cost."""
    events = pd.DataFrame({"gross_pnl_pct": [0.0050, -0.0040, 0.0010]})
    out = apply_slippage(events, SlippageLevel.S1)
    assert out["net_pnl_pct"].tolist() == pytest.approx(
        [0.0050 - 0.0030, -0.0040 - 0.0030, 0.0010 - 0.0030]
    )


def test_evaluate_pass_fail_s0_threshold():
    """OPPORTUNITY trades at S0: Sharpe >= 1.0, hit >= 55%, MaxDD <= 20%."""
    metrics = {"sharpe": 1.1, "hit_rate": 0.56, "max_dd": 0.18}
    v = evaluate_pass_fail(metrics, SlippageLevel.S0)
    assert v["pass"] is True
    metrics["sharpe"] = 0.9
    v = evaluate_pass_fail(metrics, SlippageLevel.S0)
    assert v["pass"] is False
    assert "sharpe" in v["failures"]
