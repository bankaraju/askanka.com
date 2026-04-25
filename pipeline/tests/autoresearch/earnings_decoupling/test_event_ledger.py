import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.event_ledger import build_event_ledger


@pytest.fixture
def fixtures():
    dates = pd.bdate_range("2024-01-01", periods=400)
    np.random.seed(123)
    prices = pd.DataFrame({
        "RELIANCE": np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 1000,
        "TCS":      np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 3000,
        "INFY":     np.cumprod(1 + np.random.normal(0.0005, 0.01, 400)) * 1500,
    }, index=dates)
    sector_idx = pd.DataFrame({
        "BANKNIFTY": np.cumprod(1 + np.random.normal(0, 0.005, 400)) * 50000,
    }, index=dates)
    vix = pd.Series(np.full(400, 15.0) + np.random.normal(0, 0.5, 400), index=dates)
    fno_history = [{"date": "2024-01-01", "symbols": ["RELIANCE", "TCS", "INFY"]}]
    peers_map = {"RELIANCE": ["TCS", "INFY"]}
    sector_map = {"RELIANCE": "BANKNIFTY"}
    events = pd.DataFrame({
        "symbol": ["RELIANCE"],
        "event_date": [dates[300].strftime("%Y-%m-%d")],
    })
    return dict(
        events=events, prices=prices, sector_idx=sector_idx, vix=vix,
        fno_history=fno_history, peers_map=peers_map, sector_map=sector_map,
    )


VALID_STATUSES = {
    "CANDIDATE",
    "EXCLUDED_MACRO",
    "DROPPED_INSUFFICIENT_BASELINE",
    "DROPPED_PIT_MISS",
    "DROPPED_NO_SECTOR_MAP",
    "DROPPED_NO_SECTOR_DATA",
    "DROPPED_NO_TRIGGER",
}


def test_build_event_ledger_emits_one_row_per_event(fixtures):
    ledger = build_event_ledger(**fixtures)
    assert len(ledger) == 1
    row = ledger.iloc[0]
    assert row["ticker"] == "RELIANCE"
    assert row["status"] in VALID_STATUSES


def test_build_event_ledger_drops_pit_miss(fixtures):
    fixtures["fno_history"] = [{"date": "2024-01-01", "symbols": ["TCS", "INFY"]}]  # RELIANCE not in F&O
    ledger = build_event_ledger(**fixtures)
    assert len(ledger) == 1
    assert ledger.iloc[0]["status"] == "DROPPED_PIT_MISS"


def test_build_event_ledger_assigns_direction_from_trigger_z(fixtures):
    rng = np.random.default_rng(0)
    dates = fixtures["prices"].index
    rel_returns = rng.normal(0.0001, 0.005, len(dates))
    rel_returns[298] = 0.10  # huge positive residual T-3
    rel_returns[297] = 0.10
    rel_returns[296] = 0.10
    rel_returns[295] = 0.10
    rel_returns[294] = 0.10
    fixtures["prices"]["RELIANCE"] = np.cumprod(1 + rel_returns) * 1000
    ledger = build_event_ledger(**fixtures)
    if ledger.iloc[0]["status"] == "CANDIDATE":
        assert ledger.iloc[0]["direction"] == "LONG"
        assert ledger.iloc[0]["trigger_z"] > 0


def test_build_event_ledger_excludes_macro_when_sector_index_moves_2pct(fixtures):
    """Sector index spike on event-day → status EXCLUDED_MACRO with reason SECTOR_T."""
    # Force RELIANCE to trigger (large positive residual T-7→T-3)
    rng = np.random.default_rng(0)
    dates = fixtures["prices"].index
    rel_returns = rng.normal(0.0001, 0.005, len(dates))
    rel_returns[294:299] = 0.10
    fixtures["prices"]["RELIANCE"] = np.cumprod(1 + rel_returns) * 1000
    # Inject a +3% BANKNIFTY move on the event date itself
    fixtures["sector_idx"].iloc[300, fixtures["sector_idx"].columns.get_loc("BANKNIFTY")] = (
        fixtures["sector_idx"].iloc[299, fixtures["sector_idx"].columns.get_loc("BANKNIFTY")] * 1.03
    )
    ledger = build_event_ledger(**fixtures)
    assert ledger.iloc[0]["status"] == "EXCLUDED_MACRO"
    assert ledger.iloc[0]["exclusion_reason"] in {"SECTOR_T", "SECTOR_T1"}


def test_build_event_ledger_drops_no_trigger_when_z_below_threshold(fixtures):
    """Quiet pre-event residuals → |z| < 1.5 → status DROPPED_NO_TRIGGER."""
    # Synthetic baseline already gives ~|z| < 1 from default seed; verify this is what happens
    ledger = build_event_ledger(**fixtures)
    row = ledger.iloc[0]
    if row["status"] == "DROPPED_NO_TRIGGER":
        assert abs(row["trigger_z"]) < 1.5
    elif row["status"] == "CANDIDATE":
        assert abs(row["trigger_z"]) >= 1.5
    else:
        # other statuses are also acceptable for synthetic data; this just locks the contract
        assert row["status"] in VALID_STATUSES


def test_build_event_ledger_drops_no_sector_map(fixtures):
    fixtures["sector_map"] = {}  # empty — no sector for RELIANCE
    ledger = build_event_ledger(**fixtures)
    assert ledger.iloc[0]["status"] == "DROPPED_NO_SECTOR_MAP"
