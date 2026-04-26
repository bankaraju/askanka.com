from datetime import date

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.phase_2.data_audit import audit_run_data


def test_audit_counts_zero_volume_and_stale():
    df = pd.DataFrame({
        "ticker": ["A","A","A","A"],
        "trade_date": [date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15","2026-03-03 09:16",
            "2026-03-03 09:17","2026-03-03 09:18",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100,100,100,101], "high":[100,100,100,101],
        "low":[100,100,100,101], "close":[100,100,100,101],
        "volume":[10, 0, 0, 5],
    })
    rep = audit_run_data(df)
    assert rep["zero_volume_bar_count"] == 2
    assert rep["stale_quote_count_min3"] == 1   # 3 consecutive identical OHLC bars
    assert rep["bad_data_pct"] >= 0
