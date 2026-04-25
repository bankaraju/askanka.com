"""Locked constants for H-2026-04-25-002 — DO NOT change without registering a new hypothesis version."""
from __future__ import annotations

# Label thresholds
SIGMA_THRESHOLD: float = 1.5      # |r_t| > 1.5 * sigma_60d → tail
SIGMA_LOOKBACK_DAYS: int = 60     # trailing window for sigma estimation, strict (excludes t)

# Splits (ISO dates, inclusive)
TRAIN_START: str = "2020-04-23"
TRAIN_END:   str = "2024-12-31"
VAL_START:   str = "2025-01-01"
VAL_END:     str = "2025-04-25"
HOLDOUT_START: str = "2025-04-26"
HOLDOUT_END:   str = "2026-04-25"

# ETF universe — 30 symbols from pipeline/autoresearch/etf_optimal_weights.json
# Order is stable: any change requires re-training and a new hypothesis version.
ETF_SYMBOLS: tuple[str, ...] = (
    "agriculture", "brazil", "developed", "dollar", "em", "euro",
    "financials", "high_yield", "india_etf", "industrials",
    "kbw_bank", "natgas", "silver", "sp500", "tech", "treasury",
    "yen", "india_vix_daily", "nifty_close_daily", "fii_net_daily",
    "dii_net_daily", "crude_oil", "gold", "copper", "global_bonds",
    "uk_etf", "japan_etf", "china_etf", "korea_etf", "taiwan_etf",
)

# NSE sectoral indices — Amendment A1.1 (2026-04-25), added before single-touch holdout consumed.
# 10 indices with 5-year daily coverage, no IPO discontinuities.
# CSV files: pipeline/data/sectoral_indices/<SYM>_daily.csv
SECTORAL_INDEX_SYMBOLS: tuple[str, ...] = (
    "BANKNIFTY", "NIFTYAUTO", "NIFTYENERGY", "NIFTYFMCG", "NIFTYIT",
    "NIFTYMEDIA", "NIFTYMETAL", "NIFTYPHARMA", "NIFTYPSUBANK", "NIFTYREALTY",
)

# Combined panel of indices used as the global state vector.
# Per Amendment A1.1 (2026-04-25), sectoral indices contribute identical-shape
# features alongside global ETFs.
ALL_INDEX_SYMBOLS: tuple[str, ...] = ETF_SYMBOLS + SECTORAL_INDEX_SYMBOLS

ETF_RETURN_WINDOWS: tuple[int, ...] = (1, 5, 20)

# Stock context features (6 dims, fixed order)
STOCK_CONTEXT_FEATURES: tuple[str, ...] = (
    "ret_5d", "vol_z_60d", "volume_z_20d",
    "adv_percentile_252d", "sector_id", "dist_from_52w_high_pct",
)

# Model architecture
EMBEDDING_DIM: int = 8
TRUNK_HIDDEN_1: int = 128
TRUNK_HIDDEN_2: int = 64
N_CLASSES: int = 3                # down_tail / neutral / up_tail
DROPOUT: float = 0.3

# Training hyperparams
LR: float = 1e-3
WEIGHT_DECAY_TRUNK: float = 1e-4
WEIGHT_DECAY_EMBEDDING: float = 1e-3   # 10× trunk on embedding parameter group
BATCH_SIZE: int = 256
MAX_EPOCHS: int = 100
EARLY_STOP_PATIENCE: int = 10

# Verdict gates (locked at registration)
DELTA_NATS: float = 0.005          # margin model must beat best baseline by
P_VALUE_FLOOR: float = 0.01
N_PERMUTATIONS: int = 100_000
FRAGILITY_TOL_PCT: float = 0.02    # ±2% holdout CE for STABLE
FRAGILITY_MIN_PASSING: int = 4     # of 6

# Universe drop rules
MIN_TAIL_EXAMPLES_PER_SIDE: int = 30   # per ticker in training window
MIN_REGIME_DAYS_IN_HOLDOUT: int = 30   # per regime

# Baseline identifiers (used in comparators output, locked)
BASELINE_IDS: tuple[str, ...] = (
    "B0_always_prior", "B1_regime_logistic", "B2_interactions_logistic",
)

# B2 interaction terms (locked at registration — no post-hoc additions)
B2_INTERACTIONS: tuple[tuple[str, str], ...] = (
    ("etf_brazil_ret_1d",          "sector_id"),
    ("etf_dollar_ret_1d",          "sector_id"),
    ("etf_india_vix_daily_ret_1d", "vol_z_60d"),
    ("etf_india_etf_ret_1d",       "dist_from_52w_high_pct"),
)

# Reproducibility
RANDOM_SEED: int = 42

# Class label encoding
CLASS_DOWN: int = 0
CLASS_NEUTRAL: int = 1
CLASS_UP: int = 2
CLASS_NAMES: tuple[str, ...] = ("down_tail", "neutral", "up_tail")
