"""
Anka Research — Scorecard Alpha Test (Analysis 2)
Does management grade predict stock returns? Does it vary by regime?

Method:
  1. Load all 57 graded stocks from opus/artifacts trust_score.json
  2. Bucket into QUALITY (A+/A/B+/B) vs NEUTRAL (C) vs WEAK (D/F)
  3. Fetch 1-year daily prices via yfinance (free, $0)
  4. Reconstruct regimes using India VIX proxy (VIX<15 RISK-ON, 15-20 NEUTRAL, >20 RISK-OFF)
  5. Compute forward returns (5d, 10d, 20d) for each bucket × regime
  6. Report: does quality separate returns? Is the edge regime-dependent?

Output: pipeline/data/scorecard_alpha_results.json + console summary
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure lib/ is importable
_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("scorecard_alpha")

PIPELINE_DIR = Path(__file__).parent
OPUS_DIR = PIPELINE_DIR.parent / "opus" / "artifacts"
DATA_DIR = PIPELINE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Load trust score grades
# ---------------------------------------------------------------------------

def load_grades() -> dict[str, dict]:
    """Load all trust scores, return {SYMBOL: {grade, score_pct, trajectory}}."""
    results = {}
    for d in sorted(OPUS_DIR.iterdir()):
        ts_file = d / "trust_score.json"
        if not ts_file.exists():
            continue
        try:
            data = json.loads(ts_file.read_text(encoding="utf-8"))
            grade = data.get("trust_score_grade", "?")
            if grade == "?":
                continue
            results[d.name] = {
                "grade": grade,
                "score_pct": data.get("trust_score_pct", 0),
                "trajectory": data.get("credibility_trajectory", "unknown"),
                "delivery_rate": data.get("delivery_rate", 0),
            }
        except (json.JSONDecodeError, KeyError):
            continue
    return results


def bucket_stocks(grades: dict) -> dict[str, list[str]]:
    """Group stocks into QUALITY / NEUTRAL / WEAK buckets."""
    buckets = {"QUALITY": [], "NEUTRAL": [], "WEAK": []}
    for sym, info in grades.items():
        g = info["grade"]
        if g in ("A+", "A", "B+", "B"):
            buckets["QUALITY"].append(sym)
        elif g == "C":
            buckets["NEUTRAL"].append(sym)
        elif g in ("D", "F"):
            buckets["WEAK"].append(sym)
    return buckets


# ---------------------------------------------------------------------------
# 2. Fetch price data (yfinance — free)
# ---------------------------------------------------------------------------

def fetch_prices(symbols: list[str], days: int = 400) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for all symbols. Cache to CSV."""
    import yfinance as yf

    hist_dir = DATA_DIR / "alpha_test_cache"
    hist_dir.mkdir(exist_ok=True)

    end = datetime.now()
    start = end - timedelta(days=days)
    result = {}

    for sym in symbols:
        csv_path = hist_dir / f"{sym}.csv"
        # Use cache if < 12 hours old
        if csv_path.exists():
            mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
            if (datetime.now() - mtime) < timedelta(hours=12):
                df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                if len(df) > 50:
                    result[sym] = df
                    continue

        yf_ticker = f"{sym}.NS"
        try:
            df = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df is None or len(df) < 50:
                log.warning("Insufficient data for %s (%d rows)", sym, len(df) if df is not None else 0)
                continue
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_csv(csv_path)
            result[sym] = df
            log.info("Fetched %s: %d rows", sym, len(df))
        except Exception as exc:
            log.warning("Failed to fetch %s: %s", sym, exc)

    return result


