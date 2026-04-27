from datetime import date
import math
import pandas as pd
from pipeline.pattern_scanner.rank import rank_today, ScannerSignal
from pipeline.pattern_scanner.detect import PatternFlag


def _stats_row(ticker, pattern, direction, n, wr, z, mean_pnl, fold_stab):
    return {
        "ticker": ticker, "pattern_id": pattern, "direction": direction,
        "n_occurrences": n, "wins": int(round(wr * n)), "losses": n - int(round(wr * n)),
        "win_rate": wr, "mean_pnl_pct": mean_pnl, "stddev_pnl_pct": 0.01,
        "z_score": z, "fold_win_rates": [wr] * 4, "fold_stability": fold_stab,
        "first_seen": date(2020, 1, 1), "last_seen": date(2026, 4, 1),
    }


def test_filters_below_min_n():
    flags = [PatternFlag(date(2026, 4, 27), "ABC", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("ABC", "BULLISH_HAMMER", "LONG", n=20,
                                      wr=0.7, z=2.0, mean_pnl=0.012, fold_stab=0.8)])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert out == []


def test_filters_unstable_folds():
    flags = [PatternFlag(date(2026, 4, 27), "ABC", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("ABC", "BULLISH_HAMMER", "LONG", n=100,
                                      wr=0.7, z=4.0, mean_pnl=0.012, fold_stab=0.3)])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert out == []


def test_composite_score_ordering():
    flags = [
        PatternFlag(date(2026, 4, 27), "AAA", "BULLISH_HAMMER", "LONG", {}),
        PatternFlag(date(2026, 4, 27), "BBB", "MORNING_STAR", "LONG", {}),
    ]
    stats = pd.DataFrame([
        _stats_row("AAA", "BULLISH_HAMMER", "LONG", n=50, wr=0.62, z=1.7,
                   mean_pnl=0.010, fold_stab=0.8),
        _stats_row("BBB", "MORNING_STAR", "LONG", n=500, wr=0.55, z=2.2,
                   mean_pnl=0.020, fold_stab=0.8),
    ])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert len(out) == 2
    # composite = z * log(1+n) * |mean_pnl|; BBB > AAA
    assert out[0].ticker == "BBB"


def test_top_n_truncation():
    flags = [PatternFlag(date(2026, 4, 27), f"T{i:02d}", "BULLISH_HAMMER", "LONG", {})
             for i in range(15)]
    stats = pd.DataFrame([
        _stats_row(f"T{i:02d}", "BULLISH_HAMMER", "LONG", n=50, wr=0.6 - i * 0.001,
                   z=2.0, mean_pnl=0.012, fold_stab=0.8) for i in range(15)
    ])
    out = rank_today(flags, stats, min_n=30, min_fold_stability=0.5, top_n=10)
    assert len(out) == 10


def test_signal_id_format():
    flags = [PatternFlag(date(2026, 4, 27), "RELIANCE", "BULLISH_HAMMER", "LONG", {})]
    stats = pd.DataFrame([_stats_row("RELIANCE", "BULLISH_HAMMER", "LONG", n=50,
                                      wr=0.6, z=2.0, mean_pnl=0.012, fold_stab=0.8)])
    out = rank_today(flags, stats)
    assert out[0].signal_id == "2026-04-27_RELIANCE_BULLISH_HAMMER"
