"""Tests for replay_trail_stop.simulate_signal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "autoresearch"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay_trail_stop import simulate_signal


def _mk_signal():
    return {
        "signal_id": "SIG-TEST-001",
        "spread_name": "Coal vs OMCs",
        "open_timestamp": "2026-04-01T04:29:29",
        "close_timestamp": "2026-04-08T04:14:51",
        "long_legs":  [{"ticker": "COALINDIA", "price": 464.0}],
        "short_legs": [{"ticker": "BPCL",      "price": 292.0},
                       {"ticker": "HPCL",      "price": 350.0}],
        "status": "STOPPED_OUT",
        "final_pnl": {"spread_pnl_pct": -4.04},
        "peak_spread_pnl_pct": 7.07,
    }


def test_simulate_returns_earlier_exit_when_trail_breached():
    # Daily closes: peak on day 3, then give-back crossing trail on day 5
    daily_prices = {
        "COALINDIA": [
            ("2026-04-01", 464.0),
            ("2026-04-02", 475.0),
            ("2026-04-03", 490.0),   # peak
            ("2026-04-04", 488.0),
            ("2026-04-07", 478.0),   # breach
            ("2026-04-08", 450.9),
        ],
        "BPCL": [
            ("2026-04-01", 292.0),
            ("2026-04-02", 290.0),
            ("2026-04-03", 285.0),
            ("2026-04-04", 286.0),
            ("2026-04-07", 292.0),
            ("2026-04-08", 295.05),
        ],
        "HPCL": [
            ("2026-04-01", 350.0),
            ("2026-04-02", 348.0),
            ("2026-04-03", 343.0),
            ("2026-04-04", 344.0),
            ("2026-04-07", 352.0),
            ("2026-04-08", 354.85),
        ],
    }
    levels = {"avg_favorable_move": 2.38, "daily_std": 3.57}
    result = simulate_signal(_mk_signal(), daily_prices, levels)

    assert result["signal_id"] == "SIG-TEST-001"
    assert result["simulated_exit"]["reason"] == "TRAIL_STOP"
    assert result["simulated_exit"]["date"] < "2026-04-08"
    assert result["simulated_exit"]["pnl_pct"] > result["actual_exit"]["pnl_pct"]
    assert result["delta_pct"] > 0


def test_simulate_keeps_actual_when_no_trail_breach():
    # Monotonically improving trade — trail never fires, simulated = actual
    daily_prices = {
        "COALINDIA": [("2026-04-01", 464.0), ("2026-04-02", 470.0), ("2026-04-03", 480.0)],
        "BPCL":      [("2026-04-01", 292.0), ("2026-04-02", 290.0), ("2026-04-03", 285.0)],
        "HPCL":      [("2026-04-01", 350.0), ("2026-04-02", 348.0), ("2026-04-03", 345.0)],
    }
    sig = _mk_signal()
    sig["close_timestamp"] = "2026-04-03T16:00:00"
    sig["final_pnl"] = {"spread_pnl_pct": 3.5}
    sig["peak_spread_pnl_pct"] = 3.5
    levels = {"avg_favorable_move": 2.38, "daily_std": 3.57}
    result = simulate_signal(sig, daily_prices, levels)

    assert result["simulated_exit"]["reason"] in ("ACTUAL_CLOSE", None)
    assert result["delta_pct"] == 0
