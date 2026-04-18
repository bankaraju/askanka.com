"""
Tests for pipeline/shadow_pnl.py

Run: pytest pipeline/tests/test_shadow_pnl.py -v
"""
import pytest
from datetime import datetime, timedelta, timezone

from pipeline.shadow_pnl import (
    create_shadow_trade,
    update_shadow_trade,
    generate_daily_strip,
    STOP_LOSS_PCT,
    TARGET_PCT,
)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SIGNAL = {
    "signal_id": "SIG-2026-04-18-001",
    "spread_name": "Defence vs IT",
    "direction": "LONG",
    "conviction": 72.5,
}


# ---------------------------------------------------------------------------
# create_shadow_trade tests
# ---------------------------------------------------------------------------

class TestCreateShadowTrade:
    def test_create_shadow_trade_structure(self):
        """All required fields must be present in the returned dict."""
        trade = create_shadow_trade(
            signal=SAMPLE_SIGNAL,
            entry_price=1000.0,
            regime="RISK_ON",
            sizing_factor=1.0,
        )

        required_keys = [
            "signal_id", "spread_name", "direction", "regime_at_entry",
            "conviction", "sizing_multiplier", "entry_price", "entry_time",
            "stop_loss", "target", "expiry_date", "status", "pnl_pct", "peak_pnl",
        ]
        for key in required_keys:
            assert key in trade, f"Missing key: {key}"

        assert trade["status"] == "OPEN"
        assert trade["pnl_pct"] == 0.0
        assert trade["peak_pnl"] == 0.0
        assert trade["entry_price"] == 1000.0
        assert trade["sizing_multiplier"] == 1.0
        assert trade["direction"] == "LONG"
        assert trade["regime_at_entry"] == "RISK_ON"
        assert trade["signal_id"] == "SIG-2026-04-18-001"

    def test_reduced_sizing_stored(self):
        """sizing_factor=0.5 is stored as sizing_multiplier."""
        trade = create_shadow_trade(
            signal=SAMPLE_SIGNAL,
            entry_price=500.0,
            regime="NEUTRAL",
            sizing_factor=0.5,
        )
        assert trade["sizing_multiplier"] == 0.5

    def test_direction_defaults_to_long(self):
        """Missing direction defaults to LONG."""
        signal_no_dir = {"signal_id": "SIG-NODIR", "spread_name": "X vs Y"}
        trade = create_shadow_trade(signal_no_dir, entry_price=100.0, regime="NEUTRAL")
        assert trade["direction"] == "LONG"

    def test_stop_and_target_stored(self):
        """stop_loss and target are stored from module constants."""
        trade = create_shadow_trade(SAMPLE_SIGNAL, entry_price=100.0, regime="NEUTRAL")
        assert trade["stop_loss"] == STOP_LOSS_PCT
        assert trade["target"] == TARGET_PCT


# ---------------------------------------------------------------------------
# update_shadow_trade tests
# ---------------------------------------------------------------------------

class TestUpdateShadowTrade:
    def _open_trade(self, entry_price=1000.0, direction="LONG") -> dict:
        return {
            "signal_id": "SIG-UPDATE-001",
            "spread_name": "Test Spread",
            "direction": direction,
            "entry_price": entry_price,
            "entry_time": datetime.now(IST).isoformat(),
            "stop_loss": STOP_LOSS_PCT,
            "target": TARGET_PCT,
            "expiry_date": (datetime.now(IST) + timedelta(days=5)).isoformat(),
            "status": "OPEN",
            "pnl_pct": 0.0,
            "peak_pnl": 0.0,
        }

    def test_update_trade_still_open(self):
        """Small price move keeps trade OPEN with updated pnl_pct."""
        trade = self._open_trade(entry_price=1000.0)
        updated = update_shadow_trade(trade, current_price=1010.0)  # +1%

        assert updated["status"] == "OPEN"
        assert abs(updated["pnl_pct"] - 1.0) < 0.001
        assert updated["peak_pnl"] >= 1.0
        assert "close_reason" not in updated

    def test_update_trade_target_hit(self):
        """Price rise beyond TARGET_PCT closes trade as TARGET."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")
        # TARGET_PCT = 4.5 → need price > 1045
        updated = update_shadow_trade(trade, current_price=1050.0)  # +5%

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "TARGET"
        assert "close_time" in updated
        assert updated["pnl_pct"] > TARGET_PCT

    def test_update_trade_stop_hit(self):
        """Price drop beyond STOP_LOSS_PCT closes trade as STOP_LOSS."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")
        # STOP_LOSS_PCT = 3.0 → need price < 970
        updated = update_shadow_trade(trade, current_price=960.0)  # -4%

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "STOP_LOSS"
        assert "close_time" in updated
        assert updated["pnl_pct"] < -STOP_LOSS_PCT

    def test_update_trade_short_direction(self):
        """Short trade profits when price falls."""
        trade = self._open_trade(entry_price=1000.0, direction="SHORT")
        # Price falls 5% → short makes +5%
        updated = update_shadow_trade(trade, current_price=950.0)

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "TARGET"
        assert updated["pnl_pct"] > 0

    def test_update_trade_already_closed_unchanged(self):
        """Calling update on a CLOSED trade returns it unchanged."""
        trade = self._open_trade()
        trade["status"] = "CLOSED"
        trade["close_reason"] = "TARGET"
        trade["pnl_pct"] = 4.5

        result = update_shadow_trade(trade, current_price=2000.0)

        assert result["status"] == "CLOSED"
        assert result["pnl_pct"] == 4.5  # not recalculated

    def test_trailing_stop_fires_after_peak(self):
        """Trailing stop closes trade when P&L drops 1.5% from a 2%+ peak."""
        trade = self._open_trade(entry_price=1000.0, direction="LONG")

        # Simulate: price goes to 1025 (+2.5%), arming trail
        trade = update_shadow_trade(trade, current_price=1025.0)
        assert trade["status"] == "OPEN"
        assert trade["peak_pnl"] >= 2.0  # trail should be armed

        # Now price drops to 1009 (+0.9%) — drop from peak is 1.6% → trail fires
        trade = update_shadow_trade(trade, current_price=1009.0)
        assert trade["status"] == "CLOSED"
        assert trade["close_reason"] == "TRAIL_STOP"

    def test_expiry_closes_trade(self):
        """Trade past expiry_date is closed as EXPIRY."""
        trade = self._open_trade()
        # Set expiry in the past
        past = datetime.now(IST) - timedelta(hours=1)
        trade["expiry_date"] = past.isoformat()

        updated = update_shadow_trade(trade, current_price=1000.0)

        assert updated["status"] == "CLOSED"
        assert updated["close_reason"] == "EXPIRY"


