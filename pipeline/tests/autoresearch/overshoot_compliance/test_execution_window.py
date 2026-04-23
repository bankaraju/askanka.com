import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import execution_window as EW


def _df(rows):
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["Date"])
    return df.drop(columns=["Date"])


def _clean_audit(flagged_dates=None):
    return {"flagged_dates": flagged_dates or {}}


def test_mode_a_checks_t_and_t_plus_1():
    audit = _clean_audit({pd.Timestamp("2025-01-03"): ["missing"]})
    # Trade entered Jan 2, exit Jan 3 (T+1). T+1 impaired => invalid.
    valid, reasons = EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_A", audit)
    assert valid is False
    assert "missing" in reasons


def test_mode_a_passes_when_both_days_clean():
    valid, reasons = EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_A", _clean_audit())
    assert valid is True
    assert reasons == []


def test_mode_b_only_checks_entry_day():
    # T+1 impaired but MODE_B only cares about T
    audit = _clean_audit({pd.Timestamp("2025-01-03"): ["stale_run"]})
    valid, _ = EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_B", audit)
    assert valid is True
    # But T itself impaired invalidates MODE_B
    audit2 = _clean_audit({pd.Timestamp("2025-01-02"): ["zero_volume"]})
    valid2, reasons2 = EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_B", audit2)
    assert valid2 is False
    assert "zero_volume" in reasons2


def test_strict_any_flag_invalidates():
    for flag in ("missing", "duplicate", "stale_run", "zero_price", "zero_volume"):
        audit = _clean_audit({pd.Timestamp("2025-01-02"): [flag]})
        valid, reasons = EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_A", audit)
        assert valid is False
        assert flag in reasons


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        EW.is_tradeable("X", pd.Timestamp("2025-01-02"), "MODE_Z", _clean_audit())


def test_build_flagged_dates_detects_missing():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        # Jan 2 missing
        {"Date": "2025-01-03", "Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000},
    ]
    flagged = EW.build_flagged_dates("X", _df(rows),
                                      business_days=pd.bdate_range("2025-01-01", "2025-01-03"))
    assert "missing" in flagged[pd.Timestamp("2025-01-02")]


def test_build_flagged_dates_detects_stale_run():
    rows = [{"Date": d.strftime("%Y-%m-%d"), "Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 1000}
            for d in pd.bdate_range("2025-01-01", periods=5)]
    flagged = EW.build_flagged_dates("X", _df(rows),
                                      business_days=pd.bdate_range("2025-01-01", periods=5),
                                      stale_run_min=3)
    # All 5 bars are in a stale run >= 3 => all 5 flagged
    assert len(flagged) == 5
    for dt in flagged:
        assert "stale_run" in flagged[dt]


def test_build_flagged_dates_detects_zero_price_and_volume():
    rows = [
        {"Date": "2025-01-01", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
        {"Date": "2025-01-02", "Open": 0, "High": 0, "Low": 0, "Close": 0, "Volume": 1000},
        {"Date": "2025-01-03", "Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 0},
    ]
    flagged = EW.build_flagged_dates("X", _df(rows),
                                      business_days=pd.bdate_range("2025-01-01", "2025-01-03"))
    assert "zero_price" in flagged[pd.Timestamp("2025-01-02")]
    assert "zero_volume" in flagged[pd.Timestamp("2025-01-03")]
