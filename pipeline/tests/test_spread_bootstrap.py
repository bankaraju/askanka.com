"""
Tests for pipeline/spread_bootstrap.py

Run:
    cd C:/Users/Claude_Anka/askanka.com
    python -m pytest pipeline/tests/test_spread_bootstrap.py -v --no-header
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure pipeline/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# tier_from_n
# =============================================================================


def test_tier_from_n_thresholds():
    from spread_bootstrap import tier_from_n
    assert tier_from_n(100) == "FULL"
    assert tier_from_n(30) == "FULL"
    assert tier_from_n(29) == "PROVISIONAL"
    assert tier_from_n(15) == "PROVISIONAL"
    assert tier_from_n(14) == "DROPPED"
    assert tier_from_n(0) == "DROPPED"


# =============================================================================
# ensure() — already-present case
# =============================================================================


def test_ensure_skips_if_already_present(monkeypatch, tmp_path):
    """ensure() returns status='already_present' when spread already has regime stats."""
    stats_file = tmp_path / "spread_stats.json"
    existing = {
        "Known Spread": {
            "MACRO_NEUTRAL": {"count": 55, "mean": 0.001, "std": 0.025,
                              "correlated_warning": False},
        }
    }
    stats_file.write_text(json.dumps(existing), encoding="utf-8")

    import spread_bootstrap as sb
    monkeypatch.setattr(sb, "_STATS_FILE", stats_file)

    result = sb.ensure("Known Spread", long_legs=["HAL"], short_legs=["TCS"])
    assert result["status"] == "already_present"
    assert result["name"] == "Known Spread"
    assert result["tier"] in ("FULL", "PROVISIONAL")


# =============================================================================
# ensure() — bootstrap + tiering
# =============================================================================


def test_ensure_bootstraps_and_tiers_correctly(monkeypatch, tmp_path):
    """
    Mock fetcher returns enough data to produce 3 regime buckets:
    MACRO_NEUTRAL n=40 (FULL), MACRO_EASY n=20 (PROVISIONAL), MACRO_STRESS n=10 (DROPPED).
    ensure() should write only the two >=15 buckets, drop MACRO_STRESS, and
    report tier=FULL (max across kept buckets).
    """
    import spread_bootstrap as sb

    stats_file = tmp_path / "spread_stats.json"
    stats_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sb, "_STATS_FILE", stats_file)

    # Build synthetic daily_data: 40 NEUTRAL, 20 EASY, 10 STRESS rows
    import random
    random.seed(42)

    def _row(regime):
        r = random.gauss(0, 0.01)
        return {"date": "2025-01-01", "regime": regime,
                "spread_return": r, "long_avg": r * 0.5, "short_avg": -r * 0.5}

    daily_data = (
        [_row("MACRO_NEUTRAL") for _ in range(40)]
        + [_row("MACRO_EASY") for _ in range(20)]
        + [_row("MACRO_STRESS") for _ in range(10)]
    )

    def _mock_fetch_daily_data(name, long_legs, short_legs, days=1825):
        return daily_data

    monkeypatch.setattr(sb, "_fetch_daily_data_for_spread", _mock_fetch_daily_data)

    result = sb.ensure("New Spread", long_legs=["A"], short_legs=["B"])

    assert result["status"] == "bootstrapped"
    assert result["tier"] == "FULL"           # max across kept buckets
    assert "MACRO_STRESS" in result["dropped_buckets"]
    assert result["n_samples"] == 40 + 20     # total kept

    # Verify on-disk: MACRO_STRESS should NOT be written
    written = json.loads(stats_file.read_text())
    assert "New Spread" in written
    assert "MACRO_NEUTRAL" in written["New Spread"]
    assert "MACRO_EASY" in written["New Spread"]
    assert "MACRO_STRESS" not in written["New Spread"]


# =============================================================================
# ensure() — fetch failure → skipped
# =============================================================================


def test_ensure_returns_skipped_on_fetch_failure(monkeypatch, tmp_path):
    """Mock fetcher raises; ensure() must not re-raise — returns status='skipped'."""
    import spread_bootstrap as sb

    stats_file = tmp_path / "spread_stats.json"
    stats_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sb, "_STATS_FILE", stats_file)

    def _failing_fetch(name, long_legs, short_legs, days=1825):
        raise RuntimeError("network timeout")

    monkeypatch.setattr(sb, "_fetch_daily_data_for_spread", _failing_fetch)

    result = sb.ensure("Bad Spread", long_legs=["X"], short_legs=["Y"])
    assert result["status"] == "skipped"
    assert result["name"] == "Bad Spread"
    assert "reason" in result


# =============================================================================
# regime_scanner wires bootstrap for unknown spreads
# =============================================================================


def test_regime_scanner_calls_bootstrap_for_unknown_spreads(monkeypatch, tmp_path):
    """
    Inject eligible_spreads with a spread not in spread_stats.
    Verify scan_regime() calls ensure() at least once.
    """
    import spread_bootstrap as sb

    stats_file = tmp_path / "spread_stats.json"
    stats_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sb, "_STATS_FILE", stats_file)

    ensure_calls = []

    def _mock_ensure(name, long_legs, short_legs):
        ensure_calls.append(name)
        return {"status": "skipped", "reason": "mock", "name": name}

    monkeypatch.setattr(sb, "ensure", _mock_ensure)

    # Patch regime_scanner to call bootstrap
    import regime_scanner as rs

    # Build a minimal trade-map file
    trade_map_file = tmp_path / "regime_trade_map.json"
    trade_map_file.write_text(json.dumps({
        "today_zone": "NEUTRAL",
        "results": {
            "NEUTRAL": {
                "Unknown Spread": {"win_rate": 0.6, "long_legs": ["SUNPHARMA"], "short_legs": ["HDFCBANK"]}
            }
        }
    }), encoding="utf-8")

    today_regime_file = tmp_path / "today_regime.json"
    prev_regime_file = tmp_path / "prev_regime.json"

    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map_file)
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", today_regime_file)
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", prev_regime_file)
    monkeypatch.setattr(rs, "_DATA", tmp_path)

    # Suppress MSI computation
    monkeypatch.setattr(rs, "_load_prev_regime", lambda: {})

    with patch("builtins.__import__", side_effect=_selective_import_blocker(["macro_stress"])):
        try:
            rs.scan_regime()
        except Exception:
            pass  # MSI failure is non-fatal; we only care about ensure calls

    assert len(ensure_calls) >= 1, f"ensure() was never called; calls={ensure_calls}"


def _selective_import_blocker(blocked_modules):
    """Return a custom __import__ that raises ImportError for listed modules."""
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _custom_import(name, *args, **kwargs):
        if any(name.startswith(m) for m in blocked_modules):
            raise ImportError(f"blocked in test: {name}")
        return original_import(name, *args, **kwargs)

    return _custom_import


# =============================================================================
# spread_intelligence triggers bootstrap when stats are missing
# =============================================================================


def test_gate_calls_bootstrap_when_stats_missing(monkeypatch, tmp_path):
    """
    apply_gates with spread not in spread_stats should trigger _maybe_bootstrap.
    The final status should still be INSUFFICIENT_DATA (bootstrap returns nothing usable),
    but the bootstrap attempt must have been made.
    """
    import spread_intelligence as si
    import spread_bootstrap as sb

    stats_file = tmp_path / "spread_stats.json"
    stats_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sb, "_STATS_FILE", stats_file)

    bootstrap_calls = []

    def _mock_maybe_bootstrap(spread_name, long_legs, short_legs):
        bootstrap_calls.append(spread_name)

    monkeypatch.setattr(si, "_maybe_bootstrap", _mock_maybe_bootstrap)

    regime_data = {
        "eligible_spreads": {
            "Mystery Spread": {"long_legs": ["A"], "short_legs": ["B"]}
        }
    }
    spread_stats = {}  # empty — nothing in stats

    result = si.apply_gates(
        spread_name="Mystery Spread",
        regime_data=regime_data,
        spread_stats=spread_stats,
        today_spread_return=0.01,
        regime="NEUTRAL",
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert "Mystery Spread" in bootstrap_calls