def fetch_vix(days: int = 400) -> pd.Series:
    """Fetch India VIX history as regime proxy."""
    import yfinance as yf

    cache = DATA_DIR / "alpha_test_cache" / "INDIAVIX.csv"
    if cache.exists():
        mtime = datetime.fromtimestamp(cache.stat().st_mtime)
        if (datetime.now() - mtime) < timedelta(hours=12):
            df = pd.read_csv(cache, index_col=0, parse_dates=True)
            if len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df["Close"]

    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download("^INDIAVIX", start=start, end=end, progress=False, auto_adjust=True)
    if df is None or len(df) < 50:
        # Fallback: use NIFTY volatility as proxy
        log.warning("India VIX unavailable, using NIFTY 20d realized vol as proxy")
        nifty = yf.download("^NSEI", start=start, end=end, progress=False, auto_adjust=True)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        returns = nifty["Close"].pct_change()
        vix_proxy = returns.rolling(20).std() * np.sqrt(252) * 100
        vix_proxy.to_frame("Close").to_csv(cache)
        return vix_proxy

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.to_csv(cache)
    return df["Close"]


# ---------------------------------------------------------------------------
# 3. Assign regimes from VIX levels
# ---------------------------------------------------------------------------

def assign_regimes(vix: pd.Series) -> pd.Series:
    """Map VIX levels to regime labels.

    VIX < 14  → RISK-ON (euphoria/momentum)
    14-18     → NEUTRAL
    18-24     → CAUTION
    > 24      → RISK-OFF (fear/defensive)
    """
    def _classify(v):
        if pd.isna(v):
            return "NEUTRAL"
        if v < 14:
            return "RISK-ON"
        elif v < 18:
            return "NEUTRAL"
        elif v < 24:
            return "CAUTION"
        else:
            return "RISK-OFF"

    return vix.apply(_classify)


# ---------------------------------------------------------------------------
# 4. Compute forward returns
# ---------------------------------------------------------------------------

