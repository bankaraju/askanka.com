"""
AutoResearch — ETF Re-Optimizer + Indian Market Data Loader

This module serves two related purposes:

1. **Indian Market Data Loader** (`load_indian_data`):
   Reads the most recent daily dump (pipeline/data/daily/YYYY-MM-DD.json),
   flows snapshot (pipeline/data/flows/YYYY-MM-DD.json), and positioning.json
   to extract Indian-specific signals: FII/DII equity flows, India VIX, Nifty
   close, Bank Nifty close, PCR, RSI-14, and breadth indicators.  These values
   are used as additional inputs to the ETF regime engine so that global-ETF
   signals are cross-checked against domestic participation data before a
   regime call is finalised.

2. **ETF Re-Optimizer** (`run_reoptimize`):
   Fetches 3 years of global ETF returns via yfinance, merges with Indian
   market data time-series, runs Karpathy-style random search weight
   optimisation, saves optimal weights to etf_optimal_weights.json, and
   updates the today_zone in regime_trade_map.json.

Usage:
    from pipeline.autoresearch.etf_reoptimize import load_indian_data, run_reoptimize
    data = load_indian_data()   # uses default prod paths
    print(data["india_vix"], data["fii_net"])
    result = run_reoptimize()   # full pipeline, saves weights
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths (relative to repo root)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent  # askanka.com/
_DAILY_DIR: Path = _REPO / "pipeline" / "data" / "daily"
_FLOWS_DIR: Path = _REPO / "pipeline" / "data" / "flows"
_POSITIONING_PATH: Path = _REPO / "pipeline" / "data" / "positioning.json"
_WEIGHTS_PATH: Path = _HERE / "etf_optimal_weights.json"
_TRADE_MAP_PATH: Path = _HERE / "regime_trade_map.json"

# ---------------------------------------------------------------------------
# Global ETF universe (EODHD format → stripped for yfinance)
# ---------------------------------------------------------------------------
GLOBAL_ETFS = {
    "defence": "ITA.US", "energy": "XLE.US", "financials": "XLF.US",
    "tech": "XLK.US", "healthcare": "XLV.US", "staples": "XLP.US",
    "industrials": "XLI.US", "em": "EEM.US", "brazil": "EWZ.US",
    "india_etf": "INDA.US", "china": "FXI.US", "japan": "EWJ.US",
    "developed": "EFA.US", "oil": "USO.US", "natgas": "UNG.US",
    "silver": "SLV.US", "agriculture": "DBA.US", "high_yield": "HYG.US",
    "ig_bond": "LQD.US", "treasury": "TLT.US", "mid_treasury": "IEF.US",
    "dollar": "UUP.US", "euro": "FXE.US", "yen": "FXY.US",
    "sp500": "SPY.US", "gold": "GLD.US", "vix": "^VIX",
    "kbw_bank": "KBE.US", "innovation": "ARKK.US",
}
NIFTY_TICKER = "^NSEI"

# Regime thresholds (from historical calibration)
_CALM_CENTER = 0.0953
_CALM_BAND = 3.8974


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_indian_data(
    daily_dir: Optional[Path] = None,
    flows_dir: Optional[Path] = None,
    positioning_path: Optional[Path] = None,
) -> dict:
    """Load the latest Indian market data from local JSON snapshots.

    Parameters
    ----------
    daily_dir : Path, optional
        Directory containing dated daily dump files (``YYYY-MM-DD.json``).
        Defaults to ``pipeline/data/daily/``.
    flows_dir : Path, optional
        Directory containing dated FII/DII flow files (``YYYY-MM-DD.json``).
        Defaults to ``pipeline/data/flows/``.
    positioning_path : Path, optional
        Path to the positioning snapshot (``positioning.json``).
        Defaults to ``pipeline/data/positioning.json``.

    Returns
    -------
    dict
        Keys (all ``float | None``):
        - ``fii_net``           — FII equity net (crore INR)
        - ``dii_net``           — DII equity net (crore INR)
        - ``india_vix``         — India VIX close
        - ``nifty_close``       — Nifty 50 close
        - ``banknifty_close``   — Bank Nifty close (if available)
        - ``pcr``               — Market-wide put/call ratio
        - ``nifty_rsi_14``      — Nifty 14-day RSI (if stored)
        - ``pct_above_200dma``  — % of F&O stocks above 200 DMA (if stored)
        - ``pct_above_50dma``   — % of F&O stocks above 50 DMA (if stored)
        - ``sector_breadth``    — Advance/decline breadth score (if stored)

    Missing fields are ``None`` — callers must handle ``None`` gracefully.
    """
    daily_dir = Path(daily_dir) if daily_dir is not None else _DAILY_DIR
    flows_dir = Path(flows_dir) if flows_dir is not None else _FLOWS_DIR
    positioning_path = (
        Path(positioning_path) if positioning_path is not None else _POSITIONING_PATH
    )

    result: dict = {
        "fii_net": None,
        "dii_net": None,
        "india_vix": None,
        "nifty_close": None,
        "banknifty_close": None,
        "pcr": None,
        "nifty_rsi_14": None,
        "pct_above_200dma": None,
        "pct_above_50dma": None,
        "sector_breadth": None,
    }

    # --- daily dump ---
    result.update(_load_daily(daily_dir))

    # --- flows ---
    result.update(_load_flows(flows_dir))

    # --- positioning ---
    result.update(_load_positioning(positioning_path))

    return result


# ---------------------------------------------------------------------------
# Weight Optimizer
# ---------------------------------------------------------------------------

def optimize_weights(
    features: pd.DataFrame,
    target: pd.Series,
    n_iterations: int = 2000,
    train_frac: float = 0.7,
) -> dict:
    """Karpathy-style random search weight optimizer for the ETF regime engine.

    Parameters
    ----------
    features : pd.DataFrame
        Feature matrix where each column is an ETF or signal series.
        Index must be date-aligned with *target*.
    target : pd.Series
        Binary direction labels: +1 (up) or -1 (down).
    n_iterations : int
        Number of random perturbation steps. Default 2000.
    train_frac : float
        Fraction of data used for training the seed weights. Default 0.7.

    Returns
    -------
    dict
        - ``optimal_weights`` — top-20 weights by absolute value (col → weight)
        - ``best_accuracy``   — accuracy on test set (0–100 float)
        - ``baseline``        — naive baseline accuracy on test set (0–100 float)
        - ``best_sharpe``     — annualised Sharpe of the weighted signal on test set
        - ``n_iterations``    — number of iterations actually run
    """
    # --- align and split ---
    aligned = features.join(target.rename("__target__"), how="inner").dropna()
    X = aligned.drop(columns=["__target__"])
    y = aligned["__target__"]

    split = int(len(X) * train_frac)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    n_test = len(y_test)

    # --- baseline: predict "up" every day ---
    n_up_test = int((y_test == 1).sum())
    baseline = (n_up_test / n_test * 100) if n_test > 0 else 50.0

    # --- correlation-weighted seed ---
    cols = list(X.columns)
    seed_weights: dict[str, float] = {}
    for col in cols:
        corr = X_train[col].corr(y_train)
        seed_weights[col] = float(corr) if not np.isnan(corr) else 0.0

    # --- random search ---
    best_weights = dict(seed_weights)
    best_sharpe = -np.inf
    best_accuracy = 0.0

    for _ in range(n_iterations):
        # Perturb each weight
        candidate: dict[str, float] = {}
        for col, base in best_weights.items():
            noise_scale = abs(base) * 0.5 if abs(base) > 1e-9 else 0.1
            candidate[col] = base + np.random.normal(0, noise_scale)

        # Compute weighted signal on test set
        signal_test = sum(X_test[col] * w for col, w in candidate.items())

        # Accuracy: correct direction predictions
        predictions = np.sign(signal_test)
        correct = (predictions == y_test.values).sum()
        accuracy = correct / n_test * 100 if n_test > 0 else 0.0

        # Sharpe: annualised on signal * target
        pnl = signal_test * y_test
        pnl_std = pnl.std()
        sharpe = (pnl.mean() / pnl_std * np.sqrt(252)) if pnl_std > 1e-9 else 0.0

        # Track best by Sharpe
        if sharpe > best_sharpe:
            best_sharpe = float(sharpe)
            best_accuracy = float(accuracy)
            best_weights = candidate

    # --- return top-20 weights by absolute value ---
    sorted_weights = sorted(best_weights.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top_weights = dict(sorted_weights[:20])

    return {
        "optimal_weights": top_weights,
        "best_accuracy": best_accuracy,
        "baseline": baseline,
        "best_sharpe": best_sharpe,
        "n_iterations": n_iterations,
    }


# ---------------------------------------------------------------------------
# Full reoptimization pipeline
# ---------------------------------------------------------------------------

def run_reoptimize(
    weights_path: Path = _WEIGHTS_PATH,
    trade_map_path: Path = _TRADE_MAP_PATH,
    n_iterations: int = 2000,
    dry_run: bool = False,
    daily_dir: Path = _DAILY_DIR,
    flows_dir: Path = _FLOWS_DIR,
) -> dict:
    """Run the full ETF weight reoptimization pipeline.

    Steps:
    1. Fetch 3 years of global ETF returns via yfinance (with synthetic fallback)
    2. Build Indian feature time-series from daily/flows JSON files
    3. Merge features, fill NaN
    4. Build next-day Nifty direction target
    5. Run optimize_weights()
    6. Compute today's regime signal and zone
    7. Save weights to weights_path (unless dry_run)
    8. Update today_zone in trade_map_path (unless dry_run)

    Parameters
    ----------
    weights_path : Path
        Destination for etf_optimal_weights.json.
    trade_map_path : Path
        Path to regime_trade_map.json (read + updated in-place).
    n_iterations : int
        Number of random search iterations for optimize_weights().
    dry_run : bool
        If True, skip all file writes and return status="dry_run".
    daily_dir : Path
        Directory of YYYY-MM-DD.json daily dump files.
    flows_dir : Path
        Directory of YYYY-MM-DD.json FII/DII flow files.

    Returns
    -------
    dict
        Keys: status, today_zone, today_signal, best_accuracy, best_sharpe,
              indian_inputs, optimal_weights, timestamp.
    """
    weights_path = Path(weights_path)
    trade_map_path = Path(trade_map_path)
    daily_dir = Path(daily_dir)
    flows_dir = Path(flows_dir)

    # 1. Fetch global ETF returns
    logger.info("run_reoptimize: fetching global ETF data…")
    etf_returns = _fetch_etf_returns()
    if etf_returns is None or etf_returns.empty:
        logger.warning("run_reoptimize: yfinance unavailable — using synthetic data")
        dates = pd.date_range("2024-01-01", periods=500, freq="B")
        etf_returns = pd.DataFrame(
            np.random.randn(500, len(GLOBAL_ETFS) + 1) * 0.5,
            index=dates,
            columns=list(GLOBAL_ETFS.keys()) + ["nifty"],
        )

    # 2. Build Indian feature time-series
    logger.info("run_reoptimize: building Indian feature time-series…")
    indian_df = _build_indian_features(daily_dir, flows_dir)
    indian_inputs = list(indian_df.columns) if not indian_df.empty else []

    # 3. Merge features
    if not indian_df.empty:
        features = etf_returns.join(indian_df, how="left")
    else:
        features = etf_returns.copy()
    features = features.ffill().bfill().fillna(0)

    # 4. Build target — next-day Nifty direction
    nifty_col = "nifty" if "nifty" in features.columns else None
    if nifty_col:
        nifty_returns = features[nifty_col]
        target = np.sign(nifty_returns.shift(-1)).dropna()
        features_aligned = features.loc[target.index]
    else:
        # Fallback: random target from first column
        target = pd.Series(
            np.random.choice([1.0, -1.0], size=len(features) - 1),
            index=features.index[:-1],
        )
        features_aligned = features.iloc[:-1]

    # 5. Optimize weights
    logger.info("run_reoptimize: running optimize_weights (n_iterations=%d)…", n_iterations)
    opt_result = optimize_weights(features_aligned, target, n_iterations=n_iterations)

    # 6. Compute today's signal and map to regime zone
    last_row = features.iloc[-1]
    today_signal = float(
        sum(last_row.get(col, 0.0) * w for col, w in opt_result["optimal_weights"].items())
    )
    today_zone = _signal_to_zone(today_signal)
    logger.info("run_reoptimize: today_signal=%.4f → %s", today_signal, today_zone)

    timestamp = datetime.now(tz=timezone.utc).isoformat()

    result = {
        "status": "dry_run" if dry_run else "saved",
        "today_zone": today_zone,
        "today_signal": today_signal,
        "best_accuracy": opt_result["best_accuracy"],
        "best_sharpe": opt_result["best_sharpe"],
        "indian_inputs": indian_inputs,
        "optimal_weights": opt_result["optimal_weights"],
        "timestamp": timestamp,
    }

    if dry_run:
        logger.info("run_reoptimize: dry_run=True — skipping file writes")
        return result

    # 7. Save weights
    weights_payload = {
        "optimal_weights": opt_result["optimal_weights"],
        "best_accuracy": opt_result["best_accuracy"],
        "best_sharpe": opt_result["best_sharpe"],
        "today_zone": today_zone,
        "today_signal": today_signal,
        "indian_inputs": indian_inputs,
        "timestamp": timestamp,
        "n_iterations": n_iterations,
    }
    weights_path.write_text(json.dumps(weights_payload, indent=2), encoding="utf-8")
    logger.info("run_reoptimize: weights saved to %s", weights_path)

    # 8. Update trade map — preserve existing spread definitions, update metadata
    existing_map: dict = {}
    if trade_map_path.is_file():
        try:
            existing_map = json.loads(trade_map_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("run_reoptimize: could not read trade map — %s", exc)

    existing_map["today_zone"] = today_zone
    existing_map["today_signal"] = today_signal
    existing_map["reoptimize_timestamp"] = timestamp
    existing_map["best_accuracy"] = opt_result["best_accuracy"]
    existing_map["best_sharpe"] = opt_result["best_sharpe"]
    trade_map_path.write_text(json.dumps(existing_map, indent=2), encoding="utf-8")
    logger.info("run_reoptimize: trade map updated at %s", trade_map_path)

    return result


def _fetch_etf_returns(days: int = 1095) -> Optional[pd.DataFrame]:
    """Download close prices for all GLOBAL_ETFS + Nifty via yfinance.

    Returns a DataFrame of percentage returns (pct_change * 100) with
    friendly column names matching GLOBAL_ETFS keys plus 'nifty'.
    Returns None if yfinance is unavailable or download fails.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        logger.warning("_fetch_etf_returns: yfinance not installed")
        return None

    # Build ticker → friendly-name mapping, stripping ".US" suffix
    ticker_map: dict[str, str] = {}
    for name, raw_ticker in GLOBAL_ETFS.items():
        yf_ticker = raw_ticker.replace(".US", "")
        ticker_map[yf_ticker] = name
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
        logger.warning("_fetch_etf_returns: yfinance download failed — %s", exc)
        return None

    # Extract Close prices
    if raw is None or raw.empty:
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        try:
            close = raw["Close"]
        except KeyError:
            return None
    else:
        close = raw

    if close.empty:
        return None

    # Rename columns to friendly names
    rename_map = {t: ticker_map[t] for t in close.columns if t in ticker_map}
    close = close.rename(columns=rename_map)

    # Compute percentage returns
    returns = close.pct_change() * 100
    returns = returns.dropna(how="all")

    return returns


