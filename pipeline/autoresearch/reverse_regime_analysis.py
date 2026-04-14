"""
Anka Research — Reverse Regime Stock Analysis (Phase A)

Maps F&O stocks against regime transitions to find gap vs drift patterns.
For each stock x regime transition, computes overnight gap, multi-day drift,
persistence, and tradeable flags.

Usage:
    python reverse_regime_analysis.py                     # full analysis
    python reverse_regime_analysis.py --regime RISK-OFF   # filter one regime

Output:
    pipeline/autoresearch/reverse_regime_profile.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent.parent
AUTORESEARCH_DIR = PIPELINE_DIR / "autoresearch"
DATA_DIR = PIPELINE_DIR / "data"
FNO_DIR = DATA_DIR / "fno_historical"
OUTPUT_PATH = AUTORESEARCH_DIR / "reverse_regime_profile.json"

sys.path.insert(0, str(PIPELINE_DIR / "lib"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anka.reverse_regime")

# ---------------------------------------------------------------------------
# Regime thresholds (from unified_regime_engine.py)
# ---------------------------------------------------------------------------
REGIME_THRESHOLDS = [
    (11.0, "EUPHORIA"),
    (14.0, "RISK-ON"),
    (18.0, "NEUTRAL"),
    (24.0, "CAUTION"),
    (float("inf"), "RISK-OFF"),
]

VALID_REGIMES = {"EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"}


def vix_to_regime(vix: float) -> str:
    """Map a VIX value to a regime label."""
    for threshold, label in REGIME_THRESHOLDS:
        if vix < threshold:
            return label
    return "RISK-OFF"


# ---------------------------------------------------------------------------
# Sector baskets
# ---------------------------------------------------------------------------
SECTOR_BASKETS = {
    "Defence": ["HAL", "BEL", "BDL"],
    "IT_Services": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "Banks_Private": ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK"],
    "Banks_PSU": ["SBIN", "BANKBARODA", "PNB"],
    "OMCs": ["BPCL", "HINDPETRO", "IOC"],
    "Upstream_Energy": ["ONGC", "COALINDIA"],
    "Pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "Metals": ["TATASTEEL", "HINDALCO", "JSWSTEEL", "SAIL", "VEDL", "NMDC"],
    "Auto": ["MARUTI", "M&M", "BHARATFORG"],
    "FMCG": ["HINDUNILVR", "ITC", "DABUR", "BRITANNIA"],
    "RealEstate": ["DLF", "OBEROIRLTY", "GODREJPROP"],
    "Infra_Power": ["NTPC", "POWERGRID", "TATAPOWER", "LT"],
    "Conglomerate": ["RELIANCE", "ADANIENT", "SIEMENS"],
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_stock_prices(ticker: str) -> pd.DataFrame | None:
    """Load a single stock CSV. Returns DataFrame with Date index or None."""
    path = FNO_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        df.sort_index(inplace=True)
        # Ensure required columns exist
        for col in ("Open", "Close"):
            if col not in df.columns:
                log.warning("%s: missing column %s", ticker, col)
                return None
        return df
    except Exception as exc:
        log.warning("Failed to load %s: %s", ticker, exc)
        return None


def load_all_stocks() -> dict[str, pd.DataFrame]:
    """Load every CSV in fno_historical/."""
    stocks: dict[str, pd.DataFrame] = {}
    csv_files = sorted(FNO_DIR.glob("*.csv"))
    for csv_path in csv_files:
        ticker = csv_path.stem
        df = load_stock_prices(ticker)
        if df is not None and len(df) >= 10:
            stocks[ticker] = df
    log.info("Loaded %d stocks from %s", len(stocks), FNO_DIR)
    return stocks


def build_vix_regime_series() -> pd.DataFrame:
    """
    Download India VIX history via yfinance and compute daily regime.
    Returns DataFrame with columns: vix, regime (indexed by Date).
    """
    import yfinance as yf

    # Determine the date range we need from stock data
    # Use a broad window — go back 2 years to be safe
    end = datetime.now()
    start = end - timedelta(days=800)

    log.info("Downloading India VIX data (^INDIAVIX) ...")
    vix_ticker = yf.Ticker("^INDIAVIX")
    vix_df = vix_ticker.history(start=start.strftime("%Y-%m-%d"),
                                end=end.strftime("%Y-%m-%d"))

    if vix_df.empty:
        log.error("No India VIX data returned from yfinance.")
        sys.exit(1)

    # Normalise index to date-only
    vix_df.index = vix_df.index.tz_localize(None).normalize()
    vix_series = vix_df["Close"].rename("vix")
    regime_series = vix_series.apply(vix_to_regime).rename("regime")

    result = pd.DataFrame({"vix": vix_series, "regime": regime_series})
    result.index.name = "Date"
    log.info("VIX data: %d rows, range %s to %s",
             len(result), result.index.min().date(), result.index.max().date())
    return result


def find_regime_transitions(regime_df: pd.DataFrame) -> pd.DataFrame:
    """
    Find dates where the regime changed from the previous trading day.
    Returns DataFrame with columns: Date, from_regime, to_regime.
    """
    regimes = regime_df["regime"]
    shifted = regimes.shift(1)
    mask = (regimes != shifted) & shifted.notna()
    transitions = regime_df.loc[mask].copy()
    transitions["from_regime"] = shifted.loc[mask]
    transitions["to_regime"] = regimes.loc[mask]
    transitions = transitions.reset_index()
    transitions = transitions[["Date", "from_regime", "to_regime"]]
    log.info("Found %d regime transitions", len(transitions))
    return transitions


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------
def compute_stock_signals(
    stock_df: pd.DataFrame,
    transitions: pd.DataFrame,
    regime_filter: str | None = None,
) -> list[dict]:
    """
    For a single stock, compute gap/drift signals at each regime transition.
    Returns list of episode dicts.
    """
    episodes = []
    dates = stock_df.index

    for _, row in transitions.iterrows():
        t_date = row["Date"]
        to_regime = row["to_regime"]
        from_regime = row["from_regime"]

        if regime_filter and to_regime != regime_filter:
            continue

        # Find T in stock index
        if t_date not in dates:
            # Try nearest business day
            candidates = dates[dates >= t_date]
            if len(candidates) == 0:
                continue
            t_date = candidates[0]

        t_loc = dates.get_loc(t_date)
        if isinstance(t_loc, slice):
            t_loc = t_loc.start

        # Need T-1 for gap calc and T+4 for drift
        if t_loc < 1:
            continue

        prev_close = stock_df.iloc[t_loc - 1]["Close"]
        open_t = stock_df.iloc[t_loc]["Open"]
        close_t = stock_df.iloc[t_loc]["Close"]

        if pd.isna(prev_close) or pd.isna(open_t) or prev_close == 0 or open_t == 0:
            continue

        gap = (open_t / prev_close) - 1
        drift_1d = (close_t / open_t) - 1

        # 3-day drift: close of T+2
        drift_3d = np.nan
        if t_loc + 2 < len(dates):
            close_t2 = stock_df.iloc[t_loc + 2]["Close"]
            if not pd.isna(close_t2):
                drift_3d = (close_t2 / open_t) - 1

        # 5-day drift: close of T+4
        drift_5d = np.nan
        if t_loc + 4 < len(dates):
            close_t4 = stock_df.iloc[t_loc + 4]["Close"]
            if not pd.isna(close_t4):
                drift_5d = (close_t4 / open_t) - 1

        # Tradeable and persistence flags (based on 5d drift)
        tradeable = False
        persists = False
        if not np.isnan(drift_5d):
            tradeable = abs(drift_5d) > abs(gap)
            persists = np.sign(drift_5d) == np.sign(gap) if gap != 0 else False

        episodes.append({
            "date": t_date.strftime("%Y-%m-%d"),
            "from_regime": from_regime,
            "to_regime": to_regime,
            "gap": round(float(gap), 6),
            "drift_1d": round(float(drift_1d), 6),
            "drift_3d": round(float(drift_3d), 6) if not np.isnan(drift_3d) else None,
            "drift_5d": round(float(drift_5d), 6) if not np.isnan(drift_5d) else None,
            "tradeable": bool(tradeable),
            "persists": bool(persists),
        })

    return episodes


def aggregate_signals(episodes: list[dict]) -> dict:
    """Aggregate episode-level signals into summary statistics."""
    if not episodes:
        return {
            "episode_count": 0,
            "avg_gap": 0,
            "avg_drift_5d": 0,
            "tradeable_rate": 0,
            "persistence_rate": 0,
            "hit_rate": 0,
        }

    gaps = [e["gap"] for e in episodes]
    drifts_5d = [e["drift_5d"] for e in episodes if e["drift_5d"] is not None]
    tradeable_flags = [e["tradeable"] for e in episodes if e["drift_5d"] is not None]
    persist_flags = [e["persists"] for e in episodes if e["drift_5d"] is not None]

    # Hit rate: fraction of episodes where drift_5d is positive (profitable long)
    positive_drifts = [d for d in drifts_5d if d > 0]
    hit_rate = len(positive_drifts) / len(drifts_5d) if drifts_5d else 0

    drifts_1d = [e["drift_1d"] for e in episodes]
    drifts_3d = [e["drift_3d"] for e in episodes if e["drift_3d"] is not None]

    return {
        "episode_count": len(episodes),
        "avg_gap": round(float(np.mean(gaps)), 6) if gaps else 0,
        "std_gap": round(float(np.std(gaps)), 6) if len(gaps) > 1 else 0,
        "avg_drift_1d": round(float(np.mean(drifts_1d)), 6),
        "std_drift_1d": round(float(np.std(drifts_1d)), 6) if len(drifts_1d) > 1 else 0,
        "avg_drift_3d": round(float(np.mean(drifts_3d)), 6) if drifts_3d else 0,
        "std_drift_3d": round(float(np.std(drifts_3d)), 6) if len(drifts_3d) > 1 else 0,
        "avg_drift_5d": round(float(np.mean(drifts_5d)), 6) if drifts_5d else 0,
        "std_drift_5d": round(float(np.std(drifts_5d)), 6) if len(drifts_5d) > 1 else 0,
        "tradeable_rate": round(sum(tradeable_flags) / len(tradeable_flags), 4) if tradeable_flags else 0,
        "persistence_rate": round(sum(persist_flags) / len(persist_flags), 4) if persist_flags else 0,
        "hit_rate": round(hit_rate, 4),
    }


def analyse_by_transition(episodes: list[dict]) -> dict[str, dict]:
    """Break down aggregate stats by regime transition type."""
    by_transition: dict[str, list[dict]] = {}
    for ep in episodes:
        key = f"{ep['from_regime']}->{ep['to_regime']}"
        by_transition.setdefault(key, []).append(ep)

    return {k: aggregate_signals(v) for k, v in by_transition.items()}


# ---------------------------------------------------------------------------
# Sector basket analysis
# ---------------------------------------------------------------------------
def build_sector_returns(
    stocks: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """
    Build equal-weight sector basket price series.
    Returns dict of sector_name -> DataFrame with Open/Close columns.
    """
    sector_dfs: dict[str, pd.DataFrame] = {}

    for sector, tickers in SECTOR_BASKETS.items():
        available = [t for t in tickers if t in stocks]
        if not available:
            log.warning("Sector %s: no stocks available", sector)
            continue

        # Normalise each stock to base=100, then equal-weight average
        normed_open_list = []
        normed_close_list = []
        for t in available:
            df = stocks[t][["Open", "Close"]].copy()
            base = df["Close"].iloc[0]
            if base == 0 or pd.isna(base):
                continue
            normed_open_list.append((df["Open"] / base * 100).rename(t))
            normed_close_list.append((df["Close"] / base * 100).rename(t))

        if not normed_open_list:
            continue

        open_basket = pd.concat(normed_open_list, axis=1).mean(axis=1).rename("Open")
        close_basket = pd.concat(normed_close_list, axis=1).mean(axis=1).rename("Close")
        basket_df = pd.concat([open_basket, close_basket], axis=1).dropna()
        sector_dfs[sector] = basket_df

    log.info("Built %d sector baskets", len(sector_dfs))
    return sector_dfs


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------
def run_analysis(regime_filter: str | None = None) -> dict:
    """
    Run the full Phase A reverse regime analysis.
    Returns the complete profile dict (also saved to JSON).
    """
    # 1. Load stock data
    stocks = load_all_stocks()
    if not stocks:
        log.error("No stock data found in %s", FNO_DIR)
        sys.exit(1)

    # 2. Build regime series and find transitions
    regime_df = build_vix_regime_series()
    transitions = find_regime_transitions(regime_df)
    if transitions.empty:
        log.error("No regime transitions found.")
        sys.exit(1)

    # 3. Analyse individual stocks
    log.info("Analysing %d stocks across %d transitions ...",
             len(stocks), len(transitions))
    stock_profiles: dict[str, dict] = {}

    for ticker, df in stocks.items():
        episodes = compute_stock_signals(df, transitions, regime_filter)
        if not episodes:
            continue
        summary = aggregate_signals(episodes)
        by_transition = analyse_by_transition(episodes)
        stock_profiles[ticker] = {
            "summary": summary,
            "by_transition": by_transition,
            "episodes": episodes,
        }

    log.info("Generated profiles for %d stocks", len(stock_profiles))

    # 4. Analyse sector baskets
    sector_dfs = build_sector_returns(stocks)
    sector_profiles: dict[str, dict] = {}

    for sector, basket_df in sector_dfs.items():
        episodes = compute_stock_signals(basket_df, transitions, regime_filter)
        if not episodes:
            continue
        summary = aggregate_signals(episodes)
        by_transition = analyse_by_transition(episodes)
        sector_profiles[sector] = {
            "summary": summary,
            "by_transition": by_transition,
            "episodes": episodes,
        }

    log.info("Generated profiles for %d sector baskets", len(sector_profiles))

    # 5. Build output
    profile = {
        "generated_at": datetime.now().isoformat(),
        "regime_filter": regime_filter,
        "transition_count": len(transitions),
        "transitions": transitions.to_dict(orient="records"),
        "stock_profiles": stock_profiles,
        "sector_profiles": sector_profiles,
    }

    # Serialise dates in transitions
    for t in profile["transitions"]:
        if isinstance(t["Date"], pd.Timestamp):
            t["Date"] = t["Date"].strftime("%Y-%m-%d")

    # Save
    AUTORESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, default=str)
    log.info("Saved profile to %s", OUTPUT_PATH)

    return profile


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------
def print_report(profile: dict) -> None:
    """Print a ranked summary to console."""
    print("\n" + "=" * 80)
    print("  REVERSE REGIME ANALYSIS — Phase A Report")
    print("=" * 80)

    regime_filter = profile.get("regime_filter")
    if regime_filter:
        print(f"  Regime filter: {regime_filter}")
    print(f"  Transitions analysed: {profile['transition_count']}")
    print()

    # Transition summary
    print("  REGIME TRANSITIONS:")
    for t in profile["transitions"]:
        print(f"    {t['Date']}  {t['from_regime']:>10s} -> {t['to_regime']:<10s}")
    print()

    # Rank stocks by tradeable_rate * persistence_rate (combined quality)
    ranked: list[tuple[str, str, dict]] = []
    for ticker, data in profile["stock_profiles"].items():
        s = data["summary"]
        if s["episode_count"] < 2:
            continue
        ranked.append((ticker, "stock", s))

    for sector, data in profile["sector_profiles"].items():
        s = data["summary"]
        if s["episode_count"] < 2:
            continue
        ranked.append((sector, "sector", s))

    # Sort by tradeable_rate descending, then persistence, then hit_rate
    ranked.sort(
        key=lambda x: (x[2]["tradeable_rate"], x[2]["persistence_rate"], x[2]["hit_rate"]),
        reverse=True,
    )

    # Top signals
    print("  TOP SIGNALS (tradeable + persistent):")
    print(f"  {'Name':<18s} {'Type':<8s} {'Episodes':>8s} {'AvgGap':>9s} "
          f"{'AvgDrift5d':>11s} {'Tradeable%':>11s} {'Persist%':>9s} {'HitRate':>8s}")
    print("  " + "-" * 78)

    gate_strict = 0
    gate_relaxed = 0
    for name, kind, s in ranked[:40]:
        flag = ""
        # Strict: all three criteria
        is_strict = (s["tradeable_rate"] > 0.80 and s["hit_rate"] > 0.55
                     and s["persistence_rate"] > 0.60)
        # Relaxed: two of three (tradeable is nearly universal, so require
        # hit_rate > 55% OR persistence > 50%, plus drift magnitude > 0.5%)
        is_relaxed = (abs(s["avg_drift_5d"]) > 0.005
                      and s["episode_count"] >= 3
                      and (s["hit_rate"] > 0.55 or s["persistence_rate"] > 0.50))
        if is_strict:
            flag = " ***"
            gate_strict += 1
        elif is_relaxed:
            flag = " **"
            gate_relaxed += 1

        print(f"  {name:<18s} {kind:<8s} {s['episode_count']:>8d} "
              f"{s['avg_gap']:>+9.4f} {s['avg_drift_5d']:>+11.4f} "
              f"{s['tradeable_rate']:>10.1%} {s['persistence_rate']:>9.1%} "
              f"{s['hit_rate']:>7.1%}{flag}")

    print()

    # Gate check (relaxed: 2-of-3 criteria + minimum drift magnitude)
    total_gate = gate_strict + gate_relaxed
    print("  " + "-" * 40)
    print(f"  Gate-passing (strict ***): {gate_strict}")
    print(f"  Gate-passing (relaxed **): {gate_relaxed}")
    print(f"  Total actionable: {total_gate}")
    if total_gate >= 5:
        print("  GATE PASSED — sufficient tradeable patterns found.")
    else:
        print("  GATE FAILED — fewer than 5 actionable stock-regime combinations")
        print("  (*** = hit>55% + persist>60% + trade>80%, ** = drift>0.5% + hit>55% or persist>50%)")
    print()

    # Sector basket summary
    if profile["sector_profiles"]:
        print("  SECTOR BASKET SUMMARY:")
        print(f"  {'Sector':<18s} {'Episodes':>8s} {'AvgGap':>9s} "
              f"{'AvgDrift5d':>11s} {'Tradeable%':>11s} {'Persist%':>9s}")
        print("  " + "-" * 60)
        for sector in sorted(profile["sector_profiles"].keys()):
            s = profile["sector_profiles"][sector]["summary"]
            print(f"  {sector:<18s} {s['episode_count']:>8d} "
                  f"{s['avg_gap']:>+9.4f} {s['avg_drift_5d']:>+11.4f} "
                  f"{s['tradeable_rate']:>10.1%} {s['persistence_rate']:>9.1%}")
        print()

    print("=" * 80)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Anka Research — Reverse Regime Stock Analysis (Phase A)"
    )
    parser.add_argument(
        "--regime",
        type=str,
        default=None,
        choices=sorted(VALID_REGIMES),
        help="Filter analysis to a single target regime (e.g. RISK-OFF)",
    )
    args = parser.parse_args()

    profile = run_analysis(regime_filter=args.regime)
    print_report(profile)


if __name__ == "__main__":
    main()
