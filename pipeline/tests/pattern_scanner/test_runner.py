import json
from datetime import date
from unittest.mock import MagicMock
import pandas as pd
import pytest
from pipeline.pattern_scanner.runner import run_daily_scan
from pipeline.pattern_scanner.detect import PatternFlag


def test_runner_writes_signals_today_json(tmp_path):
    out_dir = tmp_path / "scanner"
    out_dir.mkdir()
    out_path = out_dir / "pattern_signals_today.json"

    flags_by_ticker = {
        "RELIANCE": [PatternFlag(date(2026, 4, 27), "RELIANCE",
                                  "BULLISH_HAMMER", "LONG", {})],
        "TATAMOTORS": [PatternFlag(date(2026, 4, 27), "TATAMOTORS",
                                    "BEARISH_ENGULFING", "SHORT", {})],
    }
    detect_fn = lambda ticker, _bars, _scan_date: flags_by_ticker.get(ticker, [])
    bars_loader = lambda _t: pd.DataFrame({"open": [1], "high": [1], "low": [1],
                                            "close": [1]}, index=[pd.Timestamp("2026-04-27")])

    stats = pd.DataFrame([
        {"ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER", "direction": "LONG",
         "n_occurrences": 156, "wins": 97, "losses": 59, "win_rate": 0.62,
         "mean_pnl_pct": 0.012, "stddev_pnl_pct": 0.02, "z_score": 3.0,
         "fold_win_rates": [0.6, 0.62, 0.65, 0.61], "fold_stability": 0.78,
         "first_seen": date(2020, 4, 1), "last_seen": date(2026, 3, 12)},
        {"ticker": "TATAMOTORS", "pattern_id": "BEARISH_ENGULFING", "direction": "SHORT",
         "n_occurrences": 42, "wins": 24, "losses": 18, "win_rate": 0.57,
         "mean_pnl_pct": 0.009, "stddev_pnl_pct": 0.015, "z_score": 0.91,
         "fold_win_rates": [0.55, 0.6, 0.58, 0.56], "fold_stability": 0.85,
         "first_seen": date(2021, 1, 1), "last_seen": date(2026, 4, 20)},
    ])

    run_daily_scan(
        scan_date=date(2026, 4, 27),
        universe=["RELIANCE", "TATAMOTORS"],
        bars_loader=bars_loader,
        stats_df=stats,
        out_path=out_path,
        detect_fn=detect_fn,
    )

    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["as_of"].startswith("2026-04-27")
    assert payload["universe_size"] == 2
    assert payload["today_flags_total"] == 2
    assert payload["qualified_count"] == 2
    assert len(payload["top_10"]) == 2
