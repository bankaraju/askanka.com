"""Spec-frozen constants. Single edit point if thresholds change."""
from __future__ import annotations

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

# Window — 60 calendar days ending on the run date (spec §2, §4)
WINDOW_DAYS = 60

# Session boundaries (IST)
IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
HARD_CLOSE = time(14, 30)  # spec §5.5: 14:30 force-close

# Bar validation gate (spec §5.2)
MIN_BARS_PER_SESSION = 350      # 375 full session, allow 25 missing
FIRST_BAR_LATEST = time(9, 18)  # Kite open-tick latency
LAST_BAR_EARLIEST = time(15, 25)
OPEN_PRICE_MISMATCH_TOL_PCT = 0.05  # vs persisted day-open from history

# Shape thresholds (spec §5.4)
PEAK_PCT_THRESHOLD = 0.5    # |peak_pct| >= 0.5%
TROUGH_PCT_THRESHOLD = -0.5
PEAK_HALF_GIVEBACK = 2.0    # close_pct <= peak_pct / 2 means at least half giveback
ONE_WAY_TOLERANCE = 0.5     # close_pct > peak_pct - 0.5 means "near max"

# Entry-time grid for counterfactual replay (spec §5.5)
ENTRY_GRID = (
    time(9, 15),
    time(9, 20),
    time(9, 25),
    time(9, 30),
    time(9, 45),
)

# Execution rule constants (spec §5.5)
STOP_LOSS_PCT = 3.0
TARGET_PCT = 4.5
TRAIL_ARM_PCT = 2.0
TRAIL_DROP_PCT = 1.5

# Verdict thresholds (spec §7)
BASELINE_WIN_RATE = 0.564     # 56.4% from track_record (39 closed, 22 wins)
CONFIRMED_WIN_RATE = 0.70
WEAK_WIN_RATE_LO = 0.60
WEAK_WIN_RATE_HI = 0.70
DISCIPLINE_DELTA_PP = 1.0     # mean(cf - actual) > 1pp triggers DISCIPLINE_ONLY
MIN_CELL_N = 10
REGIME_SURVIVAL_MIN = 2       # of 5 regimes for unconditional CONFIRMED

# File paths (resolved relative to repo root)
_REPO = Path(__file__).resolve().parents[3]
DATA_DIR = _REPO / "pipeline" / "data" / "research" / "phase_c_shape_audit"
BARS_DIR = DATA_DIR / "bars"
TRADES_CSV = DATA_DIR / "trades_with_shape.csv"
MISSED_CSV = DATA_DIR / "missed_signals.csv"
REPORT_MD = _REPO / "docs" / "research" / "phase_c_shape_audit" / "2026-04-25-shape-audit.md"

# Source paths (read-only)
CLOSED_SIGNALS_JSON = _REPO / "pipeline" / "data" / "signals" / "closed_signals.json"
BREAK_HISTORY_JSON = _REPO / "pipeline" / "data" / "correlation_break_history.json"
REGIME_HISTORY_CSV = _REPO / "pipeline" / "data" / "regime_history.csv"
