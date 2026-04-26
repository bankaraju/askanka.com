from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.replay_extender import (
    aggregate_minute_to_event_returns,
)


def test_aggregate_minute_to_event_returns_emits_per_event_row(tmp_path):
    """For each (ticker, trade_date) in minute parquet, emit one event row with
    open_to_1430 return and open_to_close return."""
    df = pd.DataFrame({
        "ticker":["A"]*4,
        "trade_date":[date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 09:45",
            "2026-03-03 14:30", "2026-03-03 15:30",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100.0,101.0,103.0,104.0],
        "high":[101.0,102.0,104.0,105.0],
        "low":[99.0,100.0,102.0,103.0],
        "close":[101.0,102.0,104.0,105.0],
        "volume":[1000]*4,
    })
    out = aggregate_minute_to_event_returns(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ticker"] == "A"
    assert row["trade_date"] == date(2026,3,3)
    assert row["open_to_1430_pct"] == pytest.approx((104.0 - 100.0)/100.0)
    assert row["open_to_close_pct"] == pytest.approx((105.0 - 100.0)/100.0)
