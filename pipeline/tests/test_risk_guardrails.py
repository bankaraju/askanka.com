"""
Tests for pipeline/risk_guardrails.py

Run: pytest pipeline/tests/test_risk_guardrails.py -v
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.risk_guardrails import check_risk_gates

IST = timezone(timedelta(hours=5, minutes=30))


def _make_signal(pnl_pct: float, days_ago: float = 5) -> dict:
    """Helper: closed signal with root-level pnl_pct."""
    close_dt = datetime.now(IST) - timedelta(days=days_ago)
    return {
        "signal_id": f"SIG-TEST-{pnl_pct}",
        "pnl_pct": pnl_pct,
        "close_timestamp": close_dt.isoformat(),
        "status": "CLOSED",
    }


def _make_nested_signal(pnl_pct: float, days_ago: float = 5) -> dict:
    """Helper: closed signal with nested final_pnl layout (signal_tracker.py format)."""
    close_dt = datetime.now(IST) - timedelta(days=days_ago)
    return {
        "signal_id": f"SIG-NESTED-{pnl_pct}",
        "final_pnl": {"spread_pnl_pct": pnl_pct},
        "close_timestamp": close_dt.isoformat(),
        "status": "STOPPED_OUT",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormalGate:
    def test_normal_allows_full_sizing(self, tmp_path):
        """Cumulative P&L of +5% over 20 days → NORMAL gate, 1.0 sizing."""
        signals = [_make_signal(2.0), _make_signal(3.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 1.0
        assert result["level"] == "NORMAL"
        assert result["reason"] is None
        assert abs(result["cumulative_pnl"] - 5.0) < 0.001
        assert result["trades_in_window"] == 2

    def test_positive_pnl_stays_normal(self, tmp_path):
        """Large positive P&L doesn't trigger any breaker."""
        signals = [_make_signal(10.0), _make_signal(8.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "NORMAL"
        assert result["sizing_factor"] == 1.0


class TestL1Gate:
    def test_l1_reduces_sizing(self, tmp_path):
        """Cumulative P&L of -12% → L1_REDUCE with 0.5 sizing factor."""
        signals = [_make_signal(-7.0), _make_signal(-5.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 0.5
        assert result["level"] == "L1_REDUCE"
        assert result["reason"] is not None
        assert "-12" in result["reason"] or "-12.00" in result["reason"]
        assert result["trades_in_window"] == 2

    def test_l1_boundary_at_exactly_minus10(self, tmp_path):
        """P&L of exactly -10% triggers L1 (threshold is strictly less than -10)."""
        signals = [_make_signal(-10.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        # -10.0 < -10.0 is False, so this should be NORMAL
        # Boundary: strictly < -10 triggers L1
        assert result["level"] == "NORMAL"

    def test_l1_just_past_boundary(self, tmp_path):
        """P&L of -10.01% triggers L1."""
        signals = [_make_signal(-10.01)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L1_REDUCE"
        assert result["sizing_factor"] == 0.5


class TestL2Gate:
    def test_l2_pauses_entries(self, tmp_path):
        """Cumulative P&L of -16% → L2_PAUSE with 0.0 sizing, not allowed."""
        signals = [_make_signal(-10.0), _make_signal(-6.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        assert result["allowed"] is False
        assert result["sizing_factor"] == 0.0
        assert result["level"] == "L2_PAUSE"
        assert result["reason"] is not None
        assert result["trades_in_window"] == 2

    def test_l2_boundary_at_exactly_minus15(self, tmp_path):
        """P&L of exactly -15% triggers L2 (threshold is strictly less than -15)."""
        signals = [_make_signal(-15.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        # -15.0 < -15.0 is False → L1 range
        assert result["level"] == "L1_REDUCE"

    def test_l2_just_past_boundary(self, tmp_path):
        """P&L of -15.01% triggers L2."""
        signals = [_make_signal(-15.01)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L2_PAUSE"
        assert result["allowed"] is False


class TestEdgeCases:
    def test_empty_signals_returns_normal(self, tmp_path):
        """No closed signals → NORMAL, sizing 1.0."""
        f = tmp_path / "closed_signals.json"
        f.write_text("[]", encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["allowed"] is True
        assert result["sizing_factor"] == 1.0
        assert result["level"] == "NORMAL"
        assert result["cumulative_pnl"] == 0.0
        assert result["trades_in_window"] == 0

    def test_missing_file_returns_normal(self, tmp_path):
        """Non-existent file → graceful fallback to NORMAL."""
        result = check_risk_gates(
            closed_signals_path=tmp_path / "nonexistent.json"
        )

        assert result["level"] == "NORMAL"
        assert result["sizing_factor"] == 1.0

    def test_signals_outside_window_excluded(self, tmp_path):
        """Signals older than rolling_days are excluded from cumulative P&L."""
        old_signal = _make_signal(-20.0, days_ago=25)   # outside 20-day window
        new_signal = _make_signal(2.0, days_ago=5)       # inside window
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps([old_signal, new_signal]), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f, rolling_days=20)

        # Old -20% signal must not count — only +2% signal counts
        assert result["level"] == "NORMAL"
        assert result["trades_in_window"] == 1
        assert abs(result["cumulative_pnl"] - 2.0) < 0.001

    def test_nested_pnl_format_is_handled(self, tmp_path):
        """signal_tracker.py nested final_pnl.spread_pnl_pct layout is parsed correctly."""
        signals = [_make_nested_signal(-12.0)]
        f = tmp_path / "closed_signals.json"
        f.write_text(json.dumps(signals), encoding="utf-8")

        result = check_risk_gates(closed_signals_path=f)

        assert result["level"] == "L1_REDUCE"
        assert result["trades_in_window"] == 1
