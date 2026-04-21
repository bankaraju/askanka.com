# pipeline/research/phase_c_v5/run_v50.py
"""End-to-end V5.0 runner — 4 sub-variants against full history.

Outputs ledgers to CACHE_DIR/ledgers/v50_<sub>.parquet and prints a
verdict table (Sharpe CI, hit rate, binomial p, Bonferroni pass).

DEVIATIONS FROM PLAN (documented for reviewer traceability):
  1. REGIME_HISTORY_PATH points at V4's regime_backfill.json (already
     contains 924 business days of daily regime labels) rather than a
     never-created regime_history_daily.json.
  2. Phase A profile at reverse_regime_profile.json uses
     ``stock_profiles[SYM].by_transition["X->Y"]`` — not the flat
     ``{zone: {symbols: {sym: ...}}}`` that ranker_backfill expects.
     A local _adapt_profile() helper collapses by_transition keys to a
     zone-conditional schema (picking the transition with the most
     episodes per stock/zone).
"""
from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_v5 import paths, ranker_backfill
from pipeline.research.phase_c_v5.variants import v50_regime_pair
from pipeline.research.phase_c_backtest import stats as v4_stats
from pipeline.research.phase_c_backtest import fetcher

log = logging.getLogger("v50")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BONFERRONI_N_TESTS = 12  # 8 primary + 4 V5.0 sub-variants

PROFILE_PATH = paths.PIPELINE_DIR / "autoresearch" / "reverse_regime_profile.json"
# V4 regime backfill is authoritative — contains 924 business days
# 2022-10 through 2026-04 and is kept current by the V4 backtest runner.
REGIME_HISTORY_PATH = paths.PIPELINE_DIR / "data" / "research" / "phase_c" / "regime_backfill.json"


def _adapt_profile(real_profile: dict) -> dict:
    """Collapse real Phase A schema into the zone-conditional form
    ranker_backfill expects.

    Real schema:
        {stock_profiles: {SYM: {by_transition: {"FROM->TO": {avg_drift_5d,
         hit_rate, episode_count}}}}}

    Adapted schema:
        {ZONE: {symbols: {SYM: {drift_5d_mean, hit_rate_5d, episodes}}}}

    For each (stock, target_zone) pair, pick the incoming transition with
    the largest ``episode_count``.
    """
    adapted: dict[str, dict[str, dict[str, dict]]] = {}
    stock_profiles = real_profile.get("stock_profiles", {})
    for sym, sym_data in stock_profiles.items():
        by_transition = sym_data.get("by_transition", {}) or {}
        # bucket incoming-to-zone
        per_zone_best: dict[str, dict] = {}
        for key, stats in by_transition.items():
            parts = key.split("->")
            if len(parts) != 2:
                continue
            target_zone = parts[1].strip()
            if not target_zone:
                continue
            ep = stats.get("episode_count", 0)
            best = per_zone_best.get(target_zone)
            if best is None or ep > best["_episodes"]:
                per_zone_best[target_zone] = {
                    "drift_5d_mean": stats.get("avg_drift_5d", 0.0),
                    "hit_rate_5d": stats.get("hit_rate", 0.0),
                    "episodes": ep,
                    "_episodes": ep,
                }
        for zone, entry in per_zone_best.items():
            zone_bucket = adapted.setdefault(zone, {"symbols": {}})
            zone_bucket["symbols"][sym] = {
                "drift_5d_mean": entry["drift_5d_mean"],
                "hit_rate_5d": entry["hit_rate_5d"],
                "episodes": entry["episodes"],
            }
    return adapted


def _load_regime_history() -> pd.DataFrame:
    """V4 regime_backfill.json is authoritative — it's a ``{date: zone}`` map."""
    raw = json.loads(REGIME_HISTORY_PATH.read_text(encoding="utf-8"))
    rows = [{"date": d, "zone": z} for d, z in raw.items()]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _unique_candidate_symbols(ranker_df: pd.DataFrame) -> list[str]:
    return sorted(set(ranker_df["symbol"].tolist()))


