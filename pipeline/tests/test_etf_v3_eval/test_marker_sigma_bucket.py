import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.sigma_bucket import (
    bucket_event_sigma,
    SigmaBucket,
)


def test_bucket_event_sigma_assigns_correct_bucket():
    events = pd.DataFrame({"break_z": [2.1, 2.6, 3.6, 4.0, 1.5]})
    out = bucket_event_sigma(events)
    assert out["bucket"].tolist() == [
        SigmaBucket.MILD, SigmaBucket.RARE,
        SigmaBucket.EXTREME, SigmaBucket.EXTREME,
        SigmaBucket.SUB_THRESHOLD,
    ]


def test_bucket_event_sigma_handles_empty_frame():
    """Empty events frame returns an empty frame with the bucket column present."""
    events = pd.DataFrame({"break_z": []})
    out = bucket_event_sigma(events)
    assert "bucket" in out.columns
    assert len(out) == 0


def test_bucket_event_sigma_raises_on_missing_column():
    events = pd.DataFrame({"some_other_col": [1.0, 2.0]})
    with pytest.raises(ValueError, match="not found"):
        bucket_event_sigma(events)


def test_bucket_event_sigma_handles_negative_z_via_abs():
    """Negative z values are bucketed by their absolute value."""
    events = pd.DataFrame({"break_z": [-2.1, -3.6, -1.0]})
    out = bucket_event_sigma(events)
    assert out["bucket"].tolist() == [SigmaBucket.MILD, SigmaBucket.EXTREME, SigmaBucket.SUB_THRESHOLD]
