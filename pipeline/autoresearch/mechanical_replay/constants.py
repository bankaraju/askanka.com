"""Spec-frozen constants for the mechanical 60-day replay.

All rules mirror the live engine as of 2026-04-25. Single edit point if
execution rules change. Spec at
docs/superpowers/specs/2026-04-25-mechanical-60day-replay-design.md.
"""
from __future__ import annotations

from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

# Window
IST = ZoneInfo("Asia/Kolkata")
WINDOW_DAYS = 60

# Session boundaries (IST)
SESSION_OPEN = time(9, 15)
ENTRY_TIME = time(9, 30)        # mandate: every signal enters at 09:30
HARD_CLOSE = time(14, 30)       # mandate: 14:30 force-close
SESSION_CLOSE = time(15, 30)

# ATR-based stop. Live intent (per break_signal_generator.py:143-149):
# Phase C is intraday → 1.0× ATR with abs cap at 3.5%. Overnight default 2.0×
# (atr_stops.py module default), used here for any non-intraday engine entries
# the replay processes. Note: live atr_stops.py is missing the max_abs_pct
# kwarg the caller passes — separate live bug, replay honors documented intent.
ATR_LOOKBACK = 14
ATR_MULT_INTRADAY = 1.0
ATR_MULT_OVERNIGHT = 2.0
ATR_MAX_ABS_PCT = 3.5
ATR_FALLBACK_PCT = -1.0

# Trail logic (mirrors signal_tracker.check_signal_status post-2026-04-22 B9 + B10)
TRAIL_ARM_PCT = 2.0             # trail arms when peak >= trail_budget
DAILY_STOP_FRACTION = 0.50      # daily_stop = -(avg_favorable_move * 0.50)

# Slippage (per backtesting-specs.txt §1)
SLIPPAGE_BPS_ROUNDTRIP = 20

# Data validation
MIN_BARS_PER_SESSION = 350
FIRST_BAR_LATEST = time(9, 18)
LAST_BAR_EARLIEST = time(15, 25)

# Sanity checks (per spec §10)
COVERAGE_THRESHOLD_PCT = 95.0
LIVE_CROSSCHECK_PNL_TOL_PP = 2.0
LIVE_CROSSCHECK_AGREE_PCT = 80.0

# File paths (resolved relative to repo root)
_REPO = Path(__file__).resolve().parents[3]

# Inputs (read-only — registered via canonical artifact)
CANONICAL_JSON = _REPO / "pipeline" / "data" / "canonical_fno_research_v1.json"
FNO_DAILY_DIR = _REPO / "pipeline" / "data" / "fno_historical"
SECTORAL_DIR = _REPO / "pipeline" / "data" / "sectoral_indices"
REGIME_HISTORY_CSV = _REPO / "pipeline" / "data" / "regime_history.csv"
BREAK_HISTORY_JSON = _REPO / "pipeline" / "data" / "correlation_break_history.json"
CLOSED_SIGNALS_JSON = _REPO / "pipeline" / "data" / "signals" / "closed_signals.json"
RANKER_STATE_JSON = _REPO / "pipeline" / "data" / "regime_ranker_state.json"

# Minute-bar cache — passthrough to SP1's existing fetcher
SP1_BARS_DIR = _REPO / "pipeline" / "data" / "research" / "phase_c_shape_audit" / "bars"

# Outputs
DATA_DIR = _REPO / "pipeline" / "data" / "research" / "mechanical_replay"
TRADES_CSV = DATA_DIR / "trades_with_exit.csv"
ENGINE_SUMMARY_JSON = DATA_DIR / "engine_summary.json"
REPORT_MD = _REPO / "docs" / "research" / "mechanical_replay" / "2026-04-25-replay-60day.md"

# Sector → NSE sectoral index map (per canonical audit doc §9)
SECTOR_TO_INDEX = {
    "Banks": "BANKNIFTY",
    "IT_Services": "NIFTYIT",
    "Pharma": "NIFTYPHARMA",
    "FMCG": "NIFTYFMCG",
    "Metals_Mining": "NIFTYMETAL",
    "Power_Utilities": "NIFTYPSUBANK",  # proxy
    "Auto_Components": "NIFTYAUTO",     # proxy
    "Consumer_Discretionary": "NIFTYAUTO",  # proxy
    "Real_Estate": "NIFTYREALTY",
    "Oil_Gas": "NIFTYENERGY",
    "Media": "NIFTYMEDIA",
}

# Phase C classifications considered tradeable per the live engine (post-2026-04-23 split)
PHASE_C_LAG_CLASSIFICATION = "OPPORTUNITY_LAG"
PHASE_C_LEGACY_CLASSIFICATION = "OPPORTUNITY"  # pre-relabel — still in 60-day history
