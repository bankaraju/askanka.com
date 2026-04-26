from datetime import datetime

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.entry_timing_audit import (
    audit_entry_timing,
    EntryMode,
)


def test_audit_passes_when_lag_30min_in_mode_b():
    trades = pd.DataFrame({
        "signal_decidable_at": pd.to_datetime(["2026-03-03 09:15"]),
        "filled_at":           pd.to_datetime(["2026-03-03 09:45"]),
    })
    rep = audit_entry_timing(trades, mode=EntryMode.B)
    assert rep["pass"] is True


def test_audit_fails_when_fill_before_signal():
    trades = pd.DataFrame({
        "signal_decidable_at": pd.to_datetime(["2026-03-03 09:30"]),
        "filled_at":           pd.to_datetime(["2026-03-03 09:00"]),
    })
    rep = audit_entry_timing(trades, mode=EntryMode.C)
    assert rep["pass"] is False
    assert rep["n_lag_negative"] == 1


def test_mode_a_skips_sub30min_check():
    """MODE A (EOD-close fills) must NOT fail on a 5-minute lag — the sub-30min
    rule is specific to MODE B/C and exists to model intraday execution
    realism, which does not apply to EOD fills."""
    trades = pd.DataFrame({
        "signal_decidable_at": pd.to_datetime(["2026-03-03 15:30"]),
        "filled_at":           pd.to_datetime(["2026-03-03 15:35"]),
    })
    rep = audit_entry_timing(trades, mode=EntryMode.A)
    assert rep["pass"] is True
    assert rep["n_lag_under_30min"] == 0


def test_missing_columns_raises_with_context():
    trades = pd.DataFrame({"signal_decidable_at": pd.to_datetime(["2026-03-03 09:15"])})
    with pytest.raises(ValueError, match="filled_at"):
        audit_entry_timing(trades, mode=EntryMode.B)