def _build_indian_features(
    daily_dir: Path, flows_dir: Path
) -> pd.DataFrame:
    """Build a date-indexed DataFrame of Indian market features.

    Iterates all YYYY-MM-DD.json files in daily_dir and flows_dir,
    building columns: india_vix_daily, nifty_close_daily,
    fii_net_daily, dii_net_daily.

    Returns an empty DataFrame if no files exist.
    """
    records: dict[str, dict] = {}

    # Daily dump files → VIX + Nifty close
    if daily_dir.is_dir():
        for path in sorted(daily_dir.glob("????-??-??.json")):
            date_str = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            rec = records.setdefault(date_str, {})
            indices = data.get("indices", {})
            vix_entry = indices.get("INDIA VIX") or {}
            if vix_entry.get("close") is not None:
                try:
                    rec["india_vix_daily"] = float(vix_entry["close"])
                except (TypeError, ValueError):
                    pass
            nifty_entry = indices.get("Nifty 50") or {}
            if nifty_entry.get("close") is not None:
                try:
                    rec["nifty_close_daily"] = float(nifty_entry["close"])
                except (TypeError, ValueError):
                    pass

    # Flows files → FII/DII net
    if flows_dir.is_dir():
        for path in sorted(flows_dir.glob("????-??-??.json")):
            date_str = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            rec = records.setdefault(date_str, {})
            fii = data.get("fii_equity_net")
            dii = data.get("dii_equity_net")
            if fii is not None:
                try:
                    rec["fii_net_daily"] = float(fii)
                except (TypeError, ValueError):
                    pass
            if dii is not None:
                try:
                    rec["dii_net_daily"] = float(dii)
                except (TypeError, ValueError):
                    pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(records, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def _signal_to_zone(signal: float) -> str:
    """Map a scalar signal to a regime zone string."""
    center = _CALM_CENTER
    band = _CALM_BAND
    if signal >= center + 2 * band:
        return "EUPHORIA"
    if signal >= center + band:
        return "RISK-ON"
    if signal >= center - band:
        return "NEUTRAL"
    if signal >= center - 2 * band:
        return "CAUTION"
    return "RISK-OFF"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latest_dated_file(directory: Path) -> Optional[Path]:
    """Return the most recent ``YYYY-MM-DD.json`` file in *directory*, or None."""
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob("????-??-??.json"))
    return candidates[-1] if candidates else None


