import json
from pathlib import Path
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.coef_delta import (
    compute_weekly_delta_magnitude,
    flag_high_rotation_dates,
)


def test_compute_weekly_delta_magnitude():
    weights_a = {"E1": 0.5, "E2": 0.5}
    weights_b = {"E1": 0.6, "E2": 0.4}   # |delta| L2 = sqrt(0.01+0.01) = 0.1414
    mag = compute_weekly_delta_magnitude(weights_a, weights_b)
    assert mag == pytest.approx(0.1414, abs=1e-3)


def test_flag_high_rotation_dates_uses_p75_threshold():
    df = pd.DataFrame({
        "refit_anchor": pd.to_datetime(["2026-01-01","2026-01-08","2026-01-15","2026-01-22"]),
        "delta_mag":    [0.1, 0.2, 0.3, 0.9],
    })
    out, threshold = flag_high_rotation_dates(df, percentile=75)
    assert out["high_rotation"].tolist() == [False, False, False, True]
    assert threshold == pytest.approx(0.45)
