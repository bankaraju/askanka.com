import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.regime_transition import (
    flag_regime_transitions,
)


def test_flag_regime_transitions_marks_change_dates():
    z = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03","2026-03-04"]).date,
        "zone": ["NEUTRAL","NEUTRAL","RISK-ON","RISK-ON"],
    })
    out = flag_regime_transitions(z)
    # First row has no prior, returns False; transition flagged on 03-03.
    assert out["transition"].tolist() == [False, False, True, False]
