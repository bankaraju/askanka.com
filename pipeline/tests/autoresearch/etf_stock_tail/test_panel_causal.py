# pipeline/tests/autoresearch/etf_stock_tail/test_panel_causal.py
"""Mirror of pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py.

For a row in the training window, mutate every input field AFTER train_end
(i.e. only in the holdout zone) and assert the row's features are unchanged.

Two corrections vs. the verbatim plan spec:

1. _mk_stock_bars uses deliberate ±10% tail injections (the _mk_stock_bars_with_tails
   pattern from test_panel.py) instead of random std=0.012 closes.
   Reason: the random fixture yields only ~21 up / ~22 down tails in the
   training window, which is below MIN_TAIL_EXAMPLES_PER_SIDE=30, so AAA would
   be dropped and the panel would be empty.

2. The mutation boundary is `date > train_end` (strictly after the training
   window) rather than `date >= eval_date`.
   Reason: label_series computes the return AT eval_date using close[eval_date],
   so mutating close[eval_date] changes that label.  More generally, any
   mutation inside the training window changes tail counts and can cause AAA to
   fail the MIN_TAIL_EXAMPLES_PER_SIDE screen, emptying panel_mut.  Mutating
   only the holdout zone (> train_end) leaves train-window labels intact,
   keeps AAA in the panel, and still exercises the causal guarantee: holdout-
   zone data must not pollute training-window features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import PanelInputs, assemble_panel


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rows = []
    rng = np.random.default_rng(7)
    for i, sym in enumerate(C.ALL_INDEX_SYMBOLS):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.005, n_days))
        for d, c in zip(dates, closes):
            rows.append({"date": d, "etf": sym, "close": float(c)})
    return pd.DataFrame(rows)


def _mk_stock_bars(start: str, n_days: int, n_up_tails: int = 35, n_down_tails: int = 35) -> pd.DataFrame:
    """Stock bars with deliberate tail events so AAA survives MIN_TAIL_EXAMPLES_PER_SIDE=30.

    Injects explicit ±10% returns at non-overlapping, evenly-spaced indices in the
    training-window zone (approximately day 91 onward) so that:
      - Up- and down-tail indices are offset by 4 days each (never overlap).
      - At most ~7-8 large returns fall in any 60-day σ-estimation window, keeping
        σ moderate enough that 10% returns always clear the 1.5σ threshold.
      - The tail-label screen reliably sees >= MIN_TAIL_EXAMPLES_PER_SIDE in each
        direction, so the ticker is kept and the panel has real rows.
    """
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.005, n_days)
    # Start from ~day 91 (≈ train_start) so tails land in the training window.
    # Cycle length = 8 days: up on day 0, down on day 4 of each cycle.
    tail_start = 91
    up_indices = list(range(tail_start, n_days, 8))[:n_up_tails]
    down_indices = list(range(tail_start + 4, n_days, 8))[:n_down_tails]
    for i in up_indices:
        rets[i] = 0.10    # +10%: always clears 1.5σ even after σ inflation
    for i in down_indices:
        rets[i] = -0.10
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def test_panel_features_causal_against_holdout_mutation():
    n_days = 400
    train_start = pd.Timestamp("2024-04-01")
    train_end = pd.Timestamp("2024-12-31")

    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", n_days),
        stock_bars={"AAA": _mk_stock_bars("2024-01-01", n_days)},
        universe={d.strftime("%Y-%m-%d"): ["AAA"] for d in pd.date_range("2024-01-01", periods=n_days, freq="D")},
        sector_map={"AAA": 0},
    )
    panel, _ = assemble_panel(inputs, train_start=train_start, train_end=train_end)
    assert len(panel) > 100

    # Pick a row from the training window (first quarter avoids edge effects).
    row = panel.iloc[len(panel) // 4]
    eval_date = pd.Timestamp(row["date"])
    assert eval_date <= train_end, "eval_date must be in the training window"

    # Mutate ALL input data strictly AFTER train_end (holdout zone only).
    # This preserves train-window tail counts so AAA is not dropped from panel_mut,
    # while still verifying that holdout-zone data cannot contaminate training-window
    # features (the causal guarantee we care about).
    inputs_mut = PanelInputs(
        etf_panel=inputs.etf_panel.copy(),
        stock_bars={"AAA": inputs.stock_bars["AAA"].copy()},
        universe=inputs.universe,
        sector_map=inputs.sector_map,
    )
    inputs_mut.etf_panel.loc[inputs_mut.etf_panel["date"] > train_end, "close"] *= 99.0
    inputs_mut.stock_bars["AAA"].loc[inputs_mut.stock_bars["AAA"]["date"] > train_end, "close"] *= 99.0
    inputs_mut.stock_bars["AAA"].loc[inputs_mut.stock_bars["AAA"]["date"] > train_end, "volume"] *= 99.0

    panel_mut, _ = assemble_panel(inputs_mut, train_start=train_start, train_end=train_end)

    # AAA must survive the tail-label screen in the mutated panel.
    matched = panel_mut[(panel_mut["date"] == eval_date) & (panel_mut["ticker"] == "AAA")]
    assert len(matched) == 1, (
        f"AAA row for {eval_date.date()} not found in mutated panel — "
        "train-window tail screen failed (mutation spilled into training window)"
    )

    # Features for the training-window row must be byte-identical.
    feature_cols = [c for c in panel.columns if c.startswith(("etf_", "stock_"))]
    pd.testing.assert_series_equal(
        row[feature_cols].astype(float),
        matched.iloc[0][feature_cols].astype(float),
        check_names=False,
    )