def _yfinance_fetch(symbol: str, years: int = 4) -> pd.DataFrame | None:
    """Fetch daily OHLCV via yfinance as a last-resort fallback.

    Returns a DataFrame with V4 schema (date, open, high, low, close, volume)
    or None if unavailable.
    """
    from datetime import date, timedelta
    try:
        import yfinance as yf
        end = date.today().strftime("%Y-%m-%d")
        start = (date.today() - timedelta(days=years * 366)).strftime("%Y-%m-%d")
        raw = yf.download(f"{symbol}.NS", start=start, end=end,
                          progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)
        raw = raw.reset_index()
        raw.columns = [c.lower() for c in raw.columns]
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(raw.columns)):
            return None
        df = raw[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.sort_values("date").reset_index(drop=True)
        return df if not df.empty else None
    except Exception as exc:
        log.warning("yfinance fallback failed for %s: %s", symbol, exc)
        return None


def _load_bars_bulk(symbols: list[str], days: int = 1500) -> dict[str, pd.DataFrame]:
    """Load daily bars for all candidate symbols.

    Primary: V4 fetcher (reads from parquet cache; falls back to Kite when
    cache coverage is stale but Kite may be unavailable outside schedule hours).
    Secondary: yfinance with .NS suffix — used when the fetcher raises any
    exception (e.g. Kite auth missing).
    """
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            out[sym] = fetcher.fetch_daily(sym, days=days)
        except Exception as exc:
            log.warning("V4 fetcher failed for %s (%s) — trying yfinance fallback", sym, exc)
            yf_df = _yfinance_fetch(sym)
            if yf_df is not None and not yf_df.empty:
                # Write to cache so the simulator can use it and future runs are fast
                cache_path = fetcher._DAILY_DIR / f"{sym}.parquet"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                yf_df.to_parquet(cache_path, index=False)
                log.info("yfinance fallback seeded cache for %s (%d rows)", sym, len(yf_df))
                out[sym] = yf_df
            else:
                log.warning("yfinance fallback also failed for %s — symbol will be skipped", sym)
    return out


def _verdict_row(ledger: pd.DataFrame, sub_variant: str) -> dict:
    if ledger.empty:
        return {"sub_variant": sub_variant, "n_trades": 0, "passes": False,
                "reason": "no trades"}
    returns = (ledger["pnl_net_inr"].values / ledger["notional_total_inr"].values)
    wins = int((returns > 0).sum())
    n = int(len(returns))
    point, lo, hi = v4_stats.bootstrap_sharpe_ci(returns, seed=7)
    p_value = v4_stats.binomial_p(wins, n)
    alpha_per = v4_stats.bonferroni_alpha_per(0.01, BONFERRONI_N_TESTS)
    passes = lo > 0 and p_value < alpha_per
    return {
        "sub_variant": sub_variant, "n_trades": n, "wins": wins,
        "hit_rate": wins / n if n else 0.0, "sharpe_point": point,
        "sharpe_lo": lo, "sharpe_hi": hi, "binomial_p": p_value,
        "alpha_per_test": alpha_per, "passes": passes,
    }


def main(hold_days: int = 5) -> None:
    paths.ensure_cache()
    regime_df = _load_regime_history()
    log.info("loaded regime history: %d days (%s → %s)",
             len(regime_df),
             regime_df["date"].min().date() if not regime_df.empty else "?",
             regime_df["date"].max().date() if not regime_df.empty else "?")

    real_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    adapted = _adapt_profile(real_profile)
    log.info("adapted profile covers zones: %s", sorted(adapted.keys()))

    # ranker_backfill expects a file path — write the adapted profile to a
    # temporary location that persists for the duration of the run.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                      encoding="utf-8") as tmp:
        json.dump(adapted, tmp)
        adapted_path = Path(tmp.name)
    try:
        ranker_df = ranker_backfill.backfill_daily_top_n(
            profile_path=adapted_path,
            regime_history=regime_df,
            top_n=5,
            min_episodes=4, min_hit_rate=0.6,
        )
    finally:
        adapted_path.unlink(missing_ok=True)

    log.info("backfilled ranker rows: %d across %d days",
             len(ranker_df), ranker_df["date"].nunique() if not ranker_df.empty else 0)
    if ranker_df.empty:
        log.error("ranker backfill emitted zero rows — profile/regime/filter mismatch")
        return

    symbols = _unique_candidate_symbols(ranker_df)
    log.info("candidate symbols: %d", len(symbols))
    bars = _load_bars_bulk(symbols, days=1500)
    log.info("fetched bars for %d/%d symbols", len(bars), len(symbols))

    verdicts: list[dict] = []
    for sub in ("a", "b", "c", "d"):
        ledger = v50_regime_pair.run(
            ranker_df=ranker_df, symbol_bars=bars,
            sub_variant=sub, hold_days=hold_days,
        )
        ledger_path = paths.LEDGERS_DIR / f"v50_{sub}.parquet"
        ledger.to_parquet(ledger_path, index=False)
        log.info("wrote %s (%d trades)", ledger_path.name, len(ledger))
        verdicts.append(_verdict_row(ledger, sub))

    verdict_df = pd.DataFrame(verdicts)
    verdict_df.to_csv(paths.LEDGERS_DIR / "v50_verdicts.csv", index=False)
    print("\n=== V5.0 Verdicts ===")
    print(verdict_df.to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-days", type=int, default=5)
    args = parser.parse_args()
    main(hold_days=args.hold_days)
