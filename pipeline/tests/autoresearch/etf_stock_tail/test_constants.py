import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def test_sigma_threshold_is_1_5():
    assert C.SIGMA_THRESHOLD == 1.5


def test_holdout_window_is_12_months():
    start = pd.Timestamp(C.HOLDOUT_START)
    end = pd.Timestamp(C.HOLDOUT_END)
    assert (end - start).days == 365 - 1  # 2025-04-26..2026-04-25 inclusive


def test_etf_list_has_30_symbols():
    assert len(C.ETF_SYMBOLS) == 30
    assert len(set(C.ETF_SYMBOLS)) == 30  # no duplicates


def test_baselines_locked():
    assert set(C.BASELINE_IDS) == {"B0_always_prior", "B1_regime_logistic", "B2_interactions_logistic"}


def test_random_seed_locked():
    assert C.RANDOM_SEED == 42
