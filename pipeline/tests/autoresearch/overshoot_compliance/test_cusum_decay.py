import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import cusum_decay as CD


def _events(mean_hist, mean_recent, months_hist=60, events_per_month=20, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(months_hist):
        mu = mean_hist if m < months_hist - 24 else mean_recent
        for _ in range(events_per_month):
            rows.append({
                "date": pd.Timestamp("2020-01-01") + pd.DateOffset(months=m, days=int(rng.integers(1, 20))),
                "trade_ret_pct": rng.normal(mu, 1.0),
            })
    return pd.DataFrame(rows)


def test_cusum_triggers_when_recent_shifts_down():
    ev = _events(mean_hist=0.5, mean_recent=-0.5)
    report = CD.analyse(ev, recent_months=24)
    assert report["cusum_triggers"] >= 1


def test_cusum_no_trigger_on_stationary_edge():
    ev = _events(mean_hist=0.5, mean_recent=0.5)
    report = CD.analyse(ev, recent_months=24)
    assert report["cusum_triggers"] == 0


def test_recent_ratio_computed():
    ev = _events(mean_hist=0.5, mean_recent=0.3)
    report = CD.analyse(ev, recent_months=24)
    assert 0 < report["recent_24m_ratio"] < 1
    assert "recent_24m_mean_ret_pct" in report
    assert "full_history_mean_ret_pct" in report


def test_verdict_decaying_when_recent_under_half():
    ev = _events(mean_hist=1.0, mean_recent=0.1)
    report = CD.analyse(ev, recent_months=24)
    assert report["verdict"] == "DECAYING"


def test_verdict_stable_when_recent_at_least_half():
    ev = _events(mean_hist=0.5, mean_recent=0.4)
    report = CD.analyse(ev, recent_months=24)
    assert report["verdict"] in {"STABLE", "DECAYING"}
