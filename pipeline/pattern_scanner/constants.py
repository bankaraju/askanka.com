"""Pattern Scanner constants — the canonical 12-pattern set + thresholds.

Per spec §9 (`docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md`).
"""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PatternDef:
    pattern_id: str
    direction: Literal["LONG", "SHORT"]
    pandas_ta_name: str | None  # documentary: pandas-ta function that would match. We hand-roll all 12.
    semantic: str


PATTERNS: list[PatternDef] = [
    PatternDef("BULLISH_HAMMER",    "LONG",  "hammer",        "Reversal-up after downtrend"),
    PatternDef("BULLISH_ENGULFING", "LONG",  "engulfing+",    "Strong reversal-up"),
    PatternDef("MORNING_STAR",      "LONG",  "morningstar",   "3-candle reversal-up"),
    PatternDef("PIERCING_LINE",     "LONG",  "piercing",      "2-candle reversal-up"),
    PatternDef("BB_BREAKOUT",       "LONG",  None,            "BB squeeze + close above upper"),
    PatternDef("MACD_BULL_CROSS",   "LONG",  None,            "MACD line crosses signal up"),
    PatternDef("SHOOTING_STAR",     "SHORT", "shootingstar",  "Reversal-down after uptrend"),
    PatternDef("BEARISH_ENGULFING", "SHORT", "engulfing-",    "Strong reversal-down"),
    PatternDef("EVENING_STAR",      "SHORT", "eveningstar",   "3-candle reversal-down"),
    PatternDef("DARK_CLOUD_COVER",  "SHORT", "darkcloudcover","2-candle reversal-down"),
    PatternDef("BB_BREAKDOWN",      "SHORT", None,            "BB squeeze + close below lower"),
    PatternDef("MACD_BEAR_CROSS",   "SHORT", None,            "MACD line crosses signal down"),
]

WIN_THRESHOLD: float = 0.008          # +/- 0.8% T+1 open-to-close
MIN_N: int = 30                        # min occurrences for ranking eligibility
MIN_FOLD_STABILITY: float = 0.5        # min walk-forward fold-stability ratio
TOP_N: int = 10                        # daily Top-N

BB_LENGTH: int = 20
BB_STD: float = 2.0
BB_SQUEEZE_RATIO: float = 0.7          # current band width < 20-day avg * 0.7

MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9