# ---------------------------------------------------------------------------
# generate_daily_strip tests
# ---------------------------------------------------------------------------

def _make_closed(pnl_pct: float, date_str: str) -> dict:
    """Helper: minimal closed signal for strip generation."""
    return {
        "signal_id": f"SIG-{date_str}-{pnl_pct}",
        "pnl_pct": pnl_pct,
        "close_time": f"{date_str}T15:30:00+05:30",
        "status": "CLOSED",
    }


class TestGenerateDailyStrip:
    def test_generate_daily_strip_empty(self):
        """Empty list → zero stats, empty strip."""
        result = generate_daily_strip([])

        assert result["trading_days"] == 0
        assert result["daily_strip"] == []
        s = result["summary"]
        assert s["total_trades"] == 0
        assert s["wins"] == 0
        assert s["losses"] == 0
        assert s["win_rate"] == 0.0
        assert s["cumulative_return"] == 0.0
        assert s["max_drawdown"] == 0.0
        assert s["sharpe"] == 0.0

    def test_generate_daily_strip_structure(self):
        """Strip output has correct structure and types."""
        signals = [
            _make_closed(2.0, "2026-04-14"),
            _make_closed(1.5, "2026-04-14"),
            _make_closed(-1.0, "2026-04-15"),
        ]
        result = generate_daily_strip(signals)

        assert isinstance(result["trading_days"], int)
        assert result["trading_days"] == 2

        strip = result["daily_strip"]
        assert len(strip) == 2

        for entry in strip:
            assert "date" in entry
            assert "pnl" in entry
            assert "result" in entry
            assert "trades" in entry
            assert entry["result"] in ("WIN", "LOSS")

        s = result["summary"]
        assert "total_trades" in s
        assert "wins" in s
        assert "losses" in s
        assert "win_rate" in s
        assert "avg_return" in s
        assert "cumulative_return" in s
        assert "max_drawdown" in s
        assert "sharpe" in s

    def test_strip_sorted_by_date_ascending(self):
        """Daily strip entries are returned in chronological order."""
        signals = [
            _make_closed(1.0, "2026-04-16"),
            _make_closed(2.0, "2026-04-14"),
            _make_closed(1.5, "2026-04-15"),
        ]
        result = generate_daily_strip(signals)
        dates = [e["date"] for e in result["daily_strip"]]
        assert dates == sorted(dates)

    def test_win_loss_classification(self):
        """Days with positive total P&L are WIN, negative are LOSS."""
        signals = [
            _make_closed(3.0, "2026-04-14"),   # WIN day
            _make_closed(-2.0, "2026-04-15"),  # LOSS day
        ]
        result = generate_daily_strip(signals)
        strip = {e["date"]: e["result"] for e in result["daily_strip"]}
        assert strip["2026-04-14"] == "WIN"
        assert strip["2026-04-15"] == "LOSS"

    def test_summary_win_rate_calculation(self):
        """win_rate = wins / total_trades across all trades (not days)."""
        signals = [
            _make_closed(2.0, "2026-04-14"),   # win
            _make_closed(-1.0, "2026-04-14"),  # loss (same day)
            _make_closed(1.0, "2026-04-15"),   # win
        ]
        result = generate_daily_strip(signals)
        s = result["summary"]
        assert s["total_trades"] == 3
        assert s["wins"] == 2
        assert s["losses"] == 1
        assert abs(s["win_rate"] - 2/3) < 0.001

    def test_nested_pnl_format_in_strip(self):
        """Signals with nested final_pnl.spread_pnl_pct are handled correctly."""
        signal = {
            "signal_id": "SIG-NESTED",
            "final_pnl": {"spread_pnl_pct": 3.5},
            "close_timestamp": "2026-04-14T15:30:00+05:30",
            "status": "STOPPED_OUT",
        }
        result = generate_daily_strip([signal])
        assert result["trading_days"] == 1
        assert result["summary"]["total_trades"] == 1
        assert result["summary"]["wins"] == 1
