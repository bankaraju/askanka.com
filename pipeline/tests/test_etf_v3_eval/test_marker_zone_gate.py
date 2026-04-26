import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.markers.zone_gate import (
    apply_zone_gate,
    ZoneGateConfig,
)


def test_zone_gate_drops_neutral_band():
    """Events on dates whose v3 z-signal is within ±band σ of mean are dropped."""
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03"]).date,
        "ret": [0.01, 0.02, -0.03],
    })
    signals = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01","2026-03-02","2026-03-03"]).date,
        "signal_z": [0.1, 1.5, -1.5],   # 03-01 inside ±0.5σ → drop
    })
    out = apply_zone_gate(events, signals, ZoneGateConfig(band_sigma=0.5))
    assert set(out["trade_date"]) == {pd.Timestamp("2026-03-02").date(), pd.Timestamp("2026-03-03").date()}