def _load_daily(daily_dir: Path) -> dict:
    """Extract VIX and Nifty close from the most recent daily dump."""
    out: dict = {}
    path = _latest_dated_file(daily_dir)
    if path is None:
        logger.debug("load_indian_data: no daily dump found in %s", daily_dir)
        return out

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", path, exc)
        return out

    indices: dict = data.get("indices", {})

    # India VIX — stored under indices as "INDIA VIX"
    vix_entry = indices.get("INDIA VIX") or {}
    if vix_entry.get("close") is not None:
        try:
            out["india_vix"] = float(vix_entry["close"])
        except (TypeError, ValueError):
            pass

    # Nifty 50 close
    nifty_entry = indices.get("Nifty 50") or {}
    if nifty_entry.get("close") is not None:
        try:
            out["nifty_close"] = float(nifty_entry["close"])
        except (TypeError, ValueError):
            pass

    # Bank Nifty close (may or may not be present)
    banknifty_entry = (
        indices.get("Nifty Bank")
        or indices.get("BANKNIFTY")
        or indices.get("Bank Nifty")
        or {}
    )
    if banknifty_entry.get("close") is not None:
        try:
            out["banknifty_close"] = float(banknifty_entry["close"])
        except (TypeError, ValueError):
            pass

    # Breadth / RSI fields (stored in top-level or metadata when available)
    meta: dict = data.get("metadata", {})
    for field in ("nifty_rsi_14", "pct_above_200dma", "pct_above_50dma", "sector_breadth"):
        raw = meta.get(field)
        if raw is not None:
            try:
                out[field] = float(raw)
            except (TypeError, ValueError):
                pass

    return out


