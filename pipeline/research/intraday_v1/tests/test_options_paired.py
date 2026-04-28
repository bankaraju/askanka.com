"""Tests options_paired.py — ATM-strike resolution + paired-leg P&L."""
from __future__ import annotations

import pytest

from pipeline.research.intraday_v1 import options_paired


def test_atm_strike_round_to_50():
    # NIFTY strikes typically step by 50
    strikes = [22000, 22050, 22100, 22150, 22200, 22250]
    chosen = options_paired.resolve_atm_strike(spot=22107, available_strikes=strikes)
    assert chosen == 22100  # nearest


def test_atm_strike_picks_higher_when_tie():
    strikes = [100, 110, 120]
    # spot 105 → equidistant 100 / 110; tie-break: higher strike
    chosen = options_paired.resolve_atm_strike(spot=105, available_strikes=strikes)
    assert chosen == 110


def test_atm_strike_raises_when_no_strikes():
    with pytest.raises(ValueError, match="empty"):
        options_paired.resolve_atm_strike(spot=100, available_strikes=[])


def test_paired_leg_long_call_pnl():
    # Long stock direction → long ATM call paired leg
    leg = options_paired.build_paired_leg(
        underlying="RELIANCE",
        direction="LONG",
        spot_at_entry=2500.0,
        atm_strike=2500,
        entry_premium=50.0,
        exit_premium=70.0,
    )
    assert leg["instrument_type"] == "CE"
    assert leg["pnl_pct"] == pytest.approx((70 - 50) / 50 * 100)


def test_paired_leg_short_put_pnl():
    leg = options_paired.build_paired_leg(
        underlying="RELIANCE",
        direction="SHORT",
        spot_at_entry=2500.0,
        atm_strike=2500,
        entry_premium=50.0,
        exit_premium=30.0,
    )
    assert leg["instrument_type"] == "PE"
    assert leg["pnl_pct"] == pytest.approx((30 - 50) / 50 * 100)
