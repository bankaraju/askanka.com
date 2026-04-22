import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal_tracker


def _mk_signal(stop_pct, source="CORRELATION_BREAK", atr_source="atr_14"):
    return {
        "signal_id": "BRK-TEST",
        "source": source,
        "spread_name": "Phase C: BHEL REGIME_LAG",
        "long_legs": [{"ticker": "BHEL", "yf": "BHEL.NS", "price": 318.5, "weight": 1.0}],
        "short_legs": [],
        "_atr_stop": {
            "stop_pct": stop_pct, "stop_price": 303.5,
            "atr_14": 7.5, "stop_source": atr_source,
        },
        "open_timestamp": "2026-04-22T10:00:00+05:30",
        "peak_spread_pnl_pct": 0.0,
    }


def test_monitor_uses_atr_stop_when_correlation_break():
    """daily_stop must come from _atr_stop.stop_pct, not from spread_statistics default."""
    sig = _mk_signal(stop_pct=-2.3)
    # BHEL down 3% today → -3.0 <= -2.3 → should stop out
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": -3.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=-3.0), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 309.0})
    assert status == "STOPPED_OUT"
    assert sig["_data_levels"]["daily_stop"] == -2.3


def test_monitor_falls_back_when_atr_stop_source_is_fallback():
    """If _atr_stop.stop_source == 'fallback', behave exactly as before (use spread stats default)."""
    sig = _mk_signal(stop_pct=-1.0, atr_source="fallback")
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": -0.5}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=-0.5), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 318.5})
    # -0.5 > -1.0 spread default → OPEN
    assert status == "OPEN"
    assert sig["_data_levels"]["daily_stop"] == -1.0


def test_monitor_ignores_atr_for_non_correlation_sources():
    """For SPREAD trades, _atr_stop must be ignored even if present."""
    sig = _mk_signal(stop_pct=-2.3, source="SPREAD")
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": -0.9}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=-0.9), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        status, _ = signal_tracker.check_signal_status(sig, current_prices={"BHEL": 318.5})
    # Falls back to spread default: -(2.0 * 0.5) = -1.0. -0.9 > -1.0 → OPEN.
    assert status == "OPEN"
    assert sig["_data_levels"]["daily_stop"] == -1.0


def test_data_levels_carries_stop_source_for_atr():
    """check_signal_status must record stop_source in _data_levels so the UI
    can distinguish real ATR stops from fallback defaults."""
    sig = _mk_signal(stop_pct=-2.3, atr_source="atr_14")
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 0.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.0), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        signal_tracker.check_signal_status(sig, current_prices={"BHEL": 318.5})
    assert sig["_data_levels"]["stop_source"] == "atr_14"


def test_data_levels_carries_stop_source_fallback_for_spread():
    """Non-ATR paths label stop_source as 'spread_stats' (not fallback) —
    fallback indicator is reserved for ATR-attempted-but-failed only."""
    sig = _mk_signal(stop_pct=-1.0, source="SPREAD", atr_source="atr_14")
    with patch.object(signal_tracker, "compute_signal_pnl",
                      return_value={"spread_pnl_pct": 0.0}), \
         patch.object(signal_tracker, "_compute_todays_spread_move", return_value=0.0), \
         patch.object(signal_tracker, "get_levels_for_spread",
                      return_value={"daily_std": 2.0, "avg_favorable_move": 2.0,
                                    "entry_level": 0.0, "stop_level": -1.5,
                                    "cum_percentile": 50.0, "cum_peak": 5.0, "cum_trough": -2.0}):
        signal_tracker.check_signal_status(sig, current_prices={"BHEL": 318.5})
    assert sig["_data_levels"]["stop_source"] == "spread_stats"
