import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.exit_rule import (
    apply_fixed_exit_rule,
    ExitRule,
)


def test_apply_fixed_exit_rule_uses_time_stop_pct():
    events = pd.DataFrame({
        "open_to_1430_pct":  [0.012, -0.020, 0.005],
        "open_to_close_pct": [0.020, -0.030, 0.010],
    })
    out = apply_fixed_exit_rule(events, ExitRule.TIME_STOP_1430)
    assert out["realized_pct"].tolist() == [0.012, -0.020, 0.005]
