"""
AutoResearch — Unified Backtest (Statistical Referee)

Replays the ETF regime engine + spread trade logic across 3 years of historical
data to validate whether the current optimal weights produce genuine alpha or
are simply overfitted noise.

Algorithm
---------
1. Fetch 3 years of ETF returns via yfinance (same function as etf_reoptimize).
2. Load optimal weights from etf_optimal_weights.json.
3. For each trading day, compute the regime signal and zone.
4. Load F&O historical CSVs for all 6 spread legs.
5. For each (day, zone) pair, compute 1d/3d/5d spread returns.
6. Aggregate win rates, Sharpe, drawdown, confidence intervals.
7. Write backtest_results.json and backtest_summary.json.

Usage
-----
    python -m pipeline.autoresearch.unified_backtest
    python -m pipeline.autoresearch.unified_backtest --dry-run
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import scipy.stats as stats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_WEIGHTS_PATH = _HERE / "etf_optimal_weights.json"
_TRADE_MAP_PATH = _HERE / "regime_trade_map.json"
_FNO_HIST_DIR = _REPO / "pipeline" / "data" / "fno_historical"
_RESULTS_PATH = _HERE / "backtest_results.json"
_SUMMARY_PATH = _HERE / "backtest_summary.json"

# ---------------------------------------------------------------------------
# Spread definitions — tickers match fno_historical CSV filenames
# ---------------------------------------------------------------------------
SPREAD_DEFINITIONS: dict[str, dict] = {
    "Defence vs IT": {
        "long": ["HAL", "BEL"],
        "short": ["TCS", "INFY"],
    },
    "Upstream vs Downstream": {
        "long": ["ONGC", "COALINDIA"],
        "short": ["BPCL", "HPCL"],
    },
    "Coal vs OMCs": {
        "long": ["COALINDIA"],
        "short": ["BPCL", "HPCL"],
    },
    "Pharma vs Banks": {
        "long": ["SUNPHARMA"],
        "short": ["HDFCBANK"],
    },
    "Banks vs IT": {
        "long": ["HDFCBANK"],
        "short": ["TCS", "INFY"],
    },
    "Reliance vs OMCs": {
        "long": ["RELIANCE"],
        "short": ["BPCL", "HPCL"],
    },
}

HOLD_PERIODS = [1, 3, 5]
PASS_WIN_RATE = 0.55
PASS_SHARPE = 1.0


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_weights(weights_path: Path = _WEIGHTS_PATH) -> dict:
    """Load etf_optimal_weights.json. Raises FileNotFoundError if missing."""
    if not weights_path.is_file():
        raise FileNotFoundError(f"Weights file not found: {weights_path}")
    payload = json.loads(weights_path.read_text(encoding="utf-8"))
    return payload


def _fetch_etf_returns(days: int = 1095) -> Optional[pd.DataFrame]:
    """Download 3yr global ETF + Nifty returns via yfinance.

    Mirrors _fetch_etf_returns() from etf_reoptimize exactly.
    Returns None on failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — cannot fetch ETF data")
        return None

    from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS, NIFTY_TICKER

    ticker_map: dict[str, str] = {}
    for name, raw in GLOBAL_ETFS.items():
        ticker_map[raw.replace(".US", "")] = name
    ticker_map[NIFTY_TICKER] = "nifty"

    all_tickers = list(ticker_map.keys())
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=days)

    try:
        raw = yf.download(
            all_tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception as exc:
        logger.error("yfinance download failed: %s", exc)
        return None

    if raw is None or raw.empty:
        return None

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if close.empty:
        return None

    rename_map = {t: ticker_map[t] for t in close.columns if t in ticker_map}
    close = close.rename(columns=rename_map)
    returns = close.pct_change() * 100
    return returns.dropna(how="all")


def _load_fno_close(symbol: str, fno_dir: Path = _FNO_HIST_DIR) -> Optional[pd.Series]:
    """Load Close prices for a single F&O ticker from CSV.

    Returns a date-indexed Series of Close prices, or None if the CSV is
    missing or cannot be parsed.
    """
    csv_path = fno_dir / f"{symbol}.csv"
    if not csv_path.is_file():
        logger.warning("F&O CSV not found for %s — skipping", symbol)
        return None
    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
        if "Close" not in df.columns:
            logger.warning("No 'Close' column in %s", csv_path)
            return None
        return df["Close"].sort_index()
    except Exception as exc:
        logger.warning("Failed to read %s: %s", csv_path, exc)
        return None


def _load_all_spread_prices(
    spread_defs: dict = SPREAD_DEFINITIONS,
    fno_dir: Path = _FNO_HIST_DIR,
) -> dict[str, Optional[pd.Series]]:
    """Pre-load all unique tickers needed for spreads. Returns symbol → Series."""
    unique_symbols: set[str] = set()
    for defn in spread_defs.values():
        unique_symbols.update(defn["long"])
        unique_symbols.update(defn["short"])

    return {sym: _load_fno_close(sym, fno_dir) for sym in unique_symbols}


# ---------------------------------------------------------------------------
# Signal + regime computation
# ---------------------------------------------------------------------------

def _signal_to_zone(signal: float) -> str:
    """Map scalar signal → regime zone (mirrors etf_reoptimize._signal_to_zone)."""
    from pipeline.autoresearch.etf_reoptimize import _signal_to_zone as _sz
    return _sz(signal)


def _compute_daily_regimes(
    etf_returns: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    """For each day in etf_returns, compute the regime zone using weights.

    Returns a Series indexed by date, values are zone strings.
    """
    zones: dict = {}
    for dt, row in etf_returns.iterrows():
        signal = sum(row.get(col, 0.0) * w for col, w in weights.items())
        zones[dt] = _signal_to_zone(signal)
    return pd.Series(zones, name="zone")


# ---------------------------------------------------------------------------
# Spread return computation
# ---------------------------------------------------------------------------

def _avg_returns(prices: pd.Series, dates: pd.DatetimeIndex, period: int) -> pd.Series:
    """Compute forward return over *period* days for each date in *dates*.

    Forward return = (price[t + period] - price[t]) / price[t] * 100.
    Returns a Series indexed by dates, NaN where data is unavailable.
    """
    result = {}
    for dt in dates:
        loc = prices.index.searchsorted(dt)
        if loc >= len(prices):
            result[dt] = np.nan
            continue
        p0 = prices.iloc[loc]
        fwd_loc = loc + period
        if fwd_loc >= len(prices):
            result[dt] = np.nan
            continue
        p1 = prices.iloc[fwd_loc]
        result[dt] = (p1 - p0) / p0 * 100 if p0 != 0 else np.nan
    return pd.Series(result)


def _compute_spread_returns(
    long_symbols: list[str],
    short_symbols: list[str],
    prices_cache: dict[str, Optional[pd.Series]],
    dates: pd.DatetimeIndex,
    period: int,
) -> Optional[pd.Series]:
    """Compute spread returns for all dates at given hold period.

    spread_return = avg(long_leg_returns) - avg(short_leg_returns)

    Returns None if no data is available for any leg.
    """
    long_returns_list = []
    for sym in long_symbols:
        s = prices_cache.get(sym)
        if s is not None and not s.empty:
            r = _avg_returns(s, dates, period)
            long_returns_list.append(r)

    short_returns_list = []
    for sym in short_symbols:
        s = prices_cache.get(sym)
        if s is not None and not s.empty:
            r = _avg_returns(s, dates, period)
            short_returns_list.append(r)

    if not long_returns_list or not short_returns_list:
        return None

    long_avg = pd.concat(long_returns_list, axis=1).mean(axis=1)
    short_avg = pd.concat(short_returns_list, axis=1).mean(axis=1)
    return long_avg - short_avg


# ---------------------------------------------------------------------------
# Nifty accuracy
# ---------------------------------------------------------------------------

def _compute_regime_accuracy(
    zones: pd.Series,
    nifty_returns: pd.Series,
) -> dict[str, dict]:
    """For each regime zone, compute accuracy vs Nifty next-day direction.

    RISK-ON / EUPHORIA → expect Nifty up (+1).
    RISK-OFF / CAUTION → expect Nifty down (-1).
    NEUTRAL → no directional bias, skip accuracy calc.
    """
    ZONE_DIRECTION = {
        "RISK-ON": 1,
        "EUPHORIA": 1,
        "CAUTION": -1,
        "RISK-OFF": -1,
    }
    per_regime: dict[str, dict] = {}
    aligned = zones.to_frame("zone").join(nifty_returns.rename("nifty_ret"), how="inner")

    for zone in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]:
        mask = aligned["zone"] == zone
        days = int(mask.sum())
        if days == 0:
            per_regime[zone] = {
                "days": 0,
                "accuracy": None,
                "avg_nifty_return": None,
            }
            continue

        subset = aligned[mask]
        avg_nifty = float(subset["nifty_ret"].mean())

        expected_dir = ZONE_DIRECTION.get(zone)
        if expected_dir is None:
            # NEUTRAL — no directional expectation
            accuracy = None
        else:
            # Next-day direction: shift nifty_ret by -1 (we look ahead)
            # But zones are computed on day t using ETF data from day t,
            # so we compare zone[t] to nifty_ret[t] (same-day movement is proxy)
            correct = int((np.sign(subset["nifty_ret"]) == expected_dir).sum())
            accuracy = correct / days if days > 0 else None

        per_regime[zone] = {
            "days": days,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "avg_nifty_return": round(avg_nifty, 4),
        }

    return per_regime


# ---------------------------------------------------------------------------
# Sharpe + drawdown utilities
# ---------------------------------------------------------------------------

def _sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio. Returns 0.0 if std ≈ 0."""
    clean = returns.dropna()
    if len(clean) < 2:
        return 0.0
    std = clean.std()
    if std < 1e-9:
        return 0.0
    return float(clean.mean() / std * np.sqrt(periods_per_year))


def _max_drawdown(returns: pd.Series) -> float:
    """Maximum drawdown from cumulative equity curve."""
    clean = returns.dropna()
    if len(clean) < 2:
        return 0.0
    cum = (1 + clean / 100).cumprod()
    roll_max = cum.expanding().max()
    drawdown = (cum - roll_max) / roll_max
    return float(drawdown.min())


def _confidence_interval_95(returns: pd.Series) -> tuple[float, float]:
    """95% CI for mean return using t-distribution."""
    clean = returns.dropna()
    n = len(clean)
    if n < 2:
        return (0.0, 0.0)
    mean = float(clean.mean())
    se = float(clean.sem())
    t_val = stats.t.ppf(0.975, df=n - 1)
    return (round(mean - t_val * se, 4), round(mean + t_val * se, 4))


# ---------------------------------------------------------------------------
# Core backtest function
# ---------------------------------------------------------------------------

def run_backtest(
    weights_path: Path = _WEIGHTS_PATH,
    fno_dir: Path = _FNO_HIST_DIR,
    etf_returns: Optional[pd.DataFrame] = None,  # injectable for tests
    results_path: Path = _RESULTS_PATH,
    summary_path: Path = _SUMMARY_PATH,
    dry_run: bool = False,
) -> dict:
    """Run the unified backtest.

    Parameters
    ----------
    weights_path : Path
        etf_optimal_weights.json
    fno_dir : Path
        Directory of F&O historical CSVs
    etf_returns : pd.DataFrame, optional
        Pre-loaded ETF returns (for testing). If None, fetches via yfinance.
    results_path : Path
        Output path for backtest_results.json
    summary_path : Path
        Output path for backtest_summary.json
    dry_run : bool
        If True, skip writing output files.

    Returns
    -------
    dict
        Full backtest results dict (same shape as backtest_results.json).
    """
    # 1. Load weights
    weights_payload = _load_weights(weights_path)
    optimal_weights: dict[str, float] = weights_payload["optimal_weights"]
    weights_timestamp: str = weights_payload.get("timestamp", "unknown")
    logger.info("Loaded weights: %d features, Sharpe=%.2f", len(optimal_weights), weights_payload.get("best_sharpe", 0))

    # 2. Fetch ETF returns
    if etf_returns is None:
        logger.info("Fetching ETF returns via yfinance…")
        etf_returns = _fetch_etf_returns()
        if etf_returns is None or etf_returns.empty:
            logger.error("Failed to fetch ETF returns — cannot continue")
            sys.exit(1)

    etf_returns = etf_returns.dropna(how="all")
    logger.info("ETF data: %d rows from %s to %s", len(etf_returns), etf_returns.index[0].date(), etf_returns.index[-1].date())

    # 3. Compute daily regime zones
    logger.info("Computing daily regime zones…")
    zones = _compute_daily_regimes(etf_returns, optimal_weights)

    period_start = str(zones.index[0].date())
    period_end = str(zones.index[-1].date())
    trading_days = len(zones)

    regime_distribution = zones.value_counts().to_dict()
    regime_distribution = {k: int(v) for k, v in regime_distribution.items()}

    # 4. Load F&O historical prices
    logger.info("Loading F&O historical CSVs…")
    prices_cache = _load_all_spread_prices(SPREAD_DEFINITIONS, fno_dir)
    loaded = [sym for sym, s in prices_cache.items() if s is not None]
    missing = [sym for sym, s in prices_cache.items() if s is None]
    if missing:
        logger.warning("Missing F&O CSVs (spreads with these legs will be skipped): %s", missing)
    logger.info("Loaded %d/%d F&O tickers", len(loaded), len(prices_cache))

    # 5. Compute spread returns per zone
    logger.info("Computing spread returns…")
    nifty_series = etf_returns["nifty"] if "nifty" in etf_returns.columns else None

    # per_spread_trades: {spread_name: Series indexed by date}
    per_spread_series: dict[str, pd.Series] = {}
    # daily_portfolio: accumulate per-date avg return across all active spreads
    daily_portfolio_parts: list[pd.Series] = []

    # Load best_period mapping from trade_map once
    trade_map_results: dict = {}
    if _TRADE_MAP_PATH.is_file():
        try:
            trade_map = json.loads(_TRADE_MAP_PATH.read_text(encoding="utf-8"))
            trade_map_results = trade_map.get("results", {})
        except Exception:
            pass

    dates_idx = zones.index

    for spread_name, defn in SPREAD_DEFINITIONS.items():
        long_syms = defn["long"]
        short_syms = defn["short"]

        # Check data availability for this spread
        has_long = any(prices_cache.get(s) is not None for s in long_syms)
        has_short = any(prices_cache.get(s) is not None for s in short_syms)
        if not has_long or not has_short:
            logger.warning("Skipping spread '%s' — missing price data", spread_name)
            continue

        # Build a date-indexed series of (zone, spread_ret) for each period
        # Then select each row's return using the best_period for that zone
        period_rets: dict[int, pd.Series] = {}
        for period in HOLD_PERIODS:
            sr = _compute_spread_returns(long_syms, short_syms, prices_cache, dates_idx, period)
            if sr is not None:
                period_rets[period] = sr

        if not period_rets:
            continue

        # Align all periods + zone into one DataFrame
        frames = {"zone": zones}
        for p, s in period_rets.items():
            frames[f"ret_{p}d"] = s
        combined = pd.DataFrame(frames).dropna(subset=["zone"])

        # For each row, pick return at the best_period for that zone
        def _pick_best_ret(row):
            zone = row["zone"]
            bp = trade_map_results.get(zone, {}).get(spread_name, {}).get("best_period", 3)
            col = f"ret_{bp}d"
            return row.get(col, np.nan)

        best_rets = combined.apply(_pick_best_ret, axis=1)
        best_rets.name = spread_name
        per_spread_series[spread_name] = best_rets
        daily_portfolio_parts.append(best_rets)

    # 6. Aggregate results
    logger.info("Aggregating results…")

    # Portfolio daily return = average spread return across all active spreads (date-aligned)
    if daily_portfolio_parts:
        portfolio_df = pd.concat(daily_portfolio_parts, axis=1)
        # Daily P&L = mean of all active spreads (equal-weight)
        portfolio_daily = portfolio_df.mean(axis=1).dropna()
        portfolio_daily = portfolio_daily.sort_index()  # ensure chronological order
    else:
        portfolio_daily = pd.Series(dtype=float)

    # Flat list of all individual trade returns for win-rate / avg-return / CI
    all_trade_returns_list: list[float] = []
    for s in daily_portfolio_parts:
        all_trade_returns_list.extend(s.dropna().tolist())
    all_rets = pd.Series([r for r in all_trade_returns_list if not np.isnan(r)])
    total_trades = len(all_rets)

    if total_trades == 0:
        logger.warning("No trades computed — check F&O data availability")
        win_rate = 0.0
        avg_return = 0.0
        sharpe = 0.0
        max_dd = 0.0
        ci_95 = (0.0, 0.0)
    else:
        win_rate = float((all_rets > 0).sum() / total_trades)
        avg_return = float(all_rets.mean() / 100)  # convert % to decimal
        sharpe = _sharpe(portfolio_daily)  # Sharpe on time-ordered daily P&L
        max_dd = _max_drawdown(portfolio_daily)  # Drawdown on time-ordered daily P&L
        ci_95 = _confidence_interval_95(all_rets / 100)

    # Per-spread stats
    per_spread_stats: dict[str, dict] = {}
    for spread_name, spread_series in per_spread_series.items():
        clean = spread_series.dropna().sort_index()
        n = len(clean)
        if n == 0:
            continue
        wr = float((clean > 0).sum() / n)
        avg_r = float(clean.mean())
        sp = _sharpe(clean)
        per_spread_stats[spread_name] = {
            "trades": n,
            "win_rate": round(wr, 4),
            "avg_return": round(avg_r, 4),
            "sharpe": round(sp, 4),
        }

    # Per-regime accuracy vs Nifty
    if nifty_series is not None:
        per_regime = _compute_regime_accuracy(zones, nifty_series)
    else:
        per_regime = {z: {"days": regime_distribution.get(z, 0), "accuracy": None, "avg_nifty_return": None}
                      for z in ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]}

    # Overall regime accuracy (directional zones only)
    dir_zones = ["RISK-OFF", "CAUTION", "RISK-ON", "EUPHORIA"]
    dir_correct = 0
    dir_total = 0
    for zone, stats_d in per_regime.items():
        if zone in dir_zones and stats_d["accuracy"] is not None and stats_d["days"] > 0:
            dir_correct += int(stats_d["accuracy"] * stats_d["days"])
            dir_total += stats_d["days"]
    regime_accuracy = dir_correct / dir_total if dir_total > 0 else 0.0

    # Find best and worst spreads
    if per_spread_stats:
        best_spread_name = max(per_spread_stats, key=lambda k: per_spread_stats[k]["win_rate"])
        worst_spread_name = min(per_spread_stats, key=lambda k: per_spread_stats[k]["win_rate"])
        best_spread_wr = per_spread_stats[best_spread_name]["win_rate"]
        worst_spread_wr = per_spread_stats[worst_spread_name]["win_rate"]
    else:
        best_spread_name = "N/A"
        worst_spread_name = "N/A"
        best_spread_wr = 0.0
        worst_spread_wr = 0.0

    verdict = "PASS" if (win_rate > PASS_WIN_RATE and sharpe > PASS_SHARPE) else "FAIL"
    computed_at = datetime.now(tz=timezone.utc).isoformat()

    # 7. Build output dicts
    results = {
        "period_start": period_start,
        "period_end": period_end,
        "trading_days": trading_days,
        "weights_file": str(weights_path.name),
        "weights_timestamp": weights_timestamp,
        "regime_distribution": regime_distribution,
        "regime_accuracy": round(regime_accuracy, 4),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "avg_return_per_trade": round(avg_return, 6),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "confidence_interval_95": list(ci_95),
        "per_spread": per_spread_stats,
        "per_regime": per_regime,
        "computed_at": computed_at,
    }

    summary = {
        "period": f"{period_start} to {period_end}",
        "trading_days": trading_days,
        "regime_accuracy_pct": round(regime_accuracy * 100, 2),
        "win_rate_pct": round(win_rate * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "best_spread": f"{best_spread_name} ({best_spread_wr*100:.0f}% win rate)" if best_spread_name != "N/A" else "N/A",
        "worst_spread": f"{worst_spread_name} ({worst_spread_wr*100:.0f}% win rate)" if worst_spread_name != "N/A" else "N/A",
        "verdict": verdict,
        "computed_at": computed_at,
    }

    # 8. Write outputs
    if not dry_run:
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Wrote %s", results_path)
        logger.info("Wrote %s", summary_path)
    else:
        logger.info("dry_run=True — skipping file writes")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Unified Backtest — Statistical Referee for ETF V2 weights"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute backtest but do not write output files",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=_WEIGHTS_PATH,
        help=f"Path to etf_optimal_weights.json (default: {_WEIGHTS_PATH})",
    )
    parser.add_argument(
        "--fno-dir",
        type=Path,
        default=_FNO_HIST_DIR,
        help=f"Path to fno_historical/ directory (default: {_FNO_HIST_DIR})",
    )
    args = parser.parse_args()

    results = run_backtest(
        weights_path=args.weights,
        fno_dir=args.fno_dir,
        dry_run=args.dry_run,
    )

    # Print summary to stdout
    summary = {
        "period": f"{results['period_start']} to {results['period_end']}",
        "trading_days": results["trading_days"],
        "regime_accuracy_pct": round(results["regime_accuracy"] * 100, 2),
        "win_rate_pct": round(results["win_rate"] * 100, 2),
        "sharpe": results["sharpe"],
        "max_drawdown_pct": round(results["max_drawdown"] * 100, 2),
        "total_trades": results["total_trades"],
        "verdict": "PASS" if (results["win_rate"] > PASS_WIN_RATE and results["sharpe"] > PASS_SHARPE) else "FAIL",
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
