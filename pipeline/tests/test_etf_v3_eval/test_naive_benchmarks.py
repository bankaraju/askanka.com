import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.naive_benchmarks import (
    random_direction,
    always_long,
    always_short,
    never_trade,
)


def test_always_long_returns_event_returns_unchanged():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = always_long(events)
    assert out["benchmark_pnl"].tolist() == [0.01, -0.02, 0.03]


def test_always_short_inverts_returns():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = always_short(events)
    assert out["benchmark_pnl"].tolist() == [-0.01, 0.02, -0.03]


def test_never_trade_returns_zero():
    events = pd.DataFrame({"realized_pct": [0.01, -0.02, 0.03]})
    out = never_trade(events)
    assert out["benchmark_pnl"].tolist() == [0.0, 0.0, 0.0]


def test_random_direction_uses_seeded_rng():
    rng = np.random.default_rng(42)
    events = pd.DataFrame({"realized_pct": np.arange(100) * 0.001})
    out_a = random_direction(events, rng=np.random.default_rng(42))
    out_b = random_direction(events, rng=np.random.default_rng(42))
    assert out_a["benchmark_pnl"].equals(out_b["benchmark_pnl"])
