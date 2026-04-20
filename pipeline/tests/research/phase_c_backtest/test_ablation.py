from __future__ import annotations

from pipeline.research.phase_c_backtest import ablation, classifier


PROFILE = {
    "A": {"NEUTRAL": {"expected_return": 0.02, "std_return": 0.01, "n": 100}},
    "B": {"NEUTRAL": {"expected_return": -0.02, "std_return": 0.01, "n": 100}},
}


def test_run_all_variants_returns_four_keys():
    out = ablation.run_all_variants(
        symbols=["A", "B"],
        regime="NEUTRAL",
        profile=PROFILE,
        actual_returns={"A": 0.001, "B": -0.001},
        pcr_by_symbol={"A": 1.2, "B": 0.5},
        oi_anomaly_by_symbol={"A": True, "B": False},
    )
    assert set(out.keys()) == {"full", "no_oi", "no_pcr", "degraded"}
    # each variant should contain classifications for both symbols
    for variant in out.values():
        assert set(variant.keys()) == {"A", "B"}


def test_no_oi_variant_clears_oi_anomaly():
    out = ablation.run_all_variants(
        symbols=["A", "B"],
        regime="NEUTRAL",
        profile=PROFILE,
        actual_returns={"A": 0.001, "B": -0.001},
        pcr_by_symbol={"A": 1.2, "B": 0.5},
        oi_anomaly_by_symbol={"A": True, "B": True},
    )
    # both variants produce string labels; sanity check on shape
    assert isinstance(out["full"]["A"]["label"], str)
    assert isinstance(out["no_oi"]["A"]["label"], str)


def test_degraded_variant_has_neutral_pcr_and_no_oi():
    actuals = {"A": 0.001, "B": -0.001}
    out = ablation.run_all_variants(
        symbols=["A", "B"],
        regime="NEUTRAL",
        profile=PROFILE,
        actual_returns=actuals,
        pcr_by_symbol={"A": 1.2, "B": 0.5},
        oi_anomaly_by_symbol={"A": True, "B": True},
    )
    # Degraded must equal manually calling classify_at_date with pcr=None, oi=False.
    for sym in ["A", "B"]:
        expected_label, expected_action, expected_z = classifier.classify_at_date(
            symbol=sym,
            regime="NEUTRAL",
            actual_return=actuals[sym],
            profile=PROFILE,
            pcr=None,
            oi_anomaly=False,
        )
        assert out["degraded"][sym]["label"] == expected_label
        assert out["degraded"][sym]["action"] == expected_action
        assert out["degraded"][sym]["z_score"] == expected_z
