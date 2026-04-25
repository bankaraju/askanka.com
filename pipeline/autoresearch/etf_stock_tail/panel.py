"""Assemble (ticker × date) feature + label panel with deterministic SHA256 manifest.

Drop rules:
  - INSUFFICIENT_TAIL_LABELS — ticker has < MIN_TAIL_EXAMPLES_PER_SIDE in either tail direction in train window
  - MISSING_SECTOR_MAP       — ticker is absent from sector_map (cannot assign a sector_id feature)
                               (NaN labels caused by insufficient bar history are silently skipped at the row level.)
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.etf_features import build_etf_features_matrix, etf_feature_names
from pipeline.autoresearch.etf_stock_tail.labels import label_series
from pipeline.autoresearch.etf_stock_tail.stock_features import build_stock_features_row, stock_feature_names


class PanelDropReason(str, enum.Enum):
    INSUFFICIENT_TAIL_LABELS = "INSUFFICIENT_TAIL_LABELS"
    MISSING_SECTOR_MAP = "MISSING_SECTOR_MAP"


@dataclass
class PanelInputs:
    etf_panel: pd.DataFrame                         # cols: date, etf, close
    stock_bars: dict[str, pd.DataFrame]             # ticker → DataFrame[date, close, volume]
    universe: dict[str, list[str]]                  # ISO-date → list of eligible tickers
    sector_map: dict[str, int]                      # ticker → sector_id
    regime_history: pd.DataFrame | None = None      # cols: date, regime — optional


def _sha256_df(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()


def _config_sha256() -> str:
    cfg = {k: getattr(C, k) for k in dir(C) if k.isupper()}
    blob = json.dumps(cfg, default=str, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def assemble_panel(
    inputs: PanelInputs,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    """Build the (ticker × date) panel for ALL dates train_start..C.HOLDOUT_END.

    Returns (panel_df, manifest).

    The panel covers the full date range [train_start, HOLDOUT_END] so it can be
    split into train / val / holdout windows by the caller.
    """
    train_start = pd.Timestamp(train_start)
    train_end = pd.Timestamp(train_end)
    panel_end = pd.Timestamp(C.HOLDOUT_END)

    rows: list[dict] = []
    dropped: dict[str, str] = {}
    ticker_to_id: dict[str, int] = {}

    # Pre-build the ETF feature index for all universe dates to avoid redundant computation.
    # We cache the result per unique date to avoid O(n_tickers × n_dates) re-computation.
    # NOTE: no try/except here — KeyError from build_etf_features_matrix (schema mismatch)
    # must propagate so schema regressions are never silently swallowed.
    etf_cache: dict[pd.Timestamp, pd.Series] = {}

    # Pre-index regime history for O(1) lookup (avoid O(n_regime_rows) linear scan per row).
    rh_by_date: pd.Series | None = None
    if inputs.regime_history is not None:
        rh_by_date = inputs.regime_history.set_index("date")["regime"]

    def _get_etf_row(d: pd.Timestamp) -> pd.Series:
        if d not in etf_cache:
            etf_cache[d] = build_etf_features_matrix(inputs.etf_panel, d)
        return etf_cache[d]

    for ticker, bars in inputs.stock_bars.items():
        if ticker not in inputs.sector_map:
            dropped[ticker] = PanelDropReason.MISSING_SECTOR_MAP.value
            continue

        labels = label_series(bars)
        # labels.index is DatetimeIndex (Timestamps), compatible with pd.Timestamp comparisons.

        # Pre-window screen: require >= MIN_TAIL_EXAMPLES_PER_SIDE in both tail directions
        # within the training window only.
        in_train = (labels.index >= train_start) & (labels.index <= train_end)
        train_labels = labels.values[in_train]
        n_up = int(np.sum(train_labels == C.CLASS_UP))
        n_down = int(np.sum(train_labels == C.CLASS_DOWN))
        if n_up < C.MIN_TAIL_EXAMPLES_PER_SIDE or n_down < C.MIN_TAIL_EXAMPLES_PER_SIDE:
            dropped[ticker] = PanelDropReason.INSUFFICIENT_TAIL_LABELS.value
            continue

        ticker_id = len(ticker_to_id)
        ticker_to_id[ticker] = ticker_id
        sector_id = inputs.sector_map[ticker]

        # NOTE: build_stock_features_row is uncached (per-ticker rolling window math).
        # Production cost: ~200 tickers × ~1100 trading days × 5ms ≈ 18 minutes wall time.
        # Task 9's training orchestrator must allow ≥30 min for panel assembly.
        for d in pd.date_range(train_start, panel_end, freq="D"):
            d_iso = d.strftime("%Y-%m-%d")
            if d_iso not in inputs.universe:
                continue
            if ticker not in inputs.universe[d_iso]:
                continue

            # Get the label — .get() on DatetimeIndex with Timestamp works correctly.
            label = labels.get(d, np.nan)
            if pd.isna(label):
                continue

            etf_row = _get_etf_row(d)
            ctx_row = build_stock_features_row(bars, d, sector_id)

            row: dict = {
                "date": d,
                "ticker": ticker,
                "ticker_id": ticker_id,
                "label": int(label),  # safe: NaN screened above; float label is 0.0/1.0/2.0
            }
            for col in etf_row.index:
                row[col] = etf_row[col]
            for col in ctx_row.index:
                row[col] = ctx_row[col]

            # Regime label join — O(1) via pre-indexed Series (see rh_by_date above).
            row["regime"] = rh_by_date.get(d, "UNKNOWN") if rh_by_date is not None else "UNKNOWN"

            rows.append(row)

    # Define the canonical schema for the panel DataFrame.
    # Pre-declare all columns so the DataFrame has the correct schema even when
    # rows is empty (e.g. all tickers dropped by the pre-screen).
    _meta_cols = ["date", "ticker", "ticker_id", "label", "regime"]
    _all_cols = _meta_cols + list(etf_feature_names()) + list(stock_feature_names())

    if rows:
        panel = pd.DataFrame(rows)
        # Ensure column order matches schema
        panel = panel.reindex(columns=_all_cols)
        # Drop rows where any ETF feature is NaN (e.g. early dates with insufficient history).
        before = len(panel)
        etf_cols = [c for c in panel.columns if c.startswith("etf_")]
        panel = panel.dropna(subset=etf_cols, how="any").reset_index(drop=True)
        n_dropped_etf_nan = before - len(panel)
    else:
        # Return a properly-typed empty DataFrame with the full schema.
        panel = pd.DataFrame(columns=_all_cols)
        n_dropped_etf_nan = 0

    feature_cols = list(etf_feature_names()) + list(stock_feature_names())

    manifest = {
        "etf_panel_sha256": _sha256_df(inputs.etf_panel),
        "config_sha256": _config_sha256(),
        "n_rows": int(len(panel)),
        "n_tickers_kept": int(panel["ticker"].nunique()) if len(panel) else 0,
        "dropped_tickers": dropped,
        "n_dropped_rows_etf_nan": int(n_dropped_etf_nan),
        "ticker_to_id": ticker_to_id,
        "feature_cols": feature_cols,
        "train_start": train_start.strftime("%Y-%m-%d"),
        "train_end": train_end.strftime("%Y-%m-%d"),
    }
    return panel, manifest
