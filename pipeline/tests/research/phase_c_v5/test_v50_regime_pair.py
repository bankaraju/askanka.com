from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5.variants import v50_regime_pair as v50


@pytest.fixture
def synth_ranker_df():
    """Two trading days of synthesised ranker output."""
    rows = []
    for d in ["2026-01-05", "2026-01-06"]:
        for rank, sym in enumerate(["LEAD1", "LEAD2", "LEAD3"], start=1):
            rows.append({"date": pd.Timestamp(d), "zone": "EUPHORIA",
                         "regime_age_days": rank, "side": "LONG", "rank": rank,
                         "symbol": sym, "drift_5d_mean": 0.10 - rank * 0.01,
                         "hit_rate_5d": 0.8, "episodes": 5})
        for rank, sym in enumerate(["LAG1", "LAG2", "LAG3"], start=1):
            rows.append({"date": pd.Timestamp(d), "zone": "EUPHORIA",
                         "regime_age_days": rank, "side": "SHORT", "rank": rank,
                         "symbol": sym, "drift_5d_mean": -0.05 + rank * 0.005,
                         "hit_rate_5d": 0.7, "episodes": 5})
    return pd.DataFrame(rows)


@pytest.fixture
def bars_for_v50():
    dates = pd.bdate_range(start="2026-01-05", periods=10)
    out = {}
    for sym, drift in [("LEAD1", 0.01), ("LEAD2", 0.01), ("LEAD3", 0.01),
                        ("LAG1", -0.005), ("LAG2", -0.005), ("LAG3", -0.005)]:
        rows, price = [], 100.0
        for d in dates:
            o = price
            c = price * (1 + drift)
            rows.append({"date": d, "open": o, "high": o * 1.01, "low": o * 0.99,
                         "close": c, "volume": 100_000})
            price = c
        out[sym] = pd.DataFrame(rows)
    return out


def test_v50_sub_variant_a_pools_all_regimes(synth_ranker_df, bars_for_v50):
    """Sub-variant a: N=3, all regimes pooled, no age filter."""
    ledger = v50.run(
        ranker_df=synth_ranker_df,
        symbol_bars=bars_for_v50,
        sub_variant="a",
        hold_days=3,
    )
    assert not ledger.empty
    # 2 entry dates × 3 longs × 3 shorts aggregated into 2 basket trades
    assert len(ledger) == 2
    assert set(ledger.columns) >= {
        "entry_date", "exit_date", "zone", "hold_days",
        "notional_total_inr", "pnl_gross_inr", "pnl_net_inr",
        "sub_variant", "top_n",
    }
    assert (ledger["sub_variant"] == "a").all()


def test_v50_sub_variant_c_filters_to_euphoria_optimism_only(synth_ranker_df, bars_for_v50):
    """Sub-variant c: only EUPHORIA + OPTIMISM days. Synthetic fixture has
    only EUPHORIA, so should match a (no filter effect)."""
    ledger_c = v50.run(ranker_df=synth_ranker_df, symbol_bars=bars_for_v50,
                       sub_variant="c", hold_days=3)
    ledger_a = v50.run(ranker_df=synth_ranker_df, symbol_bars=bars_for_v50,
                       sub_variant="a", hold_days=3)
    assert len(ledger_c) == len(ledger_a)


def test_v50_sub_variant_d_requires_regime_age_3(synth_ranker_df, bars_for_v50):
    """Sub-variant d: regime must be >= 3 days old. Fixture's regime_age_days
    goes 1/2/3 — only day 3+ qualifies; only one entry date survives."""
    synth = synth_ranker_df.copy()
    # Rewrite regime_age_days so only day 2026-01-06 has age >= 3
    synth["regime_age_days"] = synth.apply(
        lambda r: 4 if r["date"] == pd.Timestamp("2026-01-06") else 1, axis=1
    )
    ledger = v50.run(ranker_df=synth, symbol_bars=bars_for_v50,
                     sub_variant="d", hold_days=3)
    assert len(ledger) == 1
    assert ledger["entry_date"].iloc[0] == pd.Timestamp("2026-01-06")


def test_v50_invalid_sub_variant_raises():
    with pytest.raises(ValueError, match="sub_variant must be"):
        v50.run(ranker_df=pd.DataFrame(), symbol_bars={}, sub_variant="x",
                hold_days=3)