def compute_forward_returns(
    prices: dict[str, pd.DataFrame],
    windows: list[int] = [5, 10, 20],
) -> pd.DataFrame:
    """Compute forward returns for each stock on each trading day.

    Returns DataFrame with columns: symbol, date, fwd_5d, fwd_10d, fwd_20d
    """
    rows = []
    for sym, df in prices.items():
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"]
        for w in windows:
            col = f"fwd_{w}d"
            fwd = close.shift(-w) / close - 1
            for date, ret in fwd.items():
                # Find or create row for this sym+date
                pass  # build below

    # More efficient: build a single DataFrame per stock
    all_dfs = []
    for sym, df in prices.items():
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"]
        fwd_df = pd.DataFrame({"symbol": sym}, index=close.index)
        for w in windows:
            fwd_df[f"fwd_{w}d"] = (close.shift(-w) / close - 1) * 100  # in %
        fwd_df["date"] = fwd_df.index
        all_dfs.append(fwd_df)

    if not all_dfs:
        return pd.DataFrame()
    return pd.concat(all_dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# 5. Stratified analysis: grade × regime → returns
# ---------------------------------------------------------------------------

def run_analysis(
    fwd_returns: pd.DataFrame,
    regimes: pd.Series,
    grades: dict[str, dict],
    buckets: dict[str, list[str]],
) -> dict:
    """Core analysis: compare returns by grade bucket and regime."""

    # Add grade bucket to each row
    sym_to_bucket = {}
    for bucket_name, syms in buckets.items():
        for s in syms:
            sym_to_bucket[s] = bucket_name
    fwd_returns["bucket"] = fwd_returns["symbol"].map(sym_to_bucket)

    # Add regime to each row (align by date)
    regime_map = regimes.to_dict()
    fwd_returns["regime"] = fwd_returns["date"].map(
        lambda d: regime_map.get(d, regime_map.get(pd.Timestamp(d), "UNKNOWN"))
    )

    # Clean up
    fwd_returns = fwd_returns[fwd_returns["regime"] != "UNKNOWN"]
    fwd_returns = fwd_returns.dropna(subset=["fwd_5d"])

    results = {}

    # --- A. Overall: QUALITY vs WEAK ---
    for window in ["fwd_5d", "fwd_10d", "fwd_20d"]:
        results[f"overall_{window}"] = {}
        for bucket_name in ["QUALITY", "NEUTRAL", "WEAK"]:
            subset = fwd_returns[fwd_returns["bucket"] == bucket_name][window].dropna()
            if len(subset) == 0:
                continue
            results[f"overall_{window}"][bucket_name] = {
                "mean_return_pct": round(float(subset.mean()), 3),
                "median_return_pct": round(float(subset.median()), 3),
                "std_pct": round(float(subset.std()), 3),
                "win_rate_pct": round(float((subset > 0).mean() * 100), 1),
                "n_observations": int(len(subset)),
                "sharpe_annualized": round(
                    float(subset.mean() / subset.std() * np.sqrt(252 / int(window.split("_")[1].replace("d", "")))),
                    2,
                ) if subset.std() > 0 else 0,
            }

    # --- B. Regime-stratified: grade × regime ---
    results["by_regime"] = {}
    for regime in ["RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]:
        results["by_regime"][regime] = {}
        regime_data = fwd_returns[fwd_returns["regime"] == regime]
        if len(regime_data) == 0:
            continue
        for bucket_name in ["QUALITY", "NEUTRAL", "WEAK"]:
            subset = regime_data[regime_data["bucket"] == bucket_name]["fwd_10d"].dropna()
            if len(subset) < 10:
                results["by_regime"][regime][bucket_name] = {
                    "mean_return_pct": round(float(subset.mean()), 3) if len(subset) > 0 else None,
                    "n_observations": int(len(subset)),
                    "note": "too few observations for significance",
                }
                continue
            results["by_regime"][regime][bucket_name] = {
                "mean_return_pct": round(float(subset.mean()), 3),
                "median_return_pct": round(float(subset.median()), 3),
                "win_rate_pct": round(float((subset > 0).mean() * 100), 1),
                "n_observations": int(len(subset)),
            }

    # --- C. QUALITY - WEAK spread (the alpha) ---
    results["alpha_spread"] = {}
    for window in ["fwd_5d", "fwd_10d", "fwd_20d"]:
        q_mean = results.get(f"overall_{window}", {}).get("QUALITY", {}).get("mean_return_pct")
        w_mean = results.get(f"overall_{window}", {}).get("WEAK", {}).get("mean_return_pct")
        if q_mean is not None and w_mean is not None:
            results["alpha_spread"][window] = {
                "quality_minus_weak_pct": round(q_mean - w_mean, 3),
                "quality_mean": q_mean,
                "weak_mean": w_mean,
            }

    # --- D. Regime-stratified alpha spread ---
    results["alpha_by_regime"] = {}
    for regime in ["RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]:
        q = results.get("by_regime", {}).get(regime, {}).get("QUALITY", {})
        w = results.get("by_regime", {}).get(regime, {}).get("WEAK", {})
        q_mean = q.get("mean_return_pct")
        w_mean = w.get("mean_return_pct")
        if q_mean is not None and w_mean is not None:
            results["alpha_by_regime"][regime] = {
                "quality_minus_weak_pct": round(q_mean - w_mean, 3),
                "quality_mean": q_mean,
                "weak_mean": w_mean,
                "quality_n": q.get("n_observations", 0),
                "weak_n": w.get("n_observations", 0),
            }

    # --- E. Per-stock returns for granularity ---
    results["per_stock_10d"] = {}
    for sym in fwd_returns["symbol"].unique():
        stock_data = fwd_returns[fwd_returns["symbol"] == sym]["fwd_10d"].dropna()
        if len(stock_data) < 20:
            continue
        grade_info = grades.get(sym, {})
        results["per_stock_10d"][sym] = {
            "grade": grade_info.get("grade", "?"),
            "delivery_rate": grade_info.get("delivery_rate", 0),
            "mean_10d_return_pct": round(float(stock_data.mean()), 3),
            "win_rate_pct": round(float((stock_data > 0).mean() * 100), 1),
            "n": int(len(stock_data)),
        }

    # --- F. Statistical significance (t-test) ---
    from scipy import stats
    quality_returns = fwd_returns[fwd_returns["bucket"] == "QUALITY"]["fwd_10d"].dropna()
    weak_returns = fwd_returns[fwd_returns["bucket"] == "WEAK"]["fwd_10d"].dropna()
    if len(quality_returns) > 10 and len(weak_returns) > 10:
        t_stat, p_value = stats.ttest_ind(quality_returns, weak_returns, equal_var=False)
        results["significance"] = {
            "t_statistic": round(float(t_stat), 3),
            "p_value": round(float(p_value), 4),
            "significant_at_5pct": p_value < 0.05,
            "significant_at_10pct": p_value < 0.10,
            "quality_n": int(len(quality_returns)),
            "weak_n": int(len(weak_returns)),
        }

    return results


# ---------------------------------------------------------------------------
# 6. Pretty-print summary
# ---------------------------------------------------------------------------

def print_summary(results: dict, buckets: dict, grades: dict):
    """Print a readable summary of the alpha test results."""
    print("\n" + "=" * 70)
    print("  ANKA SCORECARD ALPHA TEST — Management Grade vs Stock Returns")
    print("=" * 70)

    print(f"\n  Universe: {sum(len(v) for v in buckets.values())} graded stocks")
    print(f"  QUALITY (A+/A/B+/B): {len(buckets['QUALITY'])} stocks — {', '.join(buckets['QUALITY'])}")
    print(f"  NEUTRAL (C):         {len(buckets['NEUTRAL'])} stocks")
    print(f"  WEAK (D/F):          {len(buckets['WEAK'])} stocks — {len([s for s in buckets['WEAK'] if grades[s]['grade']=='D'])}D + {len([s for s in buckets['WEAK'] if grades[s]['grade']=='F'])}F")

    # Overall returns
    print("\n" + "-" * 70)
    print("  OVERALL FORWARD RETURNS (annualized context)")
    print("-" * 70)
    print(f"  {'Window':<10} {'QUALITY':>12} {'NEUTRAL':>12} {'WEAK':>12} {'Q-W Alpha':>12}")
    for window in ["fwd_5d", "fwd_10d", "fwd_20d"]:
        q = results.get(f"overall_{window}", {}).get("QUALITY", {})
        n = results.get(f"overall_{window}", {}).get("NEUTRAL", {})
        w = results.get(f"overall_{window}", {}).get("WEAK", {})
        alpha = results.get("alpha_spread", {}).get(window, {})
        q_str = f"{q.get('mean_return_pct', 'N/A'):>8}%" if q else "N/A"
        n_str = f"{n.get('mean_return_pct', 'N/A'):>8}%" if n else "N/A"
        w_str = f"{w.get('mean_return_pct', 'N/A'):>8}%" if w else "N/A"
        a_str = f"{alpha.get('quality_minus_weak_pct', 'N/A'):>8}%" if alpha else "N/A"
        label = window.replace("fwd_", "").replace("d", "-day")
        print(f"  {label:<10} {q_str:>12} {n_str:>12} {w_str:>12} {a_str:>12}")

    # Win rates
    print(f"\n  {'Window':<10} {'Q win%':>12} {'N win%':>12} {'W win%':>12}")
    for window in ["fwd_5d", "fwd_10d", "fwd_20d"]:
        q = results.get(f"overall_{window}", {}).get("QUALITY", {})
        n = results.get(f"overall_{window}", {}).get("NEUTRAL", {})
        w = results.get(f"overall_{window}", {}).get("WEAK", {})
        label = window.replace("fwd_", "").replace("d", "-day")
        print(f"  {label:<10} {q.get('win_rate_pct', 'N/A'):>11}% {n.get('win_rate_pct', 'N/A'):>11}% {w.get('win_rate_pct', 'N/A'):>11}%")

    # Regime-stratified
    print("\n" + "-" * 70)
    print("  REGIME-STRATIFIED (10-day forward returns)")
    print("-" * 70)
    for regime in ["RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]:
        alpha = results.get("alpha_by_regime", {}).get(regime, {})
        data = results.get("by_regime", {}).get(regime, {})
        if not data:
            print(f"  {regime:<12} — no data")
            continue
        q = data.get("QUALITY", {})
        w = data.get("WEAK", {})
        q_str = f"{q.get('mean_return_pct', 'N/A')}% (n={q.get('n_observations', 0)})"
        w_str = f"{w.get('mean_return_pct', 'N/A')}% (n={w.get('n_observations', 0)})"
        a_str = f"{alpha.get('quality_minus_weak_pct', 'N/A')}%" if alpha else "N/A"
        print(f"  {regime:<12} QUALITY: {q_str:<25} WEAK: {w_str:<25} Alpha: {a_str}")

    # Significance
    sig = results.get("significance", {})
    if sig:
        print("\n" + "-" * 70)
        print("  STATISTICAL SIGNIFICANCE (Welch's t-test, QUALITY vs WEAK 10d returns)")
        print("-" * 70)
        print(f"  t-statistic:  {sig['t_statistic']}")
        print(f"  p-value:      {sig['p_value']}")
        print(f"  Significant at 5%:  {'YES' if sig.get('significant_at_5pct') else 'NO'}")
        print(f"  Significant at 10%: {'YES' if sig.get('significant_at_10pct') else 'NO'}")
        print(f"  Observations: QUALITY={sig['quality_n']}, WEAK={sig['weak_n']}")

    # Top/bottom stocks
    per_stock = results.get("per_stock_10d", {})
    if per_stock:
        print("\n" + "-" * 70)
        print("  TOP 10 STOCKS BY 10-DAY MEAN RETURN")
        print("-" * 70)
        sorted_stocks = sorted(per_stock.items(), key=lambda x: x[1]["mean_10d_return_pct"], reverse=True)
        print(f"  {'Stock':<15} {'Grade':>6} {'Delivery%':>10} {'Mean 10d':>10} {'Win%':>8}")
        for sym, info in sorted_stocks[:10]:
            print(f"  {sym:<15} {info['grade']:>6} {info['delivery_rate']:>9.1f}% {info['mean_10d_return_pct']:>9.3f}% {info['win_rate_pct']:>7.1f}%")
        print(f"\n  BOTTOM 10:")
        for sym, info in sorted_stocks[-10:]:
            print(f"  {sym:<15} {info['grade']:>6} {info['delivery_rate']:>9.1f}% {info['mean_10d_return_pct']:>9.3f}% {info['win_rate_pct']:>7.1f}%")

    # Verdict
    print("\n" + "=" * 70)
    alpha_10d = results.get("alpha_spread", {}).get("fwd_10d", {}).get("quality_minus_weak_pct")
    if alpha_10d is not None:
        if alpha_10d > 0.5:
            verdict = "STRONG SIGNAL — Management grade predicts returns. Build the basket."
        elif alpha_10d > 0.1:
            verdict = "MODERATE SIGNAL — Grade has some predictive power. Combine with other factors."
        elif alpha_10d > -0.1:
            verdict = "NO SIGNAL — Grade does not separate returns meaningfully."
        else:
            verdict = "INVERSE SIGNAL — Weak management stocks outperform! Grade may be contrarian."
        print(f"  VERDICT: {verdict}")
        print(f"  10-day alpha (QUALITY - WEAK): {alpha_10d:+.3f}%")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("Loading trust score grades...")
    grades = load_grades()
    buckets = bucket_stocks(grades)
    log.info("Grades loaded: QUALITY=%d, NEUTRAL=%d, WEAK=%d",
             len(buckets["QUALITY"]), len(buckets["NEUTRAL"]), len(buckets["WEAK"]))

    all_symbols = sum(buckets.values(), [])
    log.info("Fetching price data for %d stocks (yfinance, $0)...", len(all_symbols))
    prices = fetch_prices(all_symbols)
    log.info("Price data: %d/%d stocks loaded", len(prices), len(all_symbols))

    log.info("Fetching India VIX for regime classification...")
    vix = fetch_vix()
    regimes = assign_regimes(vix)
    regime_counts = regimes.value_counts()
    log.info("Regime distribution:\n%s", regime_counts.to_string())

    log.info("Computing forward returns...")
    fwd_returns = compute_forward_returns(prices)
    log.info("Forward return observations: %d", len(fwd_returns))

    log.info("Running stratified analysis...")
    results = run_analysis(fwd_returns, regimes, grades, buckets)

    # Save results
    output_file = DATA_DIR / "scorecard_alpha_results.json"
    output_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log.info("Results saved to %s", output_file)

    # Print summary
    print_summary(results, buckets, grades)

    return results


if __name__ == "__main__":
    main()
