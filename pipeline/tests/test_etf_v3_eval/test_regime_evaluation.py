"""Unit tests for the Phase 2 regime evaluator pure helpers.

Covers the load-bearing logic that the Test-1 driver relies on:
  - 5-zone bucketing boundaries (signal_to_zone)
  - 2-day hysteresis (apply_hysteresis)
  - Per-zone NIFTY-outcome aggregation (per_zone_metrics)

Heavy I/O paths (panel + features build, run_test_1) are intentionally not
unit-tested here -- they run against the real smoke output via CLI.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.regime_evaluation import (
    ZONE_DIRECTION_HYPOTHESIS,
    ZONE_LABELS,
    apply_hysteresis,
    per_zone_metrics,
    signal_to_zone,
)


# ---------------------------------------------------------------------------
# signal_to_zone
# ---------------------------------------------------------------------------


class TestSignalToZone:
    def test_neutral_at_center(self):
        assert signal_to_zone(0.0, center=0.0, band=1.0) == "NEUTRAL"

    def test_risk_on_at_plus_one_band(self):
        # boundary inclusive
        assert signal_to_zone(1.0, center=0.0, band=1.0) == "RISK-ON"

    def test_euphoria_at_plus_two_bands(self):
        assert signal_to_zone(2.0, center=0.0, band=1.0) == "EUPHORIA"

    def test_caution_at_minus_one_band_minus_eps(self):
        assert signal_to_zone(-1.0001, center=0.0, band=1.0) == "CAUTION"

    def test_risk_off_at_minus_two_bands_minus_eps(self):
        assert signal_to_zone(-2.0001, center=0.0, band=1.0) == "RISK-OFF"

    def test_all_five_zones_reachable(self):
        seen = set()
        for sig in (-3.0, -1.5, 0.0, 1.5, 3.0):
            seen.add(signal_to_zone(sig, center=0.0, band=1.0))
        assert seen == set(ZONE_LABELS)

    def test_nonzero_center(self):
        # center=10, band=2 -> NEUTRAL [8, 12], RISK-ON [12, 14), EUPHORIA >=14,
        # CAUTION [6, 8), RISK-OFF <6
        assert signal_to_zone(13.5, center=10.0, band=2.0) == "RISK-ON"
        assert signal_to_zone(14.0, center=10.0, band=2.0) == "EUPHORIA"
        assert signal_to_zone(8.5, center=10.0, band=2.0) == "NEUTRAL"
        assert signal_to_zone(7.5, center=10.0, band=2.0) == "CAUTION"
        assert signal_to_zone(5.5, center=10.0, band=2.0) == "RISK-OFF"

    def test_nan_signal_raises(self):
        with pytest.raises(ValueError, match="signal must be finite"):
            signal_to_zone(float("nan"), center=0.0, band=1.0)

    def test_zero_band_raises(self):
        with pytest.raises(ValueError, match="band must be positive"):
            signal_to_zone(0.0, center=0.0, band=0.0)

    def test_negative_band_raises(self):
        with pytest.raises(ValueError, match="band must be positive"):
            signal_to_zone(0.0, center=0.0, band=-1.0)

    def test_nan_center_raises(self):
        with pytest.raises(ValueError):
            signal_to_zone(0.0, center=float("nan"), band=1.0)


# ---------------------------------------------------------------------------
# apply_hysteresis
# ---------------------------------------------------------------------------


class TestApplyHysteresis:
    def test_empty_input(self):
        assert apply_hysteresis([]) == []

    def test_single_day_passthrough(self):
        assert apply_hysteresis(["NEUTRAL"]) == ["NEUTRAL"]

    def test_no_flips_when_all_same(self):
        raw = ["NEUTRAL"] * 5
        assert apply_hysteresis(raw) == ["NEUTRAL"] * 5

    def test_single_day_flip_absorbed(self):
        # Day 3 jumps to RISK-ON for 1 day then back -> stays NEUTRAL throughout
        raw = ["NEUTRAL", "NEUTRAL", "RISK-ON", "NEUTRAL", "NEUTRAL"]
        assert apply_hysteresis(raw, k=2) == ["NEUTRAL"] * 5

    def test_two_day_flip_promotes(self):
        # Two consecutive RISK-ON days -> the SECOND day flips the official
        raw = ["NEUTRAL", "NEUTRAL", "RISK-ON", "RISK-ON", "RISK-ON"]
        # Day 0: NEUTRAL (init)
        # Day 1: NEUTRAL (raw matches official)
        # Day 2: candidate=RISK-ON count=1; official stays NEUTRAL
        # Day 3: candidate=RISK-ON count=2 -> flip to RISK-ON
        # Day 4: matches official RISK-ON
        assert apply_hysteresis(raw, k=2) == [
            "NEUTRAL", "NEUTRAL", "NEUTRAL", "RISK-ON", "RISK-ON"
        ]

    def test_candidate_resets_when_raw_returns_to_official(self):
        # Day 2 raw=RISK-ON (candidate count=1), Day 3 raw=NEUTRAL (matches
        # official -> candidate clears), Day 4 raw=RISK-ON (count=1 again,
        # not a flip)
        raw = ["NEUTRAL", "NEUTRAL", "RISK-ON", "NEUTRAL", "RISK-ON"]
        assert apply_hysteresis(raw, k=2) == ["NEUTRAL"] * 5

    def test_candidate_resets_when_raw_changes_to_third_zone(self):
        # Day 2 raw=RISK-ON count=1, Day 3 raw=CAUTION -> new candidate count=1
        # Day 4 raw=CAUTION count=2 -> flip to CAUTION
        raw = ["NEUTRAL", "NEUTRAL", "RISK-ON", "CAUTION", "CAUTION"]
        assert apply_hysteresis(raw, k=2) == [
            "NEUTRAL", "NEUTRAL", "NEUTRAL", "NEUTRAL", "CAUTION"
        ]

    def test_k_one_means_no_hysteresis(self):
        raw = ["NEUTRAL", "RISK-ON", "NEUTRAL", "CAUTION"]
        # Day 0: NEUTRAL init
        # Day 1: candidate RISK-ON count=1 >= 1 -> flip immediately
        # Day 2: candidate NEUTRAL count=1 >= 1 -> flip
        # Day 3: candidate CAUTION count=1 >= 1 -> flip
        assert apply_hysteresis(raw, k=1) == ["NEUTRAL", "RISK-ON", "NEUTRAL", "CAUTION"]

    def test_k_three_requires_three_days(self):
        raw = ["NEUTRAL"] * 2 + ["RISK-ON"] * 3 + ["NEUTRAL"] * 2
        # 2 days of NEUTRAL init, then 3 days RISK-ON: on the 3rd RISK-ON day
        # (index 4) the count reaches 3 and flips. Then NEUTRAL appears,
        # candidate count rises but only to 2 < 3 -> stays RISK-ON.
        out = apply_hysteresis(raw, k=3)
        assert out[:4] == ["NEUTRAL"] * 4
        assert out[4] == "RISK-ON"
        assert out[5:] == ["RISK-ON", "RISK-ON"]

    def test_k_zero_raises(self):
        with pytest.raises(ValueError, match="k must be"):
            apply_hysteresis(["NEUTRAL"], k=0)

    def test_first_day_initialises_official(self):
        # No prior official, so the first raw zone IS the first official
        assert apply_hysteresis(["EUPHORIA", "EUPHORIA"]) == ["EUPHORIA", "EUPHORIA"]


# ---------------------------------------------------------------------------
# per_zone_metrics
# ---------------------------------------------------------------------------


class TestPerZoneMetrics:
    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length mismatch"):
            per_zone_metrics(["NEUTRAL"] * 3, [0.1, 0.2])

    def test_empty_input_returns_zero_rows(self):
        df = per_zone_metrics([], [])
        assert list(df.index) == list(ZONE_LABELS)
        assert (df["n"] == 0).all()

    def test_missing_zone_has_nan_metrics(self):
        # Only NEUTRAL appears -> other zones get n=0 and NaN metrics
        df = per_zone_metrics(["NEUTRAL"] * 3, [0.1, -0.2, 0.3])
        assert df.loc["NEUTRAL", "n"] == 3
        assert df.loc["EUPHORIA", "n"] == 0
        assert math.isnan(df.loc["EUPHORIA", "mean_ret_pp"])

    def test_pct_up_and_down(self):
        zones = ["RISK-ON"] * 4
        rets = [+0.5, +0.3, -0.1, +0.0]
        df = per_zone_metrics(zones, rets)
        # 2 strictly positive, 1 strictly negative, 1 flat
        assert df.loc["RISK-ON", "n"] == 4
        assert df.loc["RISK-ON", "pct_up"] == 50.0
        assert df.loc["RISK-ON", "pct_down"] == 25.0

    def test_hypothesis_accuracy_uses_correct_side(self):
        # RISK-ON hypothesis is +1 -> hyp_acc = pct_up
        # CAUTION hypothesis is -1 -> hyp_acc = pct_down
        df = per_zone_metrics(
            ["RISK-ON"] * 2 + ["CAUTION"] * 2,
            [+1.0, -1.0, -1.0, +1.0],
        )
        assert df.loc["RISK-ON", "pct_up"] == 50.0
        assert df.loc["RISK-ON", "hypothesis_acc_pct"] == 50.0
        assert df.loc["CAUTION", "pct_down"] == 50.0
        assert df.loc["CAUTION", "hypothesis_acc_pct"] == 50.0

    def test_neutral_hypothesis_is_nan(self):
        df = per_zone_metrics(["NEUTRAL"] * 3, [+1.0, -1.0, +0.5])
        assert df.loc["NEUTRAL", "hypothesis_dir"] == 0
        assert math.isnan(df.loc["NEUTRAL", "hypothesis_acc_pct"])

    def test_nan_returns_dropped_before_aggregation(self):
        zones = ["RISK-ON", "RISK-ON", "RISK-ON"]
        rets = [+0.5, np.nan, +0.3]
        df = per_zone_metrics(zones, rets)
        # NaN return dropped -> n=2 not 3
        assert df.loc["RISK-ON", "n"] == 2

    def test_pct_of_days_uses_total_non_nan(self):
        zones = ["RISK-ON"] * 1 + ["NEUTRAL"] * 3
        rets = [+1.0, +0.1, -0.1, +0.0]
        df = per_zone_metrics(zones, rets)
        # 4 valid rows total -> RISK-ON 25%, NEUTRAL 75%
        assert df.loc["RISK-ON", "pct_of_days"] == 25.0
        assert df.loc["NEUTRAL", "pct_of_days"] == 75.0

    def test_zone_direction_hypothesis_covers_all_zones(self):
        # Defensive: ZONE_DIRECTION_HYPOTHESIS must define a value for every zone
        for z in ZONE_LABELS:
            assert z in ZONE_DIRECTION_HYPOTHESIS
            assert ZONE_DIRECTION_HYPOTHESIS[z] in (-1, 0, 1)
