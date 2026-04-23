"""Raw-bar canonicity execution-window validator per
docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md section 2 and section 4.
"""
from __future__ import annotations

import pandas as pd


_MODE_WINDOWS = {
    "MODE_A": (0, 1),   # T and T+1 (inclusive, business-day offsets)
    "MODE_B": (0, 0),
    "MODE_C": (0, 0),
}


def build_flagged_dates(
    ticker: str,
    df: pd.DataFrame,
    business_days: pd.DatetimeIndex,
    stale_run_min: int = 3,
) -> dict:
    """Return {pd.Timestamp -> [flag_name, ...]} for every impaired day.

    Five flag names may be emitted:
    - "missing"    : expected business day not in df.index
    - "duplicate"  : timestamp appears 2+ times in df.index
    - "stale_run"  : bar is in a run of >= stale_run_min consecutive identical-OHLC bars
    - "zero_price" : any of OHLC <= 0
    - "zero_volume": Volume <= 0 (only when Volume column exists)
    """
    flagged: dict[pd.Timestamp, list[str]] = {}
    observed = pd.DatetimeIndex(df.index).normalize()
    observed_set = set(observed)
    # Listing-effect guard: pre-first-trade days are not "missing", they are
    # pre-existence. Clip the expected calendar to the ticker's first bar.
    first_obs = observed.min() if len(observed) else None
    expected_all = pd.DatetimeIndex(business_days).normalize()
    expected = {dt for dt in expected_all if first_obs is None or dt >= first_obs}

    # missing
    for dt in expected - observed_set:
        flagged.setdefault(dt, []).append("missing")

    # duplicate
    dup_mask = observed.duplicated(keep=False)
    for dt in observed[dup_mask]:
        flagged.setdefault(dt, [])
        if "duplicate" not in flagged[dt]:
            flagged[dt].append("duplicate")

    # stale runs of identical OHLC
    if len(df) > 0:
        key = (
            df["Open"].astype(float).astype(str) + "|"
            + df["High"].astype(float).astype(str) + "|"
            + df["Low"].astype(float).astype(str) + "|"
            + df["Close"].astype(float).astype(str)
        )
        run_id = (key != key.shift()).cumsum()
        run_sizes = run_id.groupby(run_id).transform("size")
        stale_mask = (run_sizes >= stale_run_min).to_numpy()
        for dt in pd.DatetimeIndex(df.index).normalize()[stale_mask]:
            flagged.setdefault(dt, [])
            if "stale_run" not in flagged[dt]:
                flagged[dt].append("stale_run")

    # zero price
    zero_price_mask = (df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    for dt in pd.DatetimeIndex(df.index).normalize()[zero_price_mask]:
        flagged.setdefault(dt, [])
        if "zero_price" not in flagged[dt]:
            flagged[dt].append("zero_price")

    # zero volume
    if "Volume" in df.columns:
        zero_vol_mask = df["Volume"].fillna(0) <= 0
        for dt in pd.DatetimeIndex(df.index).normalize()[zero_vol_mask]:
            flagged.setdefault(dt, [])
            if "zero_volume" not in flagged[dt]:
                flagged[dt].append("zero_volume")

    return flagged


def is_tradeable(
    ticker: str,
    trade_date,
    mode: str,
    per_ticker_audit: dict,
) -> tuple[bool, list[str]]:
    """Return (valid, reasons). Valid iff all bars in the execution window are clean.

    Args:
        ticker: NSE symbol (informational, not used in logic)
        trade_date: pd.Timestamp of entry (T)
        mode: "MODE_A" | "MODE_B" | "MODE_C"
        per_ticker_audit: dict with "flagged_dates" key mapping pd.Timestamp -> [flag_name, ...]

    Returns:
        (is_valid, reasons) where reasons is a list of flag names that invalidated the trade
        (empty list when valid).

    Raises:
        ValueError: if mode is not one of the recognised values.
    """
    if mode not in _MODE_WINDOWS:
        raise ValueError(f"unknown mode {mode!r}; expected one of {list(_MODE_WINDOWS)}")
    start_offset, end_offset = _MODE_WINDOWS[mode]
    entry = pd.Timestamp(trade_date).normalize()
    flagged_dates = per_ticker_audit.get("flagged_dates", {})
    bdays = pd.bdate_range(entry, periods=end_offset + 1).normalize()
    check = bdays[start_offset:end_offset + 1]

    reasons: list[str] = []
    for dt in check:
        flags = flagged_dates.get(dt, [])
        for f in flags:
            if f not in reasons:
                reasons.append(f)
    return (len(reasons) == 0, reasons)
