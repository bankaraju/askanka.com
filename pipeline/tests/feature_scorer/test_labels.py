import pandas as pd
import pytest


@pytest.fixture
def winner_prices():
    """Monotonically rising series — simulated position hits +1.5% quickly."""
    dates = pd.date_range("2026-03-01", periods=10, freq="B")
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    return pd.DataFrame({"date": dates, "close": closes})


@pytest.fixture
def loser_prices():
    """Falling series — position hits daily stop on day 1."""
    dates = pd.date_range("2026-03-01", periods=10, freq="B")
    closes = [100, 97, 95, 94, 93, 92, 91, 90, 89, 88]
    return pd.DataFrame({"date": dates, "close": closes})


@pytest.fixture
def round_trip_prices():
    """Rises sharply to +8% peak (trail ratchets to ~+5%), retraces, trail fires at +3%."""
    dates = pd.date_range("2026-03-01", periods=10, freq="B")
    # entry is 2026-03-02 (index 1, close=100). closes after: [104,108,106,103,100,...]
    closes = [100, 100, 104, 108, 106, 103, 100, 98, 98, 98]
    return pd.DataFrame({"date": dates, "close": closes})


def test_winner_labeled_as_win(winner_prices):
    from pipeline.feature_scorer.labels import simulated_pnl_label
    label = simulated_pnl_label(winner_prices, entry_date="2026-03-02",
                                 horizon_days=5, win_threshold=0.015,
                                 daily_stop=-0.02, avg_favorable=0.02)
    assert label["y"] == 1
    assert label["realized_pct"] >= 0.015


def test_loser_labeled_as_loss(loser_prices):
    from pipeline.feature_scorer.labels import simulated_pnl_label
    label = simulated_pnl_label(loser_prices, entry_date="2026-03-02",
                                 horizon_days=5, win_threshold=0.015,
                                 daily_stop=-0.02, avg_favorable=0.02)
    assert label["y"] == 0


def test_round_trip_uses_trail_and_labels_win(round_trip_prices):
    """After peak at +3%, trail should fire and lock in ~+1.5%+ realized."""
    from pipeline.feature_scorer.labels import simulated_pnl_label
    label = simulated_pnl_label(round_trip_prices, entry_date="2026-03-02",
                                 horizon_days=5, win_threshold=0.015,
                                 daily_stop=-0.02, avg_favorable=0.02)
    assert label["y"] == 1, f"expected trail to lock in >=1.5%; realized={label['realized_pct']}"


def test_missing_entry_date_returns_none():
    from pipeline.feature_scorer.labels import simulated_pnl_label
    df = pd.DataFrame({"date": [], "close": []})
    label = simulated_pnl_label(df, entry_date="2026-03-02",
                                 horizon_days=5, win_threshold=0.015,
                                 daily_stop=-0.02, avg_favorable=0.02)
    assert label is None


def test_label_surface_for_horizon(winner_prices):
    """horizon_days=3 — only looks 3 days ahead."""
    from pipeline.feature_scorer.labels import simulated_pnl_label
    label = simulated_pnl_label(winner_prices, entry_date="2026-03-02",
                                 horizon_days=3, win_threshold=0.015,
                                 daily_stop=-0.02, avg_favorable=0.02)
    # Entry at 100 (Mar 2), 3 days later (Mar 5) close = 103 → +3% → win
    assert label["y"] == 1
    assert 0.025 < label["realized_pct"] < 0.035
