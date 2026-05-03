import json
import pandas as pd
import pytest
from pathlib import Path
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.holdout_ledger import (
    decide_open_rows,
    compute_atr_stop,
    decide_close_pnl,
)


def test_decide_open_rows_threshold_logic():
    preds = [
        {"ticker": "A", "direction": "LONG", "p_hat": 0.65},
        {"ticker": "A", "direction": "SHORT", "p_hat": 0.35},   # both: LONG fires (p_long>=0.6 AND p_short<0.4)
        {"ticker": "B", "direction": "LONG", "p_hat": 0.55},   # below 0.6, doesn't fire
        {"ticker": "C", "direction": "SHORT", "p_hat": 0.7},
        {"ticker": "C", "direction": "LONG", "p_hat": 0.3},    # SHORT fires
    ]
    fires = decide_open_rows(preds, p_long_threshold=0.6, p_short_threshold=0.4)
    fire_keys = {(f["ticker"], f["direction"]) for f in fires}
    assert ("A", "LONG") in fire_keys
    assert ("C", "SHORT") in fire_keys
    assert ("B", "LONG") not in fire_keys


def test_compute_atr_stop_long_and_short():
    long_stop = compute_atr_stop(entry=100.0, atr=2.0, mult=2.0, direction="LONG")
    assert long_stop == 96.0  # 100 - 2*2
    short_stop = compute_atr_stop(entry=100.0, atr=2.0, mult=2.0, direction="SHORT")
    assert short_stop == 104.0


def test_decide_close_pnl_long_full_hold():
    pnl, exit_reason = decide_close_pnl(
        entry=100.0, exit_ltp=102.0, stop=96.0,
        direction="LONG", position_inr=50000.0,
    )
    # +2% on 50k = +1000 INR
    assert pnl == pytest.approx(1000.0, rel=1e-9)
    assert exit_reason == "TIME_STOP"


def test_decide_close_pnl_long_atr_stopped():
    """If today's intraday low touched stop, exit at stop, NOT at 14:25 LTP."""
    pnl, exit_reason = decide_close_pnl(
        entry=100.0, exit_ltp=102.0, stop=96.0,
        direction="LONG", position_inr=50000.0, intraday_low=95.0,
    )
    # Stopped at 96 (lower of intraday touch), -4% = -2000
    assert pnl == pytest.approx(-2000.0, rel=1e-9)
    assert exit_reason == "ATR_STOP"
