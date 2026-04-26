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


def test_zone_gate_warns_and_drops_all_when_signals_are_constant():
    """σ=0 → band collapses → all events drop, surfaced as a RuntimeWarning."""
    events = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01", "2026-03-02"]).date,
        "ret": [0.01, 0.02],
    })
    signals = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01", "2026-03-02"]).date,
        "signal_z": [0.5, 0.5],
    })
    with pytest.warns(RuntimeWarning, match="zero variance"):
        out = apply_zone_gate(events, signals, ZoneGateConfig(band_sigma=0.5))
    assert len(out) == 0


def test_zone_gate_handles_empty_inputs():
    """Empty events or empty signals must not crash."""
    empty_events = pd.DataFrame({"trade_date": [], "ret": []})
    signals = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-03-01"]).date,
        "signal_z": [1.5],
    })
    out = apply_zone_gate(empty_events, signals, ZoneGateConfig(band_sigma=0.5))
    assert len(out) == 0
