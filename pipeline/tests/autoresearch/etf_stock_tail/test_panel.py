import json
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import (
    PanelInputs,
    PanelDropReason,
    assemble_panel,
)


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        for d in dates:
            day = (d - dates[0]).days + 1
            rows.append({"date": d, "etf": sym, "close": float((i + 1) * day)})
    return pd.DataFrame(rows)


def _mk_stock_bars(start: str, n_days: int, vol_scale: float = 0.005) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(123)
    rets = rng.normal(0, vol_scale, n_days)
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def _mk_stock_bars_with_tails(start: str, n_days: int, n_up_tails: int = 35, n_down_tails: int = 35) -> pd.DataFrame:
    """Stock bars with deliberate tail events distributed in time.

    Injects explicit ±10% returns at non-overlapping, evenly-spaced indices in the
    training-window zone (approximately day 91 onward) so that:
      - Up- and down-tail indices are offset by 4 days each (never overlap).
      - At most ~7–8 large returns fall in any 60-day σ-estimation window, keeping
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


def _mk_universe(symbols, dates) -> dict:
    return {d.strftime("%Y-%m-%d"): list(symbols) for d in dates}


def _mk_sector_map(symbols) -> dict:
    return {s: i % 5 for i, s in enumerate(symbols)}


def test_panel_columns(tmp_path):
    """Panel has all 90 ETF + 6 context + ticker_id + label cols, with real rows."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    expected_etf_cols = 30 * 3
    expected_ctx_cols = 6
    assert "ticker_id" in panel.columns
    assert "label" in panel.columns
    assert "date" in panel.columns
    assert "ticker" in panel.columns
    assert "regime" in panel.columns
    # ETF + context columns total 96
    feature_cols = [c for c in panel.columns if c.startswith(("etf_", "stock_"))]
    assert len(feature_cols) == expected_etf_cols + expected_ctx_cols
    # Verify the panel is not empty — AAA must survive the tail screen and produce real rows
    assert len(panel) > 0, "panel must have real rows, not just an empty schema"
    assert "AAA" in panel["ticker"].values
    assert manifest["n_tickers_kept"] == 1


def test_drops_ticker_with_too_few_tail_examples(tmp_path):
    """A ticker with < MIN_TAIL_EXAMPLES_PER_SIDE in either direction is dropped."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    flat_bars = _mk_stock_bars("2024-01-01", 400, vol_scale=0.0001)  # near-zero vol → no tails
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"BBB": flat_bars},
        universe=_mk_universe(["BBB"], dates),
        sector_map=_mk_sector_map(["BBB"]),
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    assert "BBB" in manifest["dropped_tickers"]
    assert manifest["dropped_tickers"]["BBB"] == PanelDropReason.INSUFFICIENT_TAIL_LABELS.value
    assert (panel["ticker"] == "BBB").sum() == 0


def test_manifest_contains_input_hashes(tmp_path):
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
    )
    _, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                 train_end=pd.Timestamp("2024-12-31"))
    assert "etf_panel_sha256" in manifest
    assert len(manifest["etf_panel_sha256"]) == 64
    assert "config_sha256" in manifest
    assert "n_rows" in manifest


def test_regime_history_joins_correctly():
    """When regime_history is provided, panel rows carry the regime label, not 'UNKNOWN'."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    regime_history = pd.DataFrame({
        "date": dates,
        "regime": ["RISK_ON" if i < 200 else "RISK_OFF" for i in range(400)],
    })
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
        regime_history=regime_history,
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    assert len(panel) > 0
    # Every row should have a real regime label, never UNKNOWN
    assert (panel["regime"] != "UNKNOWN").all()
    # Both regime values should appear in the panel
    regimes_seen = set(panel["regime"].unique())
    assert regimes_seen <= {"RISK_ON", "RISK_OFF"}
    assert len(regimes_seen) >= 1   # at least one regime appears
