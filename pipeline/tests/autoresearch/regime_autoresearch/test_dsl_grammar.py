"""DSL grammar validation + family-size enumeration."""
from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.dsl import (
    FEATURES, THRESHOLD_OPS, HOLD_HORIZONS, CONSTRUCTION_TYPES,
    Proposal, validate, enumerate_family_size,
)


def test_feature_library_size():
    assert len(FEATURES) == 20


def test_grammar_enumeration_non_pair():
    # 3 non-pair constructions × 20 × 4 ops × 8 thresholds × 3 holds × 5 regimes
    assert enumerate_family_size(include_pairs=False) == 28_800


def test_validate_accepts_good_proposal():
    p = Proposal(
        construction_type="single_long",
        feature="ret_20d",
        threshold_op=">",
        threshold_value=0.05,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    assert validate(p) is True


def test_validate_rejects_unknown_feature():
    p = Proposal("single_long", "not_a_feature", ">", 0.05, 5, "NEUTRAL", None)
    with pytest.raises(ValueError, match="unknown feature"):
        validate(p)


def test_validate_rejects_pair_without_pair_id():
    p = Proposal("pair", "ret_20d", ">", 2.0, 5, "NEUTRAL", None)
    with pytest.raises(ValueError, match="pair construction requires pair_id"):
        validate(p)


def test_validate_rejects_non_pair_with_pair_id():
    p = Proposal("single_long", "ret_20d", ">", 0.05, 5, "NEUTRAL", "RELIANCE_INFY")
    with pytest.raises(ValueError, match="pair_id only valid when construction_type == 'pair'"):
        validate(p)
