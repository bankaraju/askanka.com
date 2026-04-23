"""Routing tests for the post-§3.1 geometry-aware signal generator."""
import json
import pytest
from pathlib import Path


class TestGeometryRouting:
    def _make_break(self, symbol, classification, expected, actual, trade_rec):
        """Build a break dict with all Task-5 enrichment fields populated."""
        return {
            "symbol": symbol,
            "classification": classification,
            "expected_return": expected,
            "actual_return": actual,
            "z_score": 3.5,
            "event_geometry": "LAG" if classification == "OPPORTUNITY_LAG"
                               else ("OVERSHOOT" if classification == "OPPORTUNITY_OVERSHOOT" else "LAG"),
            "direction_intended": "FOLLOW" if classification == "OPPORTUNITY_LAG" else "NEUTRAL",
            "direction_tested": "FADE",
            "direction_consistent": classification == "OPPORTUNITY_LAG",
            "trade_rec": trade_rec,
            "regime": "NEUTRAL",
            "oi_anomaly": False,
        }

    def test_lag_opportunity_emits_signal(self, tmp_path, monkeypatch):
        from pipeline import break_signal_generator as bsg
        from pipeline.break_signal_generator import generate_break_candidates

        monkeypatch.setattr(bsg, "compute_atr_stop",
                            lambda symbol, direction, **_: {"stop_pct": -2.3, "stop_price": 310.5})
        breaks = [self._make_break("RELIANCE", "OPPORTUNITY_LAG", 2.0, 0.5, "LONG")]
        breaks_file = tmp_path / "correlation_breaks.json"
        payload = {
            "breaks": breaks,
            "date": "2026-04-23",
            "scan_time": "2026-04-23T11:00:00+05:30",
        }
        breaks_file.write_text(json.dumps(payload), encoding="utf-8")
        signals = generate_break_candidates(breaks_path=breaks_file)
        assert len(signals) == 1
        assert signals[0]["_break_metadata"]["classification"] == "OPPORTUNITY_LAG"
        assert signals[0]["_break_metadata"]["event_geometry"] == "LAG"
        assert signals[0]["_break_metadata"]["direction_intended"] == "FOLLOW"
        assert signals[0]["_break_metadata"]["direction_tested"] == "FADE"

    def test_overshoot_opportunity_does_not_emit_signal(self, tmp_path, monkeypatch):
        from pipeline import break_signal_generator as bsg
        from pipeline.break_signal_generator import generate_break_candidates

        monkeypatch.setattr(bsg, "compute_atr_stop",
                            lambda symbol, direction, **_: {"stop_pct": -2.3, "stop_price": 310.5})
        # Even if trade_rec happens to be set (legacy/bug), OVERSHOOT label must gate out.
        breaks = [self._make_break("TORNTPOWER", "OPPORTUNITY_OVERSHOOT", 2.0, 3.0, None)]
        breaks_file = tmp_path / "correlation_breaks.json"
        payload = {
            "breaks": breaks,
            "date": "2026-04-23",
            "scan_time": "2026-04-23T11:00:00+05:30",
        }
        breaks_file.write_text(json.dumps(payload), encoding="utf-8")
        signals = generate_break_candidates(breaks_path=breaks_file)
        assert signals == []

    def test_legacy_opportunity_label_not_emitted(self, tmp_path, monkeypatch):
        from pipeline import break_signal_generator as bsg
        from pipeline.break_signal_generator import generate_break_candidates

        monkeypatch.setattr(bsg, "compute_atr_stop",
                            lambda symbol, direction, **_: {"stop_pct": -2.3, "stop_price": 310.5})
        """Historic correlation_breaks.json may still have bare OPPORTUNITY label.
        The signal generator must not emit a signal for that — only OPPORTUNITY_LAG."""
        breaks = [self._make_break("LEGACY", "OPPORTUNITY", 2.0, 0.5, "LONG")]
        breaks[0]["event_geometry"] = "LAG"
        breaks_file = tmp_path / "correlation_breaks.json"
        payload = {
            "breaks": breaks,
            "date": "2026-04-23",
            "scan_time": "2026-04-23T11:00:00+05:30",
        }
        breaks_file.write_text(json.dumps(payload), encoding="utf-8")
        signals = generate_break_candidates(breaks_path=breaks_file)
        assert signals == []

    def test_warning_does_not_emit_signal(self, tmp_path, monkeypatch):
        from pipeline import break_signal_generator as bsg
        from pipeline.break_signal_generator import generate_break_candidates

        monkeypatch.setattr(bsg, "compute_atr_stop",
                            lambda symbol, direction, **_: {"stop_pct": -2.3, "stop_price": 310.5})
        breaks = [self._make_break("RISK", "WARNING", 2.0, 0.5, None)]
        breaks_file = tmp_path / "correlation_breaks.json"
        payload = {
            "breaks": breaks,
            "date": "2026-04-23",
            "scan_time": "2026-04-23T11:00:00+05:30",
        }
        breaks_file.write_text(json.dumps(payload), encoding="utf-8")
        signals = generate_break_candidates(breaks_path=breaks_file)
        assert signals == []
