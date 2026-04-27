"""Daily scan orchestration: detect -> join stats -> rank -> write JSON.

Per spec section 6.4 + 8.2.
"""
import json
from collections.abc import Callable
from datetime import date as _date, datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from pipeline.pattern_scanner.detect import detect_patterns_for_ticker, PatternFlag
from pipeline.pattern_scanner.rank import rank_today

IST = timezone(timedelta(hours=5, minutes=30))


def run_daily_scan(
    scan_date: _date,
    universe: list[str],
    bars_loader: Callable[[str], pd.DataFrame],
    stats_df: pd.DataFrame,
    out_path: Path,
    detect_fn: Callable | None = None,
) -> dict:
    """Detect today's patterns across the universe, rank against historical stats,
    write pattern_signals_today.json. Returns the payload dict.
    """
    detect_fn = detect_fn or detect_patterns_for_ticker
    all_flags: list[PatternFlag] = []
    for ticker in universe:
        bars = bars_loader(ticker)
        flags = detect_fn(ticker, bars, scan_date)
        all_flags.extend(flags)

    ranked = rank_today(all_flags, stats_df)

    qualified_count = len(ranked)
    today_flags_total = len(all_flags)
    below_threshold_count = today_flags_total - qualified_count

    payload = {
        "as_of": datetime.now(IST).isoformat(),
        "universe_size": len(universe),
        "today_flags_total": today_flags_total,
        "qualified_count": qualified_count,
        "below_threshold_count": below_threshold_count,
        "top_10": [
            {
                "signal_id": s.signal_id,
                "date": s.date.isoformat(),
                "ticker": s.ticker,
                "pattern_id": s.pattern_id,
                "direction": s.direction,
                "composite_score": round(s.composite_score, 4),
                "n_occurrences": s.n_occurrences,
                "win_rate": round(s.win_rate, 4),
                "z_score": round(s.z_score, 3),
                "mean_pnl_pct": round(s.mean_pnl_pct, 5),
                "fold_stability": round(s.fold_stability, 3),
                "last_seen": s.last_seen.isoformat() if hasattr(s.last_seen, "isoformat")
                    else str(s.last_seen),
            } for s in ranked
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return payload
