"""In-sample backtest per proposal. Writes proposal_log.jsonl rows.

Task 8 step 2: the DSL-to-returns compiler (`_compile_proposal_returns`)
replaces the zero-returning stub used for plumbing verification. It
evaluates Proposals against the panel:

  * single_long / single_short: per-ticker threshold-fire entries.
    One-position-per-ticker overlap rule.
  * long_short_basket: top_k / bottom_k cross-sectional ranking; build
    a balanced market-neutral basket. One-basket-at-a-time overlap.
  * pair: NotImplementedError (deferred to follow-up).

The scarcity-fallback hurdle (`regime_buy_and_hold_sharpe`) is the
Sharpe of buying `benchmark_ticker` at every regime-tagged date's close
and holding `hold_horizon` trading days — used by run_pilot when fewer
than INCUMBENT_SCARCITY_MIN clean incumbents exist in the regime.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance.slippage_grid import apply_level, LEVELS
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.features import build_feature_matrix


# ---------------------------------------------------------------------------
# Helpers — price/date lookups on the panel.
# ---------------------------------------------------------------------------


def _threshold_fires(op: str, feat: float, thresh: float) -> bool:
    """True iff a single-ticker threshold fires.

    `top_k`/`bottom_k` belong to basket construction — raise ValueError if
    called here so a caller that mixes the two worlds fails loudly.
    """
    if pd.isna(feat):
        return False
    if op == ">":
        return float(feat) > float(thresh)
    if op == "<":
        return float(feat) < float(thresh)
    if op == ">=":
        return float(feat) >= float(thresh)
    if op == "<=":
        return float(feat) <= float(thresh)
    if op in ("top_k", "bottom_k"):
        raise ValueError(
            f"_threshold_fires got {op!r}: top_k / bottom_k are basket ops, "
            "not single-ticker ops"
        )
    raise ValueError(f"_threshold_fires got unknown op: {op!r}")


def _per_ticker_dates(panel: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return {ticker -> sorted ndarray of date64 values} cached for fast
    searchsorted lookups in _nth_trading_day_after.
    """
    out: dict[str, np.ndarray] = {}
    for ticker, g in panel.groupby("ticker", sort=False):
        out[ticker] = np.sort(
            g["date"].to_numpy(dtype="datetime64[ns]", copy=True)
        )
    return out


def _per_ticker_close_map(panel: pd.DataFrame) -> dict[str, dict[np.datetime64, float]]:
    """Return {ticker -> {date -> close}} for O(1) close lookups."""
    out: dict[str, dict[np.datetime64, float]] = {}
    for ticker, g in panel.groupby("ticker", sort=False):
        g_sorted = g.sort_values("date")
        out[ticker] = dict(
            zip(
                g_sorted["date"].to_numpy(dtype="datetime64[ns]"),
                g_sorted["close"].astype(float).to_numpy(),
            )
        )
    return out


def _get_close(close_map: dict[str, dict[np.datetime64, float]],
                ticker: str, date: pd.Timestamp) -> float:
    d64 = np.datetime64(pd.Timestamp(date), "ns")
    return close_map.get(ticker, {}).get(d64, np.nan)


def _nth_trading_day_after(date_arrs: dict[str, np.ndarray],
                            ticker: str, t: pd.Timestamp,
                            n: int) -> pd.Timestamp | None:
    """Returns the n-th trading day strictly after t in ticker's own date
    series. None if fewer than n days remain.

    We use the ticker's date index (not a global one) because different
    tickers may have different trading-day histories in the panel.
    """
    arr = date_arrs.get(ticker)
    if arr is None or len(arr) == 0:
        return None
    t64 = np.datetime64(pd.Timestamp(t), "ns")
    idx = int(np.searchsorted(arr, t64, side="right"))
    target = idx + n - 1
    if target >= len(arr):
        return None
    return pd.Timestamp(arr[target])


def _trade_return(close_map: dict[str, dict[np.datetime64, float]],
                   ticker: str, entry_date: pd.Timestamp,
                   exit_date: pd.Timestamp, sign: int) -> float | None:
    """Close-to-close return with sign applied. None on missing price."""
    entry = _get_close(close_map, ticker, entry_date)
    exit_ = _get_close(close_map, ticker, exit_date)
    if pd.isna(entry) or pd.isna(exit_) or entry == 0:
        return None
    return float(sign) * float((exit_ - entry) / entry)


# ---------------------------------------------------------------------------
# Compiler — the heart of Task 8 step 2.
# ---------------------------------------------------------------------------


