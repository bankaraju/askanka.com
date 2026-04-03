"""
Anka Research Pipeline — Regime & Correlation Break Engine (ARCBE)

Five numerical methods for detecting broken correlations and emerging regime dynamics:
  1. Rolling beta shift detector
  2. Spread Z-score with persistence test
  3. Cross-asset linkage scanner
  4. Intra-sector dispersion monitor
  5. Beta decay detector (protects existing war signals)
  + Regime score (6 inputs → -6 to +6)

All public functions return plain dicts/lists — no side effects.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.arcbe")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"

# Drivers: internal name → fetch function key
DRIVER_NAMES = ["brent", "usdinr", "vix", "nifty", "us10yr"]


def fetch_price_matrix(tickers: list[str], days: int = 400) -> pd.DataFrame:
    """Fetch daily close prices for *tickers* and return a DataFrame of daily returns.

    Columns = tickers, index = date strings (YYYY-MM-DD), values = pct daily return.
    Tickers with fewer than 60 trading days of data are dropped and logged.
    Uses kite_client.fetch_historical (Kite primary, EODHD fallback).
    """
    from kite_client import fetch_historical

    closes: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            candles = fetch_historical(ticker, interval="day", days=days)
            if len(candles) < 60:
                log.warning("ARCBE: %s has only %d candles — dropping", ticker, len(candles))
                continue
            s = pd.Series(
                {c["date"]: float(c["close"]) for c in candles},
                name=ticker,
            )
            closes[ticker] = s
        except Exception as exc:
            log.warning("ARCBE: failed to fetch %s: %s", ticker, exc)

    if not closes:
        return pd.DataFrame()

    price_df = pd.DataFrame(closes)
    price_df.index = pd.to_datetime(price_df.index)
    price_df.sort_index(inplace=True)
    return price_df.pct_change().dropna(how="all")


def fetch_driver_matrix(days: int = 400) -> pd.DataFrame:
    """Fetch daily returns for 5 macro drivers.

    Returns DataFrame with columns: brent, usdinr, vix, nifty, us10yr.
    Missing drivers are filled with NaN (methods handle sparse drivers gracefully).
    """
    from kite_client import fetch_historical
    from eodhd_client import fetch_eod_series

    series: dict[str, pd.Series] = {}

    # Brent crude — MCX CRUDEOIL via Kite (primary), EODHD BZ.COMM fallback
    try:
        candles = fetch_historical("CRUDEOIL", interval="day", days=days)
        if candles:
            series["brent"] = pd.Series(
                {c["date"]: float(c["close"]) for c in candles}
            )
        else:
            raise ValueError("empty")
    except Exception:
        try:
            rows = fetch_eod_series("BZ.COMM", days=days)
            if rows:
                series["brent"] = pd.Series(
                    {r["date"]: float(r["close"]) for r in rows}
                )
        except Exception as exc:
            log.warning("ARCBE: brent fetch failed: %s", exc)

    # USD/INR — EODHD USDINR.FOREX
    try:
        rows = fetch_eod_series("USDINR.FOREX", days=days)
        if rows:
            series["usdinr"] = pd.Series(
                {r["date"]: float(r["close"]) for r in rows}
            )
    except Exception as exc:
        log.warning("ARCBE: usdinr fetch failed: %s", exc)

    # India VIX — Kite
    try:
        candles = fetch_historical("INDIA VIX", interval="day", days=days)
        if candles:
            series["vix"] = pd.Series(
                {c["date"]: float(c["close"]) for c in candles}
            )
    except Exception as exc:
        log.warning("ARCBE: india vix fetch failed: %s", exc)

    # Nifty 50 — Kite
    try:
        candles = fetch_historical("NIFTY 50", interval="day", days=days)
        if candles:
            series["nifty"] = pd.Series(
                {c["date"]: float(c["close"]) for c in candles}
            )
    except Exception as exc:
        log.warning("ARCBE: nifty fetch failed: %s", exc)

    # US 10yr yield — EODHD (TNX.INDX); fall back to yfinance ^TNX
    try:
        rows = fetch_eod_series("TNX.INDX", days=days)
        if rows:
            series["us10yr"] = pd.Series(
                {r["date"]: float(r["close"]) for r in rows}
            )
        else:
            raise ValueError("empty")
    except Exception:
        try:
            import yfinance as yf
            df = yf.download("^TNX", period="2y", interval="1d", progress=False)
            if not df.empty:
                series["us10yr"] = df["Close"].squeeze()
                series["us10yr"].index = series["us10yr"].index.strftime("%Y-%m-%d")
        except Exception as exc2:
            log.warning("ARCBE: us10yr fetch failed: %s", exc2)

    if not series:
        return pd.DataFrame(columns=DRIVER_NAMES)

    driver_df = pd.DataFrame(series)
    driver_df.index = pd.to_datetime(driver_df.index)
    driver_df.sort_index(inplace=True)
    return driver_df.pct_change().dropna(how="all")


# ---------------------------------------------------------------------------
# Method 1: Rolling Beta Shift Detector
# ---------------------------------------------------------------------------

def rolling_beta(stock: pd.Series, driver: pd.Series, window: int) -> float:
    """Compute OLS beta of stock returns on driver returns over last *window* observations.
    Returns NaN if insufficient data or zero variance in driver."""
    aligned = pd.concat([stock, driver], axis=1).dropna()
    if len(aligned) < window:
        return float("nan")
    x = aligned.iloc[-window:, 1].values
    y = aligned.iloc[-window:, 0].values
    var_x = np.var(x)
    if var_x < 1e-10:
        return float("nan")
    return float(np.cov(y, x)[0, 1] / var_x)


def beta_shift_detector(
    price_df: pd.DataFrame,
    driver_df: pd.DataFrame,
    window_short: int = 20,
    window_long: int = 90,
    watch_threshold: float = 0.5,
    alert_threshold: float = 1.0,
) -> list[dict]:
    """Method 1: Detect stocks developing new sensitivity to macro drivers.

    Returns list of dicts with keys:
      ticker, driver, beta_20d, beta_90d, beta_shift, signal
    signal ∈ {"ALERT", "WATCH", "INVERSION", "NORMAL"}
    Only returns rows where signal != "NORMAL".
    """
    results = []
    for ticker in price_df.columns:
        stock = price_df[ticker].dropna()
        for driver_name in driver_df.columns:
            driver = driver_df[driver_name].dropna()
            b20 = rolling_beta(stock, driver, window_short)
            b90 = rolling_beta(stock, driver, window_long)
            if np.isnan(b20) or np.isnan(b90):
                continue
            denom = max(abs(b90), 0.01)
            shift = (b20 - b90) / denom

            if (b20 > 0) != (b90 > 0) and abs(b90) > 0.05:
                signal = "INVERSION"
            elif abs(shift) >= alert_threshold:
                signal = "ALERT"
            elif abs(shift) >= watch_threshold:
                signal = "WATCH"
            else:
                signal = "NORMAL"

            if signal != "NORMAL":
                results.append({
                    "ticker": ticker,
                    "driver": driver_name,
                    "beta_20d": round(b20, 4),
                    "beta_90d": round(b90, 4),
                    "beta_shift": round(shift, 4),
                    "signal": signal,
                })

    return sorted(results, key=lambda r: abs(r["beta_shift"]), reverse=True)


# ---------------------------------------------------------------------------
# Method 2: Spread Z-Score with Persistence Test
# ---------------------------------------------------------------------------

def spread_zscore(
    price_df: pd.DataFrame,
    spread: dict,
    window_short: int = 30,
    window_long: int = 90,
    z_threshold: float = 2.0,
    persistence_threshold: int = 3,
) -> dict:
    """Method 2: Compute Z-score for a spread and test for regime shift vs mean reversion.

    spread must have keys: name (str), long (list[str]), short (list[str])

    Returns dict with keys:
      spread_name, z_score, persistence, direction, signal
    signal ∈ {"REGIME_SHIFT", "MEAN_REVERT", "EXIT", "NEUTRAL"}
    direction: +1 = long leg outperforming, -1 = short leg outperforming, 0 = neutral
    """
    name = spread["name"]
    long_tickers = [t for t in spread["long"] if t in price_df.columns]
    short_tickers = [t for t in spread["short"] if t in price_df.columns]

    if not long_tickers or not short_tickers:
        return {"spread_name": name, "z_score": 0.0, "persistence": 0,
                "direction": 0, "signal": "NEUTRAL", "error": "missing tickers"}

    # Cumulative spread = mean cumulative return of long leg minus short leg
    long_cum = price_df[long_tickers].add(1).cumprod().mean(axis=1)
    short_cum = price_df[short_tickers].add(1).cumprod().mean(axis=1)
    spread_series = (long_cum - short_cum).dropna()

    if len(spread_series) < window_long:
        return {"spread_name": name, "z_score": 0.0, "persistence": 0,
                "direction": 0, "signal": "NEUTRAL", "error": "insufficient history"}

    rolling_mean = spread_series.rolling(window_long).mean()
    rolling_std  = spread_series.rolling(window_long).std()

    current_val  = spread_series.iloc[-1]
    current_mean = rolling_mean.iloc[-1]
    current_std  = rolling_std.iloc[-1]

    if current_std < 1e-8:
        return {"spread_name": name, "z_score": 0.0, "persistence": 0,
                "direction": 0, "signal": "NEUTRAL", "error": "zero std"}

    z = (current_val - current_mean) / current_std

    # Count consecutive days above threshold
    z_series = (spread_series - rolling_mean) / rolling_std
    above = (z_series.abs() > z_threshold)
    persistence = 0
    for val in reversed(above.values):
        if val:
            persistence += 1
        else:
            break

    direction = 1 if z > 0 else (-1 if z < 0 else 0)

    # Determine signal
    prev_z = z_series.iloc[-2] if len(z_series) > 1 else z
    crossed_zero = (prev_z > 0) != (z > 0) and abs(prev_z) > z_threshold * 0.5

    if crossed_zero:
        signal = "EXIT"
    elif abs(z) >= z_threshold and persistence >= persistence_threshold:
        signal = "REGIME_SHIFT"
    elif abs(z) >= z_threshold and persistence == 1:
        signal = "MEAN_REVERT"
    else:
        signal = "NEUTRAL"

    return {
        "spread_name": name,
        "z_score": round(float(z), 3),
        "persistence": persistence,
        "direction": direction,
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# Method 3: Cross-Asset Linkage Scanner (bottom-up data discovery)
# ---------------------------------------------------------------------------

def linkage_scanner(
    price_df: pd.DataFrame,
    driver_df: pd.DataFrame,
    window_short: int = 20,
    window_long: int = 90,
    delta_threshold: float = 0.25,
    top_n: int = 10,
) -> list[dict]:
    """Method 3: Scan ALL stocks × ALL drivers for abnormal correlation shifts.

    Finds relationships that emerged from the data without being asked for.
    Returns top_n results sorted by |delta| descending.

    Each result: ticker, driver, corr_20d, corr_90d, delta, rank
    """
    results = []
    for ticker in price_df.columns:
        stock = price_df[ticker].dropna()
        for driver_name in driver_df.columns:
            driver = driver_df[driver_name].dropna()
            aligned = pd.concat([stock, driver], axis=1).dropna()
            if len(aligned) < window_long:
                continue
            corr_20d = float(aligned.iloc[-window_short:].corr().iloc[0, 1])
            corr_90d = float(aligned.iloc[-window_long:].corr().iloc[0, 1])
            if np.isnan(corr_20d) or np.isnan(corr_90d):
                continue
            delta = corr_20d - corr_90d
            if abs(delta) >= delta_threshold:
                results.append({
                    "ticker": ticker,
                    "driver": driver_name,
                    "corr_20d": round(corr_20d, 3),
                    "corr_90d": round(corr_90d, 3),
                    "delta": round(delta, 3),
                })

    results.sort(key=lambda r: abs(r["delta"]), reverse=True)
    for i, r in enumerate(results[:top_n]):
        r["rank"] = i + 1
    return results[:top_n]


# ---------------------------------------------------------------------------
# Method 4: Intra-Sector Dispersion Monitor
# ---------------------------------------------------------------------------

def sector_dispersion(
    price_df: pd.DataFrame,
    sector_groups: dict[str, list[str]],
    window_short: int = 20,
    window_long: int = 90,
    dispersion_threshold: float = 1.5,
) -> dict[str, dict]:
    """Method 4: Whether stocks within a sector are moving together or diverging.

    Returns dict keyed by sector name. Each value:
      sector, tickers_found, dispersion_20d, dispersion_90d_mean,
      dispersion_90d_std, dispersion_z, signal
    signal ∈ {"HIGH_DISPERSION", "LOW_DISPERSION", "NORMAL"}

    HIGH_DISPERSION → intra-sector spreads live (stocks diverging)
    LOW_DISPERSION  → trade sector as a bloc vs other sectors
    """
    results: dict[str, dict] = {}

    for sector, tickers in sector_groups.items():
        available = [t for t in tickers if t in price_df.columns]
        if len(available) < 2:
            continue

        sub = price_df[available].dropna(how="all")

        if len(sub) < window_long:
            continue

        # Daily dispersion = 1 - mean(pairwise correlations) over a window
        def _dispersion(window_df: pd.DataFrame) -> float:
            corr = window_df.corr()
            # Upper triangle only, exclude diagonal
            mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
            values = corr.values[mask]
            valid = values[~np.isnan(values)]
            if len(valid) == 0:
                return float("nan")
            return float(1.0 - np.mean(valid))

        # Rolling dispersion series using long window
        disp_series = []
        for i in range(window_long, len(sub) + 1):
            d = _dispersion(sub.iloc[i - window_long: i])
            disp_series.append(d)

        disp_series = [d for d in disp_series if not np.isnan(d)]
        if len(disp_series) < 10:
            continue

        disp_20d = _dispersion(sub.iloc[-window_short:])
        disp_90d_mean = float(np.mean(disp_series))
        disp_90d_std  = float(np.std(disp_series))

        if disp_90d_std < 1e-6:
            disp_z = 0.0
        else:
            disp_z = (disp_20d - disp_90d_mean) / disp_90d_std

        if disp_z > dispersion_threshold:
            signal = "HIGH_DISPERSION"
        elif disp_z < -dispersion_threshold:
            signal = "LOW_DISPERSION"
        else:
            signal = "NORMAL"

        results[sector] = {
            "sector": sector,
            "tickers_found": available,
            "dispersion_20d": round(disp_20d, 4),
            "dispersion_90d_mean": round(disp_90d_mean, 4),
            "dispersion_90d_std": round(disp_90d_std, 4),
            "dispersion_z": round(disp_z, 3),
            "signal": signal,
        }

    return results


# ---------------------------------------------------------------------------
# Method 5: Beta Decay Detector (protects existing war signals)
# ---------------------------------------------------------------------------

def beta_decay_detector(
    historical_events: list[dict],
    pattern_lookup: dict,
    spread_pairs: list[dict],
    decay_warning: float = 0.5,
    crowded_threshold: float = 0.3,
    recent_n_events: int = 6,
) -> list[dict]:
    """Method 5: Detect whether existing war-signal spreads are losing event sensitivity.

    Compares event beta over last *recent_n_events* events vs all historical events.
    Returns list of dicts: spread_name, decay_ratio, signal
    signal ∈ {"CROWDED", "DECAY_WARNING", "OK"}

    Only returns spreads where signal != "OK".
    """
    results = []

    for spread in spread_pairs:
        name = spread.get("name", "")
        triggers = spread.get("triggers", [])
        if not triggers:
            continue

        long_tickers = spread.get("long", [])
        short_tickers = spread.get("short", [])

        # Get all events matching this spread's triggers
        matching_events = [
            e for e in historical_events
            if e.get("category") in triggers
        ]
        if len(matching_events) < 4:
            continue  # not enough events to compare

        # Approximate spread return per event from pattern_lookup
        # pattern_lookup[category][ticker]["1d_median"]
        def _spread_return_for_events(events: list[dict]) -> list[float]:
            returns = []
            for ev in events:
                cat = ev.get("category", "")
                cat_data = pattern_lookup.get(cat, {})
                long_ret = np.mean([
                    cat_data.get(t, {}).get("1d_median", 0.0) for t in long_tickers
                    if t in cat_data
                ])
                short_ret = np.mean([
                    cat_data.get(t, {}).get("1d_median", 0.0) for t in short_tickers
                    if t in cat_data
                ])
                spread_ret = long_ret - short_ret
                returns.append(spread_ret)
            return returns

        all_returns = _spread_return_for_events(matching_events)
        recent_returns = _spread_return_for_events(matching_events[-recent_n_events:])

        if not all_returns or not recent_returns:
            continue

        beta_hist = float(np.mean(np.abs(all_returns)))
        beta_recent = float(np.mean(np.abs(recent_returns)))

        if beta_hist < 1e-6:
            continue

        decay_ratio = beta_recent / beta_hist

        if decay_ratio < crowded_threshold:
            signal = "CROWDED"
        elif decay_ratio < decay_warning:
            signal = "DECAY_WARNING"
        else:
            continue  # OK — don't include in output

        results.append({
            "spread_name": name,
            "beta_historical": round(beta_hist, 4),
            "beta_recent": round(beta_recent, 4),
            "decay_ratio": round(decay_ratio, 3),
            "signal": signal,
        })

    return results


# ---------------------------------------------------------------------------
# Regime Score (6 inputs → -6 to +6)
# ---------------------------------------------------------------------------

def regime_score(driver_df: pd.DataFrame) -> dict:
    """Compute current macro regime score from 6 numerical inputs.

    Returns dict: score (int), label (str), inputs (dict of component scores).
    label ∈ {"RISK-ON", "TRANSITIONING", "RISK-OFF"}
    """
    inputs: dict[str, int] = {}

    def _trend_pct(series: pd.Series, window: int) -> Optional[float]:
        if len(series) < window + 1:
            return None
        old = series.iloc[-(window + 1)]
        new = series.iloc[-1]
        if old == 0:
            return None
        return float((new / old - 1) * 100)

    # 1. Brent 30d trend (risk-off if rising > 5%)
    if "brent" in driver_df.columns:
        brent_prices = (driver_df["brent"] + 1).cumprod()
        t = _trend_pct(brent_prices, 30)
        if t is None:
            inputs["brent_trend"] = 0
        elif t > 5:
            inputs["brent_trend"] = -1   # rising oil = risk-off
        elif t < -5:
            inputs["brent_trend"] = 1    # falling oil = risk-on
        else:
            inputs["brent_trend"] = 0

    # 2. USD/INR 30d trend (risk-off if INR weakening > 1%)
    if "usdinr" in driver_df.columns:
        usdinr_prices = (driver_df["usdinr"] + 1).cumprod()
        t = _trend_pct(usdinr_prices, 30)
        if t is None:
            inputs["usdinr_trend"] = 0
        elif t > 1:
            inputs["usdinr_trend"] = -1  # INR weakening = risk-off
        elif t < -1:
            inputs["usdinr_trend"] = 1   # INR strengthening = risk-on
        else:
            inputs["usdinr_trend"] = 0

    # 3. India VIX level (risk-off if VIX > 18)
    if "vix" in driver_df.columns:
        try:
            from kite_client import fetch_ltp
            vix_now = fetch_ltp(["INDIA VIX"]).get("INDIA VIX", 16.0)
        except Exception:
            vix_now = 16.0
        if vix_now > 18:
            inputs["india_vix"] = -1
        elif vix_now < 14:
            inputs["india_vix"] = 1
        else:
            inputs["india_vix"] = 0

    # 4. Institutional flow (FII + DII combined)
    try:
        from macro_stress import _fetch_institutional_flow
        inst = _fetch_institutional_flow()
        combined = inst.get("combined")
        if combined is None:
            inputs["inst_flow"] = 0
        elif combined < -2000:
            inputs["inst_flow"] = -1  # net institutional selling = risk-off
        elif combined > 2000:
            inputs["inst_flow"] = 1   # net institutional buying = risk-on
        else:
            inputs["inst_flow"] = 0
    except Exception:
        inputs["inst_flow"] = 0

    # 5. Nifty 20d momentum
    if "nifty" in driver_df.columns:
        nifty_prices = (driver_df["nifty"] + 1).cumprod()
        t = _trend_pct(nifty_prices, 20)
        if t is None:
            inputs["nifty_momentum"] = 0
        elif t < -3:
            inputs["nifty_momentum"] = -1
        elif t > 3:
            inputs["nifty_momentum"] = 1
        else:
            inputs["nifty_momentum"] = 0

    # 6. US 10yr 30d direction (rising yield = risk-off)
    if "us10yr" in driver_df.columns:
        us10_prices = (driver_df["us10yr"] + 1).cumprod()
        t = _trend_pct(us10_prices, 30)
        if t is None:
            inputs["us10yr_direction"] = 0
        elif t > 0.5:    # rising ~20bps approx as pct of ~4%
            inputs["us10yr_direction"] = -1
        elif t < -0.5:
            inputs["us10yr_direction"] = 1
        else:
            inputs["us10yr_direction"] = 0

    total = sum(inputs.values())

    if total >= 3:
        label = "RISK-ON"
    elif total <= -3:
        label = "RISK-OFF"
    else:
        label = "TRANSITIONING"

    return {"score": total, "label": label, "inputs": inputs}


# ---------------------------------------------------------------------------
# Hypothesis Validator (Mode 1 — top-down)
# ---------------------------------------------------------------------------

def validate_hypotheses(
    price_df: pd.DataFrame,
    driver_df: pd.DataFrame,
    hypothesis_spreads: list[dict],
) -> list[dict]:
    """Validate each hypothesis spread against actual price data.

    For each spread, runs spread_zscore + checks if the expected driver beta
    for the short leg is developing (beta_shift signal != NORMAL).

    Returns list of dicts: spread_name, z_result, beta_confirmation, validation_status
    validation_status ∈ {"CONFIRMED", "WATCH", "REJECTED"}
    """
    beta_shifts = beta_shift_detector(price_df, driver_df)
    beta_alerts = {(r["ticker"], r["driver"]) for r in beta_shifts if r["signal"] in ("ALERT", "WATCH", "INVERSION")}

    results = []
    for spread in hypothesis_spreads:
        z_result = spread_zscore(price_df, spread)
        expected_driver = spread.get("expected_driver", "brent")

        # Check if any short-leg ticker has a beta shift on the expected driver
        short_tickers = spread.get("short", [])
        beta_confirmed = any(
            (t, expected_driver) in beta_alerts for t in short_tickers
        )

        z = z_result["z_score"]
        signal = z_result["signal"]

        if beta_confirmed and abs(z) >= 1.5:
            status = "CONFIRMED"
        elif beta_confirmed or abs(z) >= 1.0:
            status = "WATCH"
        else:
            status = "REJECTED"

        results.append({
            "spread_name": spread["name"],
            "theme": spread.get("theme", ""),
            "z_score": z,
            "z_signal": signal,
            "persistence": z_result["persistence"],
            "beta_confirmation": beta_confirmed,
            "validation_status": status,
        })

    return results
