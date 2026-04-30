"""v2 mechanical-replay orchestrator — full deterministic reconstruction.

Pipeline:
  1. Reconstruct daily regime tags from canonical ETF parquets + frozen
     weights + frozen quintile cutpoints.
  2. Reconstruct Phase C roster from canonical bars + reconstructed regime.
  3. Reconstruct Phase B basket on regime-transition days only.
  4. Reconstruct spread book from canonical bars + pair config + regime gate.
  5. For Phase C and Phase B trades, run the v1 simulator on minute bars,
     populating Z_CROSS via per-minute peer-residual recompute against
     sectoral indices.
  6. Cross-check regenerated regime + Phase C roster against live disk
     state (`regime_history.csv`, `correlation_break_history.json`).
  7. Emit per-engine roster CSVs + combined trades_with_exit.csv +
     v2 markdown one-pager + engine_summary.json.

Spec: docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md

Usage:
  python -m pipeline.autoresearch.mechanical_replay.runner_v2 \
    --window-start 2026-02-24 --window-end 2026-04-24 \
    [--limit 5] [--no-fetch] [--out-dir <path>]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay import (
    atr,
    canonical_loader,
    constants as C,
    report,
    simulator,
)
from pipeline.autoresearch.mechanical_replay.reconstruct import (
    phase_b as recon_phase_b,
    phase_c as recon_phase_c,
    regime as recon_regime,
    spread as recon_spread,
    zcross as recon_zcross,
)

try:
    from pipeline.autoresearch.phase_c_shape_audit import fetcher as sp1_fetcher
    from pipeline.autoresearch.phase_c_shape_audit import constants as sp1_const
except ImportError:
    sp1_fetcher = None
    sp1_const = None

try:
    from pipeline.scorecard_v2.sector_mapper import SectorMapper
except ImportError:
    SectorMapper = None  # type: ignore


def _load_sector_by_ticker() -> dict[str, str]:
    """Build {ticker: sector} via SectorMapper, gracefully degrade on import fail."""
    if SectorMapper is None:
        logger.warning("SectorMapper unavailable — Phase C rows will have null sector")
        return {}
    try:
        m = SectorMapper().map_all()
        return {t: v.get("sector") for t, v in m.items() if v.get("sector")}
    except Exception as exc:
        logger.warning("SectorMapper.map_all failed: %s", exc)
        return {}

logger = logging.getLogger("mechanical_replay.v2")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


_V2_DATA_DIR = C._REPO / "pipeline" / "data" / "research" / "mechanical_replay" / "v2"
_V2_REPORT_MD = (
    C._REPO / "docs" / "research" / "mechanical_replay" / "2026-04-25-replay-60day-v2.md"
)


# ---------------------------------------------------------------------------
# Reconstruction step
# ---------------------------------------------------------------------------

def reconstruct_all(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    loader: canonical_loader.CanonicalLoader,
    pair_config: list[dict],
) -> dict[str, pd.DataFrame]:
    """Run all four engine reconstructions, return roster dict."""
    rosters: dict[str, pd.DataFrame] = {}

    logger.info("v2 T1 — regenerating regime tags…")
    weights, cutpoints = recon_regime.load_canonical_inputs()
    etf_bars = recon_regime.load_canonical_etf_bars(weights=weights)
    # Phase C profile training needs lookback_years=2 of regime history before
    # the first walk-forward cutoff. Regenerate over the full historical span
    # so train_profile sees regime tags for every date in the lookback window.
    regime_full_df = recon_regime.regenerate(
        window_start=window_start - pd.DateOffset(years=2, days=30),
        window_end=window_end,
        weights=weights,
        cutpoints=cutpoints,
        etf_bars=etf_bars,
    )
    # Roster artifact: only the replay window (with small warmup for
    # transitions). Full history stays internal for profile training.
    regime_df = regime_full_df[
        regime_full_df["date"] >= (window_start - pd.Timedelta(days=10))
    ].reset_index(drop=True)
    rosters["regime"] = regime_df
    regime_by_date = {
        pd.Timestamp(d).strftime("%Y-%m-%d"): zone
        for d, zone in zip(regime_full_df["date"], regime_full_df["regime_zone"])
    }
    logger.info(
        "  → %d regime rows in window (%d total incl. lookback)",
        len(regime_df), len(regime_full_df),
    )

    logger.info("v2 T2 — regenerating Phase C roster…")
    universe_bars: dict[str, pd.DataFrame] = {}
    for ticker in sorted(loader.universe):
        try:
            df = loader.daily_bars(ticker)
            if not df.empty:
                universe_bars[ticker] = df
        except Exception as exc:
            logger.warning("  bars unavailable for %s: %s", ticker, exc)
    logger.info("  loaded daily bars for %d/%d tickers",
                len(universe_bars), len(loader.universe))
    pcr_by_date = recon_phase_c.load_pcr_history(window_start, window_end)
    n_pcr_days = len(pcr_by_date)
    n_pcr_symbol_avg = (
        int(sum(len(v) for v in pcr_by_date.values()) / max(n_pcr_days, 1))
        if pcr_by_date else 0
    )
    logger.info(
        "  loaded PCR archive: %d days, ~%d symbols/day",
        n_pcr_days, n_pcr_symbol_avg,
    )
    sector_by_ticker = _load_sector_by_ticker()
    n_sec_mapped = sum(
        1 for t in universe_bars if sector_by_ticker.get(t) in C.SECTOR_TO_INDEX
    )
    logger.info(
        "  sector map: %d/%d tickers map to a sectoral index",
        n_sec_mapped, len(universe_bars),
    )
    phase_c_full = recon_phase_c.regenerate(
        window_start=window_start,
        window_end=window_end,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        pcr_by_date=pcr_by_date,
        sector_by_ticker=sector_by_ticker,
        actionable_only=False,
    )
    # Without per-day PCR archive (a §14 contamination), `classify_break`
    # defaults PCR to NEUTRAL, which keeps most rows at POSSIBLE_OPPORTUNITY
    # rather than OPPORTUNITY_LAG. We retain BOTH labels in the roster so
    # the artifact captures every event the engine would have considered.
    if phase_c_full.empty or "classification" not in phase_c_full.columns:
        logger.info("  → 0 Phase C rows (regenerate returned empty)")
        rosters["phase_c"] = pd.DataFrame(columns=[
            "date", "ticker", "classification", "z_score", "trade_rec",
            "regime", "sector", "signal_id", "expected_return",
            "actual_return", "event_geometry",
        ])
    else:
        phase_c_df = phase_c_full[
            phase_c_full["classification"].isin({"OPPORTUNITY_LAG", "POSSIBLE_OPPORTUNITY"})
        ].copy()
        # Synthesize trade_rec for POSSIBLE_OPPORTUNITY rows (matches LAG geometry):
        # if expected_return > 0 → LONG (FOLLOW the peer up), else SHORT.
        mask_no_rec = phase_c_df["trade_rec"].isna() & (
            phase_c_df["classification"] == "POSSIBLE_OPPORTUNITY"
        )
        phase_c_df.loc[mask_no_rec, "trade_rec"] = phase_c_df.loc[mask_no_rec, "expected_return"].apply(
            lambda x: "LONG" if x > 0 else "SHORT"
        )
        rosters["phase_c"] = phase_c_df.reset_index(drop=True)
        n_lag = int((phase_c_df["classification"] == "OPPORTUNITY_LAG").sum())
        n_pos = int((phase_c_df["classification"] == "POSSIBLE_OPPORTUNITY").sum())
        n_full = int(len(phase_c_full))
        logger.info(
            "  → %d Phase C rows (of %d total events; LAG=%d, POSSIBLE=%d — POSSIBLE under NEUTRAL-PCR)",
            len(phase_c_df), n_full, n_lag, n_pos,
        )

    logger.info("v2 T3 — regenerating Phase B basket on transition days…")
    phase_b_df = recon_phase_b.regenerate(regime_history=regime_df)
    if not phase_b_df.empty:
        phase_b_df = phase_b_df[
            (phase_b_df["date"] >= window_start) & (phase_b_df["date"] <= window_end)
        ].reset_index(drop=True)
    rosters["phase_b"] = phase_b_df
    logger.info("  → %d Phase B basket rows", len(phase_b_df))

    logger.info("v2 T4 — regenerating spread book…")
    spread_df = recon_spread.regenerate(
        window_start=window_start,
        window_end=window_end,
        pairs=pair_config,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        entry_threshold=2.0,
        lookback_days=60,
    )
    rosters["spread"] = spread_df
    logger.info("  → %d spread evaluations (%d gate-OPEN)",
                len(spread_df),
                int((spread_df.get("gate_status") == "OPEN").sum()) if not spread_df.empty else 0)

    return rosters, universe_bars


# ---------------------------------------------------------------------------
# Cross-check vs live state
# ---------------------------------------------------------------------------

def cross_check_regime(rosters: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Compare regenerated regime tags vs live regime_history.csv."""
    regime_df = rosters.get("regime")
    if regime_df is None or regime_df.empty:
        return {"pass": None, "note": "no regenerated regime rows"}
    if not C.REGIME_HISTORY_CSV.exists():
        return {"pass": None, "note": "regime_history.csv missing"}
    live = pd.read_csv(C.REGIME_HISTORY_CSV, parse_dates=["date"])
    live = live[["date", "regime_zone"]].rename(columns={"regime_zone": "live_zone"})
    regen = regime_df[["date", "regime_zone"]].rename(columns={"regime_zone": "regen_zone"})
    regen["date"] = pd.to_datetime(regen["date"])
    merged = live.merge(regen, on="date", how="inner")
    if merged.empty:
        return {"pass": None, "note": "no overlap"}
    agree = (merged["live_zone"] == merged["regen_zone"]).mean() * 100
    return {
        "n_overlap": int(len(merged)),
        "agreement_pct": round(float(agree), 2),
        "threshold_pct": 98.0,
        "pass": agree >= 98.0,
    }


