"""Seed daily-bar cache for all V5.0 candidate symbols via yfinance.

Usage:
    python -m pipeline.research.phase_c_v5.seed_candidate_bars [--dry-run]

Resolves the full candidate-symbol set the V5.0 ranker would emit for any
historical day (top_n=5, min_episodes=4, min_hit_rate=0.6), then fetches 4
years of daily OHLCV for any symbol not already cached in V4's daily_bars
directory.

Fallback chain per symbol:
  1. yfinance  <SYM>.NS
  2. Local CSV at pipeline/data/india_historical/<SYM>.csv
     (schema: Date,Open,High,Low,Close,Volume)

Symbols with < 500 rows after fetch are skipped (insufficient history).
"""
from __future__ import annotations

import argparse
import json
import logging
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
from pipeline.research.phase_c_v5 import paths as v5paths, run_v50, ranker_backfill
from pipeline.research.phase_c_backtest import paths as v4paths

DAILY_BARS_DIR = v4paths.DAILY_BARS_DIR
LOCAL_CSV_DIR = v5paths.PIPELINE_DIR / "data" / "india_historical"

# Known symbol aliases: Kite name → yfinance name (.NS appended automatically)
KITE_TO_YFINANCE: dict[str, str] = {
    "LTM": "LTIMINDTREE",
    "NUVAMA": "NUVAMA",  # explicit identity — listed on NSE as NUVAMA
    "SAMMAANCAP": "SAMMAANCAP",
}

MIN_ROWS = 500  # skip symbols with insufficient history

log = logging.getLogger("seed_candidate_bars")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ── Candidate resolution ───────────────────────────────────────────────────

def resolve_candidates(top_n: int = 5, min_episodes: int = 4, min_hit_rate: float = 0.6) -> list[str]:
    """Return sorted list of every unique symbol the V5.0 ranker can emit."""
    profile_path = v5paths.PIPELINE_DIR / "autoresearch" / "reverse_regime_profile.json"
    real_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    adapted = run_v50._adapt_profile(real_profile)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     encoding="utf-8") as tmp:
        json.dump(adapted, tmp)
        adapted_path = Path(tmp.name)
    try:
        regime_df = run_v50._load_regime_history()
        ranker_df = ranker_backfill.backfill_daily_top_n(
            profile_path=adapted_path,
            regime_history=regime_df,
            top_n=top_n,
            min_episodes=min_episodes,
            min_hit_rate=min_hit_rate,
        )
    finally:
        adapted_path.unlink(missing_ok=True)

    if ranker_df.empty:
        log.error("ranker backfill returned zero rows — check profile/regime files")
        return []

    symbols = sorted(set(ranker_df["symbol"].tolist()))
    log.info("candidate symbols total: %d", len(symbols))
    log.info("zone distribution in ranker output: %s",
             ranker_df["zone"].value_counts().to_dict())
    return symbols


# ── Fetch helpers ──────────────────────────────────────────────────────────

def _fetch_yfinance(kite_sym: str, start: str, end: str) -> pd.DataFrame | None:
    """Fetch via yfinance. Returns normalised DataFrame or None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed — pip install yfinance")
        return None

    yf_sym = KITE_TO_YFINANCE.get(kite_sym, kite_sym) + ".NS"
    try:
        raw = yf.download(yf_sym, start=start, end=end, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            log.warning("yfinance returned empty for %s", yf_sym)
            return None

        # yfinance single-ticker returns flat columns; multi-ticker returns MultiIndex
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)

        raw = raw.reset_index()

        # Normalise column names to lowercase
        raw.columns = [c.lower() for c in raw.columns]

        # Ensure required columns exist
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(raw.columns)):
            log.warning("yfinance columns unexpected for %s: %s", yf_sym, list(raw.columns))
            return None

        df = raw[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.sort_values("date").reset_index(drop=True)
        return df

    except Exception as exc:
        log.warning("yfinance fetch failed for %s: %s", yf_sym, exc)
        return None


def _fetch_local_csv(kite_sym: str) -> pd.DataFrame | None:
    """Fallback: read from pipeline/data/india_historical/<SYM>.csv."""
    csv_path = LOCAL_CSV_DIR / f"{kite_sym}.csv"
    if not csv_path.is_file():
        return None
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.lower() for c in df.columns]
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            log.warning("local CSV for %s has unexpected columns: %s", kite_sym, list(df.columns))
            return None
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df = df.sort_values("date").reset_index(drop=True)
        log.info("local CSV hit for %s (%d rows)", kite_sym, len(df))
        return df
    except Exception as exc:
        log.warning("local CSV read failed for %s: %s", kite_sym, exc)
        return None


def fetch_bars(kite_sym: str, years: int = 4) -> pd.DataFrame | None:
    """Fetch bars for one symbol. Returns normalised DataFrame or None."""
    end = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=years * 366)).strftime("%Y-%m-%d")

    df = _fetch_yfinance(kite_sym, start=start, end=end)
    if df is not None and not df.empty:
        return df

    df = _fetch_local_csv(kite_sym)
    return df


# ── Main seed logic ────────────────────────────────────────────────────────

def seed(dry_run: bool = False) -> None:
    v5paths.ensure_cache()
    DAILY_BARS_DIR.mkdir(parents=True, exist_ok=True)

    candidates = resolve_candidates()
    if not candidates:
        log.error("no candidate symbols found — aborting")
        return

    cached = {p.stem for p in DAILY_BARS_DIR.glob("*.parquet")}
    missing = sorted(set(candidates) - cached)

    log.info("candidates: %d | already cached: %d | need seeding: %d",
             len(candidates), len(cached & set(candidates)), len(missing))

    if not missing:
        log.info("all candidate symbols already cached — nothing to do")
        return

    if dry_run:
        log.info("DRY-RUN — would seed: %s", missing)
        return

    seeded: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for i, sym in enumerate(missing, start=1):
        log.info("[%d/%d] seeding %s …", i, len(missing), sym)
        df = fetch_bars(sym)
        if df is None or df.empty:
            log.warning("  FAILED: no data for %s", sym)
            failed.append(sym)
        elif len(df) < MIN_ROWS:
            log.warning("  SKIPPED: only %d rows for %s (< %d)", len(df), sym, MIN_ROWS)
            skipped.append(sym)
        else:
            out_path = DAILY_BARS_DIR / f"{sym}.parquet"
            df.to_parquet(out_path, index=False)
            log.info("  seeded %s → %s (%d rows, %s → %s)",
                     sym, out_path.name, len(df),
                     df["date"].min().date(), df["date"].max().date())
            seeded.append(sym)

        # Rate-limit yfinance
        if i < len(missing):
            time.sleep(0.5)

    log.info("=== SEED COMPLETE ===")
    log.info("seeded: %d | skipped: %d | failed: %d", len(seeded), len(skipped), len(failed))
    if skipped:
        log.warning("skipped (< %d rows): %s", MIN_ROWS, skipped)
    if failed:
        log.warning("failed (no data): %s", failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed V5.0 candidate bars via yfinance")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report missing symbols without fetching")
    args = parser.parse_args()
    seed(dry_run=args.dry_run)
