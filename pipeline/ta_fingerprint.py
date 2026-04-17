"""
Fingerprint Card Generator — per-stock technical profile from backtest results.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.ta_fingerprint")

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "ta_fingerprints"

MOMENTUM_PATTERNS = {"BB_SQUEEZE", "VOL_BREAKOUT", "BB_BREAKOUT_UP"}
MEAN_REVERT_PATTERNS = {"RSI_OVERSOLD_BOUNCE", "RSI_OVERBOUGHT_REV"}
TREND_PATTERNS = {"DMA200_CROSS_UP", "MACD_CROSS_UP", "DMA200_CROSS_DN", "MACD_CROSS_DN"}
CANDLE_PATTERNS = {"CANDLE_HAMMER", "CANDLE_ENGULF_BULL", "CANDLE_ENGULF_BEAR", "CANDLE_DOJI"}


def _significance(occurrences: int, win_rate: float) -> str:
    if occurrences >= 10 and win_rate >= 0.60:
        return "STRONG"
    if occurrences >= 5 and win_rate >= 0.55:
        return "MODERATE"
    if occurrences >= 5 and win_rate >= 0.50:
        return "WEAK"
    return "INSIGNIFICANT"


def _classify_personality(significant: list[dict]) -> str:
    if not significant:
        return "pattern_agnostic"
    best = significant[0]["pattern"]
    if best in MOMENTUM_PATTERNS:
        return "momentum_breakout"
    if best in MEAN_REVERT_PATTERNS:
        return "mean_reverter"
    if best in TREND_PATTERNS:
        return "trend_follower"
    if best == "VOL_BREAKOUT":
        return "volume_driven"
    if best in CANDLE_PATTERNS:
        return "candlestick_responsive"
    return "mixed"


def generate_fingerprint(symbol: str, backtest_stats: dict, data_points: int = 0) -> dict:
    significant: list[dict] = []

    for pattern, stats in backtest_stats.items():
        occ = stats.get("occurrences", 0)
        wr = stats.get("win_rate_5d", 0)
        sig = _significance(occ, wr)
        if sig == "INSIGNIFICANT":
            continue
        significant.append({
            "pattern": pattern,
            "direction": stats.get("direction", "LONG"),
            "significance": sig,
            "occurrences": occ,
            "win_rate_5d": wr,
            "avg_return_5d": stats.get("avg_return_5d", 0),
            "avg_return_10d": stats.get("avg_return_10d", 0),
            "avg_drawdown": stats.get("min_return_5d", 0),
            "last_occurrence": stats.get("last_occurrence", ""),
        })

    significant.sort(key=lambda x: (-["INSIGNIFICANT", "WEAK", "MODERATE", "STRONG"].index(x["significance"]),
                                     -x["win_rate_5d"]))

    now = datetime.now(IST)
    return {
        "symbol": symbol,
        "generated": now.strftime("%Y-%m-%d"),
        "data_points": data_points,
        "total_patterns_tested": 15,
        "significant_patterns": len(significant),
        "fingerprint": significant,
        "best_pattern": significant[0]["pattern"] if significant else None,
        "best_win_rate": significant[0]["win_rate_5d"] if significant else 0,
        "personality": _classify_personality(significant),
    }


def save_fingerprint(card: dict, output_dir: Path = DEFAULT_OUTPUT) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{card['symbol']}.json"
    path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
