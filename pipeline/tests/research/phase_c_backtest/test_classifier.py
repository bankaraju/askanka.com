from __future__ import annotations

import pytest

from pipeline.research.phase_c_backtest import classifier


def test_classify_at_date_lagging_with_pcr_agree_is_opportunity():
    profile = {"RELIANCE": {"NEUTRAL": {"expected_return": 0.02, "std_return": 0.01, "n": 100}}}
    label, action, z = classifier.classify_at_date(
        symbol="RELIANCE",
        regime="NEUTRAL",
        actual_return=0.001,  # tiny positive vs expected +2%
        profile=profile,
        pcr=1.2,  # MILD_BULL -> agrees
        oi_anomaly=False,
    )
    assert label == "OPPORTUNITY"
    assert action == "ADD"
    assert z != 0


def test_classify_at_date_returns_uncertain_for_unknown_symbol():
    profile = {}
    label, action, z = classifier.classify_at_date(
        symbol="XYZ",
        regime="NEUTRAL",
        actual_return=0.0,
        profile=profile,
        pcr=None,
        oi_anomaly=False,
    )
    assert label == "UNCERTAIN"
    assert action == "HOLD"


def test_classify_at_date_handles_missing_pcr_as_neutral():
    profile = {"RELIANCE": {"NEUTRAL": {"expected_return": 0.02, "std_return": 0.01, "n": 100}}}
    label, action, z = classifier.classify_at_date(
        symbol="RELIANCE",
        regime="NEUTRAL",
        actual_return=0.001,
        profile=profile,
        pcr=None,
        oi_anomaly=False,
    )
    assert label in {"POSSIBLE_OPPORTUNITY", "OPPORTUNITY"}


def test_classify_universe_returns_one_label_per_symbol():
    profile = {
        "A": {"NEUTRAL": {"expected_return": 0.02, "std_return": 0.01, "n": 100}},
        "B": {"NEUTRAL": {"expected_return": -0.02, "std_return": 0.01, "n": 100}},
    }
    actuals = {"A": 0.001, "B": 0.001}
    labels = classifier.classify_universe(
        symbols=["A", "B"],
        regime="NEUTRAL",
        profile=profile,
        actual_returns=actuals,
        pcr_by_symbol={},
        oi_anomaly_by_symbol={},
    )
    assert set(labels.keys()) == {"A", "B"}
    for v in labels.values():
        assert "label" in v and "action" in v and "z_score" in v
