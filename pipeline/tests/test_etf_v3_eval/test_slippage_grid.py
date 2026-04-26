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


def test_apply_slippage_raises_on_missing_column():
    events = pd.DataFrame({"some_other_col": [0.01, -0.02]})
    with pytest.raises(ValueError, match="not found"):
        apply_slippage(events, SlippageLevel.S0)


def test_evaluate_pass_fail_raises_on_missing_metric():
    metrics = {"sharpe": 1.5, "hit_rate": 0.6}  # missing max_dd
    with pytest.raises(ValueError, match="missing key 'max_dd'"):
        evaluate_pass_fail(metrics, SlippageLevel.S0)


def test_evaluate_pass_fail_s3_is_informational_and_passes():
    """S3 always returns pass=True with informational flag, regardless of metrics."""
    metrics = {"sharpe": -10.0, "hit_rate": 0.0, "max_dd": 0.99}  # garbage
    v = evaluate_pass_fail(metrics, SlippageLevel.S3)
    assert v["pass"] is True
    assert v["informational"] is True
    assert v["failures"] == []
    assert v["level"] == "s3"


def test_evaluate_pass_fail_collects_all_failures():
    """When all 3 metrics fail at S0, all 3 should appear in failures list."""
    metrics = {"sharpe": 0.5, "hit_rate": 0.40, "max_dd": 0.30}
    v = evaluate_pass_fail(metrics, SlippageLevel.S0)
    assert v["pass"] is False
    assert set(v["failures"]) == {"sharpe", "hit_rate", "max_dd"}


def test_pass_thresholds_are_publicly_importable_for_t23_reporting():
    """T23 reports must state exact thresholds — confirm constants are public."""
    from pipeline.autoresearch.etf_v3_eval.phase_2.slippage_grid import (
        ROUND_TRIP_COST,
        PASS_THRESHOLDS,
    )
    assert ROUND_TRIP_COST[SlippageLevel.S1] == 0.0030
    assert PASS_THRESHOLDS[SlippageLevel.S0]["sharpe"] == 1.0