def _compile_proposal_returns(
    p: Proposal,
    panel: pd.DataFrame,
    event_dates: pd.DatetimeIndex,
    tickers: list[str],
) -> pd.Series:
    """Return a Series of per-event trade returns (fraction, not percent).

    One entry per executed trade. Events where the threshold didn't fire,
    or where the ticker/basket was already in an open position, are
    skipped.

    Construction-type behaviour:
      single_long  / single_short: iterate event_dates; at each t compute
        the full feature matrix once, then iterate tickers and fire on
        threshold. Overlap rule: one open position per ticker.
      long_short_basket: iterate event_dates; skip until the current
        basket has exited. Build top_k longs + bottom_k shorts
        (threshold_value = k). 50/50 weight across legs.
      pair: NotImplementedError (deferred to follow-up task).
    """
    if p.construction_type == "pair":
        raise NotImplementedError(
            "pair construction deferred to follow-up task"
        )
    if p.construction_type not in ("single_long", "single_short",
                                     "long_short_basket"):
        raise ValueError(
            f"unknown construction_type: {p.construction_type!r}"
        )

    if panel.empty or len(event_dates) == 0:
        return pd.Series([], dtype=float)

    # Pre-compute per-ticker date arrays and close maps once.
    date_arrs = _per_ticker_dates(panel)
    close_map = _per_ticker_close_map(panel)

    # Sort event_dates ascending to enforce causality.
    event_dates = pd.DatetimeIndex(sorted(pd.DatetimeIndex(event_dates).unique()))

    returns: list[float] = []

    if p.construction_type in ("single_long", "single_short"):
        sign = 1 if p.construction_type == "single_long" else -1
        open_positions: dict[str, pd.Timestamp] = {}

        for t in event_dates:
            # Fast-path feature matrix for this eval_date.
            fm = build_feature_matrix(panel, t, tickers)
            if p.feature not in fm.columns:
                # Grammar gives us FEATURES registered; guard anyway.
                continue
            feat_col = fm[p.feature]
            for ticker in tickers:
                if ticker not in feat_col.index:
                    continue
                feat_val = feat_col.loc[ticker]
                # Overlap: skip if this ticker is still holding a trade that
                # exits on or after t.
                exit_prev = open_positions.get(ticker)
                if exit_prev is not None and exit_prev >= t:
                    continue
                if not _threshold_fires(p.threshold_op, feat_val,
                                         p.threshold_value):
                    continue
                exit_date = _nth_trading_day_after(
                    date_arrs, ticker, t, p.hold_horizon,
                )
                if exit_date is None:
                    continue
                ret = _trade_return(close_map, ticker, t, exit_date, sign)
                if ret is None:
                    continue
                returns.append(ret)
                open_positions[ticker] = exit_date

        return pd.Series(returns, dtype=float)

    # long_short_basket
    if p.threshold_op not in ("top_k", "bottom_k"):
        # Basket requires a ranking op — skip otherwise.
        return pd.Series([], dtype=float)

    k = int(p.threshold_value)
    basket_open_until: pd.Timestamp | None = None

    for t in event_dates:
        if basket_open_until is not None and t <= basket_open_until:
            continue
        fm = build_feature_matrix(panel, t, tickers)
        if p.feature not in fm.columns:
            continue
        feat_col = fm[p.feature].dropna()
        if len(feat_col) < 2 * k:
            continue
        ranked = feat_col.sort_values(ascending=False)  # descending
        if p.threshold_op == "top_k":
            longs = list(ranked.index[:k])
            shorts = list(ranked.index[-k:])
        else:  # bottom_k
            longs = list(ranked.index[-k:])
            shorts = list(ranked.index[:k])
        # Pick any basket member's date index for the exit — use the first
        # long, but any member's index works (all are panel tickers).
        exit_date = _nth_trading_day_after(
            date_arrs, longs[0], t, p.hold_horizon,
        )
        if exit_date is None:
            continue
        long_rets = [
            _trade_return(close_map, tk, t, exit_date, +1) for tk in longs
        ]
        short_rets = [
            _trade_return(close_map, tk, t, exit_date, -1) for tk in shorts
        ]
        long_rets = [r for r in long_rets if r is not None]
        short_rets = [r for r in short_rets if r is not None]
        if not long_rets or not short_rets:
            continue
        basket_ret = 0.5 * float(np.mean(long_rets)) + 0.5 * float(np.mean(short_rets))
        returns.append(basket_ret)
        basket_open_until = exit_date

    return pd.Series(returns, dtype=float)


# ---------------------------------------------------------------------------
# Regime buy-and-hold benchmark (scarcity fallback).
# ---------------------------------------------------------------------------


