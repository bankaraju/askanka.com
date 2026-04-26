from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.walk_forward_runner import (
    purged_train_dates,
    PurgeConfig,
)


def test_purged_train_dates_drops_embargo_window():
    """Train dates within ±embargo_days of test window must be dropped (§10.2)."""
    train = pd.DatetimeIndex(pd.date_range("2025-01-01", "2025-01-31", freq="D"))
    test_start = pd.Timestamp("2025-01-20")
    test_end = pd.Timestamp("2025-01-22")
    cfg = PurgeConfig(embargo_days=5)
    out = purged_train_dates(train, test_start, test_end, cfg)
    assert pd.Timestamp("2025-01-14") in out
    assert pd.Timestamp("2025-01-15") not in out
    assert pd.Timestamp("2025-01-27") not in out
    assert pd.Timestamp("2025-01-28") in out


def test_purged_train_dates_overlap_holding_period():
    """Trades in train that close within test window must be purged (§10.3)."""
    train = pd.DatetimeIndex(pd.date_range("2025-01-01", "2025-01-31", freq="D"))
    test_start = pd.Timestamp("2025-01-20")
    test_end = pd.Timestamp("2025-01-22")
    cfg = PurgeConfig(embargo_days=0, holding_period_days=5)
    out = purged_train_dates(train, test_start, test_end, cfg)
    assert pd.Timestamp("2025-01-16") not in out
    assert pd.Timestamp("2025-01-15") in out  # closes 01-20 — inclusive boundary
