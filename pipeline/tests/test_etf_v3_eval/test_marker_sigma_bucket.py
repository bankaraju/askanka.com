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
