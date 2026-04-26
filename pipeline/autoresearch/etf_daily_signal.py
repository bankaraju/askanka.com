"""
AutoResearch — ETF Daily Signal Computation

Uses stored optimal weights from etf_optimal_weights.json to compute the
current day's regime signal from live ETF price data fetched via yfinance.

The signal is a weighted sum of the latest ETF returns. It is then mapped to
a regime zone (EUPHORIA / RISK-ON / NEUTRAL / CAUTION / RISK-OFF) using the
same thresholds as the weekly reoptimizer. The result is written back into
regime_trade_map.json as today_zone, today_signal, today_direction, and
signal_computed_at.

Designed to run daily as part of the morning pipeline (09:25 IST scan).

Usage:
    from pipeline.autoresearch.etf_daily_signal import compute_daily_signal
    result = compute_daily_signal()
    # or via CLI:
    python -m pipeline.autoresearch.etf_daily_signal
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_WEIGHTS_PATH = _HERE / "etf_optimal_weights.json"
_TRADE_MAP_PATH = _HERE / "regime_trade_map.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_daily_signal(
    weights_path: Path = _WEIGHTS_PATH,
    trade_map_path: Path = _TRADE_MAP_PATH,
) -> dict:
    """Compute today's ETF regime signal using stored optimal weights.

    Parameters
    ----------
    weights_path : Path
        Path to etf_optimal_weights.json (output of run_reoptimize).
    trade_map_path : Path
        Path to regime_trade_map.json — updated in-place on success.

    Returns
    -------
    dict
        On success: {"status": "updated", "today_zone": str,
                     "today_signal": float, "prev_zone": str, "changed": bool}
        On failure: {"status": "error", "reason": str}
    """
    weights_path = Path(weights_path)
    trade_map_path = Path(trade_map_path)

    # 1. Load weights
    if not weights_path.is_file():
        return {"status": "error", "reason": f"weights file not found: {weights_path}"}

    try:
        weights_data = json.loads(weights_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "reason": f"failed to parse weights file: {exc}"}

    optimal_weights: dict = weights_data.get("optimal_weights", {})
    if not optimal_weights:
        return {"status": "error", "reason": "weights file contains no optimal_weights"}

    # Detect the silent-weight-drop bug surfaced by the 2026-04-26 deep-read
    # audit (pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md).
    # The optimizer puts non-zero weights on Indian features (vix, fii_net,
    # dii_net, nifty_close) but _fetch_latest_returns only fetches keys present
    # in GLOBAL_ETFS, so those weights are silently zeroed at decision time.
    # This warns the operator until the architecture is fixed in v3.
    from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS as _GLOBAL_ETFS
    _unfetchable = [k for k in optimal_weights if k not in _GLOBAL_ETFS]
    if _unfetchable:
        _dropped_mass = sum(abs(optimal_weights[k]) for k in _unfetchable)
        _kept_mass = sum(abs(optimal_weights[k]) for k in optimal_weights if k in _GLOBAL_ETFS)
        _frac = _dropped_mass / (_kept_mass + _dropped_mass) if (_kept_mass + _dropped_mass) else 0.0
        logger.warning(
            "compute_daily_signal: SILENT WEIGHT DROP — %d weights have no "
            "yfinance ticker and will be zeroed at signal time: %s "
            "(dropped magnitude %.4f / total %.4f = %.1f%%)",
            len(_unfetchable), _unfetchable,
            _dropped_mass, _kept_mass + _dropped_mass, _frac * 100.0,
        )

    # 2. Fetch latest ETF prices
    logger.info("compute_daily_signal: fetching ETF prices for %d ETFs", len(optimal_weights))
    etf_returns = _fetch_latest_returns(list(optimal_weights.keys()))
    if etf_returns is None:
        return {"status": "error", "reason": "yfinance download failed or no data returned"}

    # 3. Compute composite signal: sum(return * weight) for weighted ETFs.
    # Weights for non-GLOBAL_ETFS keys (Indian features) contribute 0 because
    # they have no entry in etf_returns — the warning above flags this.
    today_signal = 0.0
    for etf_name, weight in optimal_weights.items():
        ret = etf_returns.get(etf_name, 0.0)
        today_signal += float(ret) * float(weight)

    # 4. Map to regime zone
    from pipeline.autoresearch.etf_reoptimize import _signal_to_zone
    today_zone = _signal_to_zone(today_signal)
    today_direction = "UP" if today_signal > 0 else "DOWN"
    logger.info(
        "compute_daily_signal: signal=%.4f → zone=%s direction=%s",
        today_signal, today_zone, today_direction,
    )

    # 5. Load existing trade map and read prev_zone
    existing_map: dict = {}
    if trade_map_path.is_file():
        try:
            existing_map = json.loads(trade_map_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("compute_daily_signal: could not read trade map — %s", exc)

    prev_zone: str = existing_map.get("today_zone", "UNKNOWN")
    changed = prev_zone != today_zone

    # 6. Update trade map
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    existing_map["today_zone"] = today_zone
    existing_map["today_signal"] = today_signal
    existing_map["today_direction"] = today_direction
    existing_map["signal_computed_at"] = timestamp

    try:
        trade_map_path.write_text(json.dumps(existing_map, indent=2), encoding="utf-8")
        logger.info("compute_daily_signal: trade map updated — zone=%s", today_zone)
    except Exception as exc:
        return {"status": "error", "reason": f"failed to write trade map: {exc}"}

    return {
        "status": "updated",
        "today_zone": today_zone,
        "today_signal": today_signal,
        "today_direction": today_direction,
        "prev_zone": prev_zone,
        "changed": changed,
        "signal_computed_at": timestamp,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_latest_returns(etf_names: list[str]) -> Optional[dict]:
    """Fetch the latest day's returns for the given ETF names.

    Maps ETF friendly names (from optimal_weights keys) back to yfinance tickers
    by consulting GLOBAL_ETFS in etf_reoptimize.py. For tickers like "ITA.US",
    strips ".US" suffix. "^VIX" stays as-is.

    Returns a dict of {etf_name: latest_return_pct} or None on failure.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        logger.warning("_fetch_latest_returns: yfinance not installed")
        return None

    from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS

    # Build reverse map: friendly_name → yfinance ticker
    name_to_yf: dict[str, str] = {}
    for name, raw_ticker in GLOBAL_ETFS.items():
        yf_ticker = raw_ticker.replace(".US", "") if ".US" in raw_ticker else raw_ticker
        name_to_yf[name] = yf_ticker

    # Only download tickers we have weights for
    needed_names = [n for n in etf_names if n in name_to_yf]
    if not needed_names:
        logger.warning("_fetch_latest_returns: no recognised ETF names in weights")
        return {}

    yf_tickers = [name_to_yf[n] for n in needed_names]

    try:
        import pandas as pd
        end = pd.Timestamp.now()
        start = end - pd.Timedelta(days=10)
        raw = yf.download(
            yf_tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception as exc:
        logger.warning("_fetch_latest_returns: yfinance download failed — %s", exc)
        return None

    if raw is None or raw.empty:
        return None

    import pandas as pd
    if isinstance(raw.columns, pd.MultiIndex):
        try:
            close = raw["Close"]
        except KeyError:
            return None
    else:
        close = raw

    if close.empty:
        return None

    # Compute pct change and take the last row
    returns = close.pct_change() * 100
    last_row = returns.iloc[-1]

    # Build yf_ticker → friendly_name for reverse lookup
    yf_to_name: dict[str, str] = {v: k for k, v in name_to_yf.items()}

    result: dict[str, float] = {}
    for col in last_row.index:
        col_str = str(col)
        name = yf_to_name.get(col_str)
        if name and not pd.isna(last_row[col]):
            result[name] = float(last_row[col])

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="ETF Engine V2 — Daily Signal Computation")
    parser.add_argument(
        "--weights", type=Path, default=_WEIGHTS_PATH,
        help="Path to etf_optimal_weights.json",
    )
    parser.add_argument(
        "--trade-map", type=Path, default=_TRADE_MAP_PATH,
        help="Path to regime_trade_map.json",
    )
    args = parser.parse_args()
    result = compute_daily_signal(weights_path=args.weights, trade_map_path=args.trade_map)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
