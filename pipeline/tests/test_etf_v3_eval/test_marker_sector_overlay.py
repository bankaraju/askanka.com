import pandas as pd

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
