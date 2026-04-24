"""Pinned constants for the regime-aware autoresearch engine v1."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).parent / "data"
FNO_DIR = REPO_ROOT / "pipeline/data/fno_historical"

# Cointegration/panel quality gates
COINT_MAX_NA_FRACTION = 0.10
COINT_MIN_TRAIN_BARS = 120

# The 5 ETF regime labels. Canonical — do not rename.
REGIMES: tuple[str, ...] = ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")

# Split boundaries (ISO dates)
TRAIN_VAL_START = "2021-04-23"
TRAIN_VAL_END = "2024-04-22"
HOLDOUT_START = "2024-04-23"
HOLDOUT_END = "2026-04-23"

# Hurdle constants
DELTA_IN_SAMPLE = 0.15       # qualify-for-holdout Sharpe gap
DELTA_HOLDOUT = 0.10         # holdout-pass Sharpe gap
INCUMBENT_SCARCITY_MIN = 3   # < this -> scarcity fallback to regime-cond buy-and-hold

# Proposer budget
PROPOSALS_PER_REGIME_HARD_CAP = 500
CONSECUTIVE_NO_IMPROVE_SOFT_CAP = 50
PROPOSER_CONTEXT_WINDOW_SIZE = 200  # last-N in-sample proposals visible to LLM

# BH-FDR
BH_FDR_Q = 0.10
BH_FDR_BATCH_CALENDAR_DAYS = 30        # whichever-first with...
BH_FDR_BATCH_ACCUMULATED_COUNT = 10

# Lifecycle
SLOTS_PER_REGIME = 10
PROMOTIONS_PER_REGIME_PER_QUARTER = 2
FORWARD_SHADOW_MIN_DAYS = 60
FORWARD_SHADOW_MIN_EVENTS = 50
CUSUM_RECENT_24M_RETIRE_THRESHOLD = 0.50

# LLM
PROPOSER_MODEL = "claude-haiku-4-5-20251001"