def regime_buy_and_hold_sharpe(
    panel: pd.DataFrame,
    regime: pd.DatetimeIndex,
    benchmark_ticker: str = "NIFTY",
    hold_horizon: int = 1,
) -> float:
    """Net Sharpe of buying `benchmark_ticker` at each regime-tagged date's
    close and holding `hold_horizon` trading days.

    Used by run_pilot as the hurdle when fewer than INCUMBENT_SCARCITY_MIN
    clean incumbents exist in the regime. Applies the slippage_grid S1
    cost model and annualises per hold_horizon (same convention as
    _net_sharpe).

    Returns 0.0 if the benchmark has no data or insufficient future bars
    at every date in `regime`.
    """
    if panel.empty or len(regime) == 0:
        return 0.0
    date_arrs = _per_ticker_dates(panel)
    close_map = _per_ticker_close_map(panel)
    if benchmark_ticker not in date_arrs:
        return 0.0
    regime_sorted = pd.DatetimeIndex(sorted(pd.DatetimeIndex(regime).unique()))
    rets: list[float] = []
    for t in regime_sorted:
        exit_date = _nth_trading_day_after(
            date_arrs, benchmark_ticker, t, hold_horizon,
        )
        if exit_date is None:
            continue
        ret = _trade_return(close_map, benchmark_ticker, t, exit_date, +1)
        if ret is None:
            continue
        rets.append(ret)
    if not rets:
        return 0.0
    # Convert fraction -> percent so the slippage grid's bps cost subtracts
    # correctly (it works in percent-return units).
    event_rets_pct = pd.Series(rets, dtype=float) * 100.0
    return _net_sharpe(event_rets_pct, level="S1", hold_horizon=hold_horizon)


# ---------------------------------------------------------------------------
# Sharpe + persistence — unchanged from Task 2 stub.
# ---------------------------------------------------------------------------


def _net_sharpe(event_rets_pct: pd.Series, level: str = "S1",
                 hold_horizon: int = 1) -> float:
    """Net Sharpe after applying the slippage_grid level, annualized by
    hold_horizon.

    A 5-day hold produces ~sqrt(252/5) × per-event-Sharpe, not sqrt(252).
    `event_rets_pct` is in percent-return units (e.g. 2.0 = 2%); the
    compiler returns fractions and the caller multiplies by 100 before
    passing here.
    """
    if event_rets_pct.empty:
        return 0.0
    if hold_horizon < 1:
        raise ValueError(f"hold_horizon must be >= 1; got {hold_horizon}")
    ledger = pd.DataFrame({"trade_ret_pct": event_rets_pct.values,
                            "ticker": "NA", "direction": 1})
    net = apply_level(ledger, level)["net_ret_pct"].astype(float)
    if net.std() == 0:
        return 0.0
    periods_per_year = 252 / hold_horizon
    return float(net.mean() / net.std() * np.sqrt(periods_per_year))


def run_in_sample(p: Proposal, panel: pd.DataFrame, log_path: Path,
                  incumbent_sharpe: float,
                  event_dates: pd.DatetimeIndex | None = None,
                  tickers: list[str] | None = None) -> dict[str, Any]:
    """Run one proposal end-to-end in-sample and persist the row.

    `event_dates` and `tickers` default to the panel's own unique values
    (excluding pseudo-tickers NIFTY / VIX / REGIME) — passing them
    explicitly is the production path, which is used by run_pilot so the
    event set is governed by the regime filter, not the panel accidentally.

    The result dict is appended to log_path as a single JSONL row before
    being returned.
    """
    _PSEUDO = {"NIFTY", "VIX", "REGIME"}
    if event_dates is None:
        event_dates = pd.DatetimeIndex(
            sorted(panel["date"].unique())
        ) if not panel.empty else pd.DatetimeIndex([])
    if tickers is None:
        tickers = sorted(
            t for t in panel["ticker"].unique() if t not in _PSEUDO
        ) if not panel.empty else []
    event_rets_frac = _compile_proposal_returns(p, panel, event_dates, tickers)
    # _net_sharpe expects percent-return units; convert.
    event_rets_pct = event_rets_frac * 100.0
    net_sharpe = _net_sharpe(event_rets_pct, "S1", hold_horizon=p.hold_horizon)
    gap = net_sharpe - incumbent_sharpe
    result = {
        "net_sharpe_in_sample": round(net_sharpe, 4),
        "n_events_in_sample": int(len(event_rets_frac)),
        "transaction_cost_bps": int(LEVELS["S1"] * 100),
        "incumbent_sharpe": round(incumbent_sharpe, 4),
        "gap_vs_incumbent": round(gap, 4),
        "regime": p.regime,
        "feature": p.feature,
        "threshold_op": p.threshold_op,
        "threshold_value": p.threshold_value,
        "hold_horizon": p.hold_horizon,
        "construction_type": p.construction_type,
        "pair_id": p.pair_id,
    }
    append_proposal_log(log_path, result)
    return result


def append_proposal_log(log_path: Path, entry: dict) -> None:
    """Append a single row to proposal_log.jsonl (append-only)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("timestamp_iso", datetime.now(timezone.utc).isoformat())
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