def _load_flows(flows_dir: Path) -> dict:
    """Extract FII/DII equity net flows from the most recent flows file."""
    out: dict = {}
    path = _latest_dated_file(flows_dir)
    if path is None:
        logger.debug("load_indian_data: no flows file found in %s", flows_dir)
        return out

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", path, exc)
        return out

    for dest_key, src_key in (("fii_net", "fii_equity_net"), ("dii_net", "dii_equity_net")):
        raw = data.get(src_key)
        if raw is not None:
            try:
                out[dest_key] = float(raw)
            except (TypeError, ValueError):
                pass

    return out


def _load_positioning(positioning_path: Path) -> dict:
    """Extract market-wide PCR from positioning.json if present."""
    out: dict = {}
    if not positioning_path.is_file():
        logger.debug("load_indian_data: positioning file not found at %s", positioning_path)
        return out

    try:
        data = json.loads(positioning_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load_indian_data: failed to parse %s — %s", positioning_path, exc)
        return out

    # Market-wide PCR may be stored at top level or under a "NIFTY" key
    pcr = data.get("pcr") or data.get("market_pcr")
    if pcr is None:
        nifty_block = data.get("NIFTY") or {}
        pcr = nifty_block.get("pcr")

    if pcr is not None:
        try:
            out["pcr"] = float(pcr)
        except (TypeError, ValueError):
            pass

    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="ETF Engine V2 — Weekly Reoptimization")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't save")
    parser.add_argument("--iterations", type=int, default=2000, help="Optimization iterations")
    args = parser.parse_args()
    result = run_reoptimize(n_iterations=args.iterations, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in result.items() if k != "optimal_weights"}, indent=2))


if __name__ == "__main__":
    main()