def cross_check_phase_c_roster(rosters: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Compare regenerated Phase C roster vs live correlation_break_history.json.

    Match key: (ticker, date). Counts how many regenerated (ticker, date) pairs
    appear in the live history.
    """
    pc = rosters.get("phase_c")
    if pc is None or pc.empty:
        return {"pass": None, "note": "no regenerated Phase C rows"}
    if not C.BREAK_HISTORY_JSON.exists():
        return {"pass": None, "note": "correlation_break_history.json missing"}
    try:
        live_payload = json.loads(C.BREAK_HISTORY_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"pass": None, "note": f"could not parse live history: {exc}"}
    live_breaks = live_payload if isinstance(live_payload, list) else live_payload.get("breaks", [])
    live_keys: set[tuple[str, str]] = set()
    for b in live_breaks:
        sym = b.get("symbol")
        d = b.get("date") or b.get("scan_date")
        if sym and d:
            live_keys.add((sym, str(d)[:10]))
    regen_keys = {
        (str(r["ticker"]), pd.Timestamp(r["date"]).strftime("%Y-%m-%d"))
        for _, r in pc.iterrows()
    }
    if not regen_keys:
        return {"pass": None, "note": "no regenerated keys"}
    intersection = regen_keys & live_keys
    overlap_pct = len(intersection) / len(regen_keys) * 100
    return {
        "n_regen": int(len(regen_keys)),
        "n_live": int(len(live_keys)),
        "n_overlap": int(len(intersection)),
        "agreement_pct": round(float(overlap_pct), 2),
        "threshold_pct": 95.0,
        "pass": overlap_pct >= 95.0,
    }


# ---------------------------------------------------------------------------
# Per-engine simulation
# ---------------------------------------------------------------------------

def _stop_pct_for_row(
    loader: canonical_loader.CanonicalLoader, ticker: str,
    trade_date: pd.Timestamp, side: Optional[str],
) -> dict:
    if side not in ("LONG", "SHORT"):
        return {"stop_pct": C.ATR_FALLBACK_PCT, "atr_14": None, "stop_source": "fallback_no_side"}
    daily = loader.daily_bars(ticker)
    cutoff = pd.Timestamp(trade_date).normalize() - pd.Timedelta(days=1)
    df_pre = daily[daily["date"] <= cutoff]
    if df_pre.empty:
        return {"stop_pct": C.ATR_FALLBACK_PCT, "atr_14": None, "stop_source": "fallback_no_history"}
    return atr.compute_stop(df_pre, side=side, profile="intraday")


def _fetch_minute_bars(
    ticker: str, trade_date: pd.Timestamp, *, no_fetch: bool, bars_dir: Path,
) -> Optional[pd.DataFrame]:
    if sp1_fetcher is None:
        return None
    try:
        if no_fetch:
            cache_path = sp1_fetcher._cache_path(bars_dir, ticker, trade_date.date())
            if not cache_path.exists():
                return None
            return pd.read_parquet(cache_path)
        return sp1_fetcher.fetch_minute_bars(
            ticker=ticker, trade_date=trade_date.date(), bars_dir=bars_dir,
        )
    except Exception as exc:
        logger.warning("minute fetch failed for %s on %s: %s", ticker, trade_date.date(), exc)
        return None


def _zcross_for_phase_c_trade(
    *,
    ticker: str,
    sector: Optional[str],
    side: str,
    minute_bars: pd.DataFrame,
    loader: canonical_loader.CanonicalLoader,
    trade_date: pd.Timestamp,
    no_fetch: bool,
    bars_dir: Path,
) -> Optional[pd.Timestamp]:
    """Compute Z_CROSS exit minute for one Phase C trade."""
    if not sector or sector not in C.SECTOR_TO_INDEX:
        return None
    index_name = C.SECTOR_TO_INDEX[sector]
    sector_bars = _fetch_minute_bars(
        index_name, trade_date, no_fetch=no_fetch, bars_dir=bars_dir,
    )
    if sector_bars is None or sector_bars.empty:
        return None
    entry_sign = +1 if side == "LONG" else -1
    return recon_zcross.find_zcross_minute(
        stock_minute_bars=minute_bars,
        sector_minute_bars=sector_bars,
        entry_sign=entry_sign,
        rolling_window=30,
    )


def simulate_phase_c_trades(
    *,
    phase_c_roster: pd.DataFrame,
    loader: canonical_loader.CanonicalLoader,
    bars_dir: Path,
    no_fetch: bool,
    enable_zcross: bool = True,
) -> list[dict]:
    """Walk each Phase C row, simulate one trade. Mirrors v1 runner with
    Z_CROSS exit channel populated."""
    trades: list[dict] = []
    for _, row in phase_c_roster.iterrows():
        ticker = row["ticker"]
        trade_date = pd.Timestamp(row["date"])
        side = row.get("trade_rec")
        if side not in ("LONG", "SHORT"):
            continue
        stop = _stop_pct_for_row(loader, ticker, trade_date, side)
        bars = _fetch_minute_bars(
            ticker, trade_date, no_fetch=no_fetch, bars_dir=bars_dir,
        )
        if bars is None or bars.empty:
            trades.append({
                "engine": "phase_c", "signal_id": row.get("signal_id"),
                "ticker": ticker, "date": trade_date,
                "regime": row.get("regime"), "side": side,
                "classification": row.get("classification"),
                "exit_reason": "FETCH_FAILED",
                "pnl_pct": np.nan, "mfe_pct": np.nan,
                "entry_time": None, "exit_time": None,
                "entry_price": None, "exit_price": None,
                "stop_pct": stop["stop_pct"], "atr_14": stop["atr_14"],
                "stop_source": stop["stop_source"],
                "actual_pnl_pct": None,
            })
            continue
        zcross_time = None
        if enable_zcross:
            zcross_time = _zcross_for_phase_c_trade(
                ticker=ticker, sector=row.get("sector"), side=side,
                minute_bars=bars, loader=loader, trade_date=trade_date,
                no_fetch=no_fetch, bars_dir=bars_dir,
            )
        trade = simulator.simulate_one_trade(
            bars=bars, side=side, stop_pct=stop["stop_pct"],
            zcross_time=zcross_time,
        )
        trades.append({
            "engine": "phase_c", "signal_id": row.get("signal_id"),
            "ticker": ticker, "date": trade_date,
            "regime": row.get("regime"), "side": side,
            "classification": row.get("classification"),
            "exit_reason": trade["exit_reason"],
            "pnl_pct": trade["pnl_pct"], "mfe_pct": trade.get("mfe_pct"),
            "entry_time": trade.get("entry_time"), "exit_time": trade.get("exit_time"),
            "entry_price": trade.get("entry_price"), "exit_price": trade.get("exit_price"),
            "stop_pct": stop["stop_pct"], "atr_14": stop["atr_14"],
            "stop_source": stop["stop_source"],
            "actual_pnl_pct": None,
            "zcross_used": zcross_time is not None,
        })
    return trades


def simulate_phase_b_trades(
    *,
    phase_b_roster: pd.DataFrame,
    loader: canonical_loader.CanonicalLoader,
    bars_dir: Path,
    no_fetch: bool,
) -> list[dict]:
    """Walk each Phase B basket entry, simulate one trade per (date, ticker, side)."""
    trades: list[dict] = []
    for _, row in phase_b_roster.iterrows():
        ticker = row["ticker"]
        trade_date = pd.Timestamp(row["date"])
        side = row["side"]
        stop = _stop_pct_for_row(loader, ticker, trade_date, side)
        bars = _fetch_minute_bars(
            ticker, trade_date, no_fetch=no_fetch, bars_dir=bars_dir,
        )
        if bars is None or bars.empty:
            trades.append({
                "engine": "phase_b", "signal_id": f"PHB-{trade_date.strftime('%Y-%m-%d')}-{ticker}",
                "ticker": ticker, "date": trade_date,
                "regime": row.get("regime"), "side": side,
                "classification": row.get("transition"),
                "exit_reason": "FETCH_FAILED",
                "pnl_pct": np.nan, "mfe_pct": np.nan,
                "entry_time": None, "exit_time": None,
                "entry_price": None, "exit_price": None,
                "stop_pct": stop["stop_pct"], "atr_14": stop["atr_14"],
                "stop_source": stop["stop_source"],
                "actual_pnl_pct": None,
            })
            continue
        trade = simulator.simulate_one_trade(
            bars=bars, side=side, stop_pct=stop["stop_pct"], zcross_time=None,
        )
        trades.append({
            "engine": "phase_b", "signal_id": f"PHB-{trade_date.strftime('%Y-%m-%d')}-{ticker}",
            "ticker": ticker, "date": trade_date,
            "regime": row.get("regime"), "side": side,
            "classification": row.get("transition"),
            "exit_reason": trade["exit_reason"],
            "pnl_pct": trade["pnl_pct"], "mfe_pct": trade.get("mfe_pct"),
            "entry_time": trade.get("entry_time"), "exit_time": trade.get("exit_time"),
            "entry_price": trade.get("entry_price"), "exit_price": trade.get("exit_price"),
            "stop_pct": stop["stop_pct"], "atr_14": stop["atr_14"],
            "stop_source": stop["stop_source"],
            "actual_pnl_pct": None,
        })
    return trades


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _load_pair_config() -> list[dict]:
    """Read the canonical pair list from pipeline/config.py::INDIA_SPREAD_PAIRS."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(C._REPO / "pipeline"))
        import config as _cfg  # type: ignore
        return list(_cfg.INDIA_SPREAD_PAIRS)
    except Exception as exc:
        logger.warning("could not load INDIA_SPREAD_PAIRS — falling back to []: %s", exc)
        return []


def run(
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    limit: Optional[int] = None,
    no_fetch: bool = False,
    out_dir: Path = _V2_DATA_DIR,
    bars_dir: Optional[Path] = None,
) -> dict:
    if bars_dir is None:
        bars_dir = sp1_const.BARS_DIR if sp1_const is not None else C.SP1_BARS_DIR
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading canonical universe…")
    loader = canonical_loader.CanonicalLoader()
    pair_config = _load_pair_config()
    rosters, _universe_bars = reconstruct_all(
        window_start=window_start, window_end=window_end,
        loader=loader, pair_config=pair_config,
    )

    logger.info("Cross-checking vs live state…")
    cross_check = {
        "regime_vs_history_csv": cross_check_regime(rosters),
        "phase_c_roster_vs_history_json": cross_check_phase_c_roster(rosters),
    }
    logger.info("  cross-check: %s", json.dumps(cross_check, default=str))

    pc_roster = rosters.get("phase_c", pd.DataFrame())
    pb_roster = rosters.get("phase_b", pd.DataFrame())
    if limit is not None:
        if not pc_roster.empty:
            pc_roster = pc_roster.head(limit).copy()
        if not pb_roster.empty:
            pb_roster = pb_roster.head(limit).copy()

    logger.info("Simulating Phase C trades (%d roster rows)…", len(pc_roster))
    pc_trades = simulate_phase_c_trades(
        phase_c_roster=pc_roster, loader=loader, bars_dir=bars_dir,
        no_fetch=no_fetch, enable_zcross=True,
    )
    logger.info("Simulating Phase B trades (%d basket rows)…", len(pb_roster))
    pb_trades = simulate_phase_b_trades(
        phase_b_roster=pb_roster, loader=loader, bars_dir=bars_dir, no_fetch=no_fetch,
    )

    trades = pc_trades + pb_trades
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    if not trades_df.empty:
        trades_df = (
            trades_df.sort_values("pnl_pct", na_position="last")
                     .drop_duplicates(subset=["engine", "ticker", "date", "side"], keep="first")
                     .sort_values(["date", "engine", "ticker"])
                     .reset_index(drop=True)
        )

    logger.info("Writing per-engine roster CSVs…")
    zcross_rows = []
    for t in pc_trades:
        if t.get("zcross_used") and t.get("exit_time") is not None:
            zcross_rows.append({
                "signal_id": t.get("signal_id"), "ticker": t["ticker"],
                "date": t["date"], "exit_time": t.get("exit_time"),
                "side": t["side"], "exit_reason": t.get("exit_reason"),
            })
    rosters["zcross_times"] = pd.DataFrame(zcross_rows)

    paths_written = report.write_per_engine_rosters(rosters, out_dir)
    trades_csv = out_dir / "trades_with_exit.csv"
    trades_df.to_csv(trades_csv, index=False)

    valid = trades_df.dropna(subset=["pnl_pct"]).copy() if not trades_df.empty else trades_df
    summary = report.build_engine_summary(valid)
    cube = report.build_regime_cube(valid)
    checks = report.run_sanity_checks(
        trades=valid,
        total_signals_in_window=len(trades_df) if not trades_df.empty else 0,
        coverage_threshold_pct=C.COVERAGE_THRESHOLD_PCT,
    )

    report.write_engine_summary(summary, out_dir / "engine_summary.json")
    report.write_v2_one_pager(
        summary=summary, cube=cube, checks=checks, trades=valid,
        cross_check=cross_check, rosters=rosters,
        window_start=window_start, window_end=window_end,
        out_path=_V2_REPORT_MD,
    )
    logger.info("Wrote %s", _V2_REPORT_MD)
    logger.info("Wrote %d trades → %s", len(trades_df), trades_csv)

    return {
        "summary": summary, "cross_check": cross_check,
        "n_trades": int(len(trades_df)),
        "n_valid": int(len(valid)) if not valid.empty else 0,
        "rosters_written": {k: str(v) for k, v in paths_written.items()},
        "checks": checks,
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Mechanical 60-day replay v2 — full reconstruction.")
    p.add_argument("--window-start", default="2026-02-24")
    p.add_argument("--window-end", default="2026-04-24")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--out-dir", default=str(_V2_DATA_DIR))
    args = p.parse_args(argv)

    run(
        window_start=pd.Timestamp(args.window_start),
        window_end=pd.Timestamp(args.window_end),
        limit=args.limit, no_fetch=args.no_fetch,
        out_dir=Path(args.out_dir),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
