# pipeline/tests/test_etf_v3_eval/test_direction_audit.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.direction_audit import (
    direction_audit,
    DirectionVerdict,
)


def test_direction_verdict_aligned_when_strategy_beats_opposite():
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]*5).date,
        "realized_pct":  [ 0.01, 0.02, 0.015, 0.012, 0.018],
        "side": ["LONG"]*5,   # All LONG → strategy wins
    })
    rep = direction_audit(events)
    assert rep.verdict == DirectionVerdict.ALIGNED


def test_direction_verdict_suspect_when_opposite_beats_strategy():
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]*5).date,
        "realized_pct":  [-0.01,-0.02,-0.015,-0.012,-0.018],
        "side": ["LONG"]*5,   # LONGs lose; SHORT would win
    })
    rep = direction_audit(events)
    assert rep.verdict == DirectionVerdict.SUSPECT


def test_unrecognized_side_raises():
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]*2).date,
        "realized_pct": [0.01, 0.02],
        "side": ["LONG", "BUY"],   # BUY is not LONG/SHORT
    })
    with pytest.raises(ValueError, match="side"):
        direction_audit(events)


def test_single_event_raises():
    """n=1 → std(ddof=1) is NaN; must fail loud, not produce a degenerate
    Sharpe via the 1e-12 floor."""
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]).date,
        "realized_pct": [0.01],
        "side": ["LONG"],
    })
    with pytest.raises(ValueError, match="at least 2 events"):
        direction_audit(events)


def test_missing_realized_pct_raises():
    events = pd.DataFrame({"side": ["LONG", "SHORT"]})
    with pytest.raises(ValueError, match="realized_pct"):
        direction_audit(events)


def test_missing_side_raises():
    events = pd.DataFrame({"realized_pct": [0.01, 0.02]})
    with pytest.raises(ValueError, match="side"):
        direction_audit(events)
