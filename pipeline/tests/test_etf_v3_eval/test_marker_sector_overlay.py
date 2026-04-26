import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.sector_overlay import (
    apply_sector_overlay,
    NEUTRAL_DAY_WINNER_SECTORS,
)


def test_sector_overlay_keeps_only_winners():
    events = pd.DataFrame({
        "ticker": ["SBIN","TCS","NTPC","ASIANPAINT"],
        "ret":    [0.01, 0.02, -0.03, 0.04],
        "sector": ["PSU BANK","IT","ENERGY","FMCG"],
    })
    out = apply_sector_overlay(events, sectors=NEUTRAL_DAY_WINNER_SECTORS)
    assert set(out["ticker"]) == {"SBIN","NTPC"}


def test_sector_overlay_returns_empty_when_no_matches():
    """No matching sector → empty frame, not error."""
    events = pd.DataFrame({
        "ticker": ["TCS"],
        "ret": [0.02],
        "sector": ["IT"],
    })
    out = apply_sector_overlay(events, sectors=NEUTRAL_DAY_WINNER_SECTORS)
    assert len(out) == 0


def test_sector_overlay_raises_on_missing_column():
    events = pd.DataFrame({"ticker": ["X"], "ret": [0.0]})
    with pytest.raises(ValueError, match="sector"):
        apply_sector_overlay(events, sectors=NEUTRAL_DAY_WINNER_SECTORS)
