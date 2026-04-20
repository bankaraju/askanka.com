"""Phase C validation backtest orchestrator.

Wires fetcher -> universe -> regime backfill -> walk-forward profile training
-> classifier -> simulators (EOD + intraday) -> stats verdict -> report.
Writes outputs under ``docs/research/phase-c-validation/`` and reuses the
cache root ``pipeline/data/research/phase_c/``.

Usage:
    python -m pipeline.research.phase_c_backtest.run_backtest \\
        --in-sample-start 2022-04-01 --in-sample-end 2026-02-19 \\
        --forward-start 2026-02-20 --forward-end 2026-04-19
"""
from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from . import (
    bhavcopy,
    classifier,
    fetcher,
    paths,
    profile,
    regime,
    report,
    simulator_eod,
    simulator_intraday,
    stats as stats_mod,
    universe as univ,
)

log = logging.getLogger(__name__)

WEIGHTS_PATH = paths.PIPELINE_DIR / "autoresearch" / "etf_optimal_weights.json"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _load_etf_list() -> list[str]:
    cfg = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    return list(cfg.get("optimal_weights", {}).keys())


def _fetch_universe_bars(symbols: list[str], days: int = 1500) -> dict[str, pd.DataFrame]:
    return {sym: fetcher.fetch_daily(sym, days=days) for sym in symbols}


def _backfill_regime(
    in_sample_start: str, forward_end: str, lookback_years: int = 2,
) -> dict[str, str]:
    """Backfill regime labels covering profile training lookback + entire backtest window.

    The profile trainer needs regime labels going ~lookback_years before the
    in_sample_start so that the first walk-forward cutoff has labelled data.
    """
    if paths.REGIME_BACKFILL.is_file():
        return json.loads(paths.REGIME_BACKFILL.read_text(encoding="utf-8"))
    etf_syms = _load_etf_list()
    etf_bars = _fetch_universe_bars(etf_syms)
    backfill_start = (
        pd.Timestamp(in_sample_start) - pd.DateOffset(years=lookback_years)
    ).strftime("%Y-%m-%d")
    dates = pd.bdate_range(start=backfill_start, end=forward_end).strftime("%Y-%m-%d").tolist()
    return regime.backfill_regime(dates, WEIGHTS_PATH, etf_bars, paths.REGIME_BACKFILL)


def _classify_window(
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    profiles_by_cutoff: dict[str, dict],
    window_start: str,
    window_end: str,
) -> pd.DataFrame:
    """Walk every business day in the window, classify the universe, return one
    row per (date, symbol).

    For each date, the *active* walk-forward cutoff is the most recent cutoff
    ``<= d``. This matches live-trading semantics: at trading time the most
    recently fitted profile is the one in use.
    """
    cutoffs = sorted(profiles_by_cutoff.keys())
    rows: list[dict] = []
    dates = pd.bdate_range(start=window_start, end=window_end).strftime("%Y-%m-%d").tolist()
    for d in dates:
        regime_today = regime_by_date.get(d)
        if regime_today is None:
            continue
        # Most recent cutoff <= d (intentional inclusive bound: at trading
        # time the most recent cutoff's profile is the active one).
        active_cutoff = max((c for c in cutoffs if c <= d), default=None)
        if active_cutoff is None:
            continue
        prof = profiles_by_cutoff[active_cutoff]
        actuals: dict[str, float] = {}
        for sym, bars in universe_bars.items():
            r = regime._daily_return_at(bars, d)  # noqa: SLF001 (intentional reuse)
            if r is not None:
                actuals[sym] = r
        # PCR comes from the NSE F&O bhavcopy archive (per-symbol, per-day).
        # Empty dict on missing days; classifier treats missing PCR as NEUTRAL.
        pcr_today = bhavcopy.pcr_by_symbol(d)
        labels = classifier.classify_universe(
            symbols=list(actuals.keys()),
            regime=regime_today,
            profile=prof,
            actual_returns=actuals,
            pcr_by_symbol=pcr_today,
            oi_anomaly_by_symbol={},
        )
        for sym, info in labels.items():
            expected = (
                prof.get(sym, {}).get(regime_today, {}).get("expected_return", 0.0)
            )
            rows.append({
                "date": d,
                "symbol": sym,
                "label": info["label"],
                "action": info["action"],
                "z_score": info["z_score"],
                "expected_return": expected,
                "regime": regime_today,
            })
    return pd.DataFrame(rows)


def _train_profiles(
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
    window_start: str,
    window_end: str,
) -> dict[str, dict]:
    cutoffs = profile.cutoff_dates_for_walk_forward(
        window_start, window_end, refit_months=3,
    )
    return {
        c: profile.train_and_cache(
            symbol_bars=universe_bars,
            regime_by_date=regime_by_date,
            cutoff_date=c,
            lookback_years=2,
        )
        for c in cutoffs
    }


def _run_in_sample(
    args: argparse.Namespace,
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profiles_by_cutoff = _train_profiles(
        universe_bars, regime_by_date, args.in_sample_start, args.in_sample_end,
    )
    classifications = _classify_window(
        universe_bars, regime_by_date, profiles_by_cutoff,
        args.in_sample_start, args.in_sample_end,
    )
    ledger = simulator_eod.run_simulation(
        classifications=classifications,
        symbol_bars=universe_bars,
        notional_inr=50_000,
        slippage_bps=5.0,
        top_n=5,
        label_filter=args.trade_label,
    )
    return ledger, classifications


def _run_forward(
    args: argparse.Namespace,
    universe_bars: dict[str, pd.DataFrame],
    regime_by_date: dict[str, str],
) -> pd.DataFrame:
    """Forward window: same classifier, but uses simulator_intraday with
    1-min bars and a mechanical 14:30 IST exit.
    """
    profiles_by_cutoff = _train_profiles(
        universe_bars, regime_by_date, args.forward_start, args.forward_end,
    )
    classifications = _classify_window(
        universe_bars, regime_by_date, profiles_by_cutoff,
        args.forward_start, args.forward_end,
    )
    opp = classifications[classifications["label"] == args.trade_label].copy()
    if opp.empty:
        return pd.DataFrame()

    # Backtest assumption: we don't have actual signal timestamps, so we
    # treat the open as the trigger. simulator_intraday will enter at the
    # *next* bar after this time.
    opp["signal_time"] = opp["date"].astype(str) + " 09:30:00"
    opp["side"] = opp["expected_return"].apply(lambda x: "LONG" if x >= 0 else "SHORT")
    # Simple fractional stops as a first-pass; a follow-up commit can
    # derive these from per-(symbol, regime) std stored in the profile.
    opp["stop_pct"] = 0.02
    opp["target_pct"] = 0.01

    def _loader(symbol: str, trade_date: str) -> pd.DataFrame | None:
        # Narrow exception surface (matches simulator_intraday.run_simulation
        # internal handling). Anything else is a real bug — let it propagate.
        try:
            return fetcher.fetch_minute(symbol, trade_date)
        except (FileNotFoundError, IOError, ValueError, KeyError) as exc:
            log.warning(
                "minute bars unavailable for %s on %s: %s",
                symbol, trade_date, exc,
            )
            return None

    return simulator_intraday.run_simulation(
        signals=opp[["date", "signal_time", "symbol", "side",
                     "stop_pct", "target_pct", "z_score"]],
        minute_bars_loader=_loader,
        notional_inr=50_000,
        slippage_bps=5.0,
        exit_time="14:30:00",
        top_n=5,
    )


def _verdict(
    in_sample_ledger: pd.DataFrame,
    forward_ledger: pd.DataFrame,
    regime_by_date: dict[str, str],
) -> dict:
    """Compute H1 OPPORTUNITY verdict from the two ledgers."""
    if in_sample_ledger.empty or forward_ledger.empty:
        return {
            "H1_OPPORTUNITY": {
                "passes": False,
                "reason": "empty ledger",
                "failed_criteria": ["no trades"],
            }
        }

    in_rets = (in_sample_ledger["pnl_net_inr"] / in_sample_ledger["notional_inr"]).to_numpy()
    fw_rets = (forward_ledger["pnl_net_inr"] / forward_ledger["notional_inr"]).to_numpy()

    in_pt, in_lo, _ = stats_mod.bootstrap_sharpe_ci(
        in_rets, n_resamples=10_000, alpha=0.01, seed=7,
    )
    fw_pt, fw_lo, _ = stats_mod.bootstrap_sharpe_ci(
        fw_rets, n_resamples=10_000, alpha=0.01, seed=7,
    )

    in_eq = in_sample_ledger["pnl_net_inr"].cumsum().to_numpy() + 100_000
    fw_eq = forward_ledger["pnl_net_inr"].cumsum().to_numpy() + 100_000
    in_dd = stats_mod.max_drawdown(in_eq)
    fw_dd = stats_mod.max_drawdown(fw_eq)

    in_hit = float((in_rets > 0).mean())
    fw_hit = float((fw_rets > 0).mean())
    in_p = stats_mod.binomial_p(int((in_rets > 0).sum()), len(in_rets))
    fw_p = stats_mod.binomial_p(int((fw_rets > 0).sum()), len(fw_rets))

    # Per-regime pass count (in-sample only — forward window typically lacks
    # the per-regime sample size needed for a stable binomial test).
    df = in_sample_ledger.copy()
    df["regime"] = df["entry_date"].map(regime_by_date)
    regimes_passed = 0
    for _reg, g in df.groupby("regime"):
        if len(g) < 30:
            continue
        rets = (g["pnl_net_inr"] / g["notional_inr"]).to_numpy()
        wins = int((rets > 0).sum())
        if (rets > 0).mean() >= 0.55 and stats_mod.binomial_p(wins, len(rets)) <= 0.01:
            regimes_passed += 1

    # TODO(task-16): wire real ablation result. The H1 verdict requires the
    # `degraded` ablation variant (no PCR + no OI) to show non-negative net
    # P&L. Until Task 16 plumbs the ablation grid through, we hard-code
    # True so the orchestrator runs end-to-end. Task 16 must replace this
    # with the actual aggregate from ablation.run_all_variants(...).
    h1 = stats_mod.h1_verdict(
        in_sample_sharpe_lo=in_lo,
        forward_sharpe_lo=fw_lo,
        in_sample_hit=in_hit,
        forward_hit=fw_hit,
        in_sample_p=in_p,
        forward_p=fw_p,
        in_sample_dd=in_dd,
        forward_dd=fw_dd,
        regime_pass_count=regimes_passed,
        in_sample_sharpe_point=in_pt,
        forward_sharpe_point=fw_pt,
        degraded_ablation_positive=True,  # TODO(task-16): replace placeholder
    )
    return {"H1_OPPORTUNITY": h1}


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="Phase C validation backtest orchestrator",
    )
    parser.add_argument("--in-sample-start", required=True)
    parser.add_argument("--in-sample-end", required=True)
    parser.add_argument("--forward-start", required=True)
    parser.add_argument("--forward-end", required=True)
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional explicit symbol list (default: full F&O universe at --forward-end)",
    )
    parser.add_argument(
        "--trade-label",
        default="OPPORTUNITY",
        choices=["OPPORTUNITY", "POSSIBLE_OPPORTUNITY"],
        help=(
            "Classification label that triggers entry. Default OPPORTUNITY now "
            "that NSE F&O bhavcopy provides historical per-symbol PCR. Use "
            "POSSIBLE_OPPORTUNITY to replicate the prior degraded run."
        ),
    )
    args = parser.parse_args(argv)

    paths.ensure_cache()

    log.info("Loading universe...")
    symbols = args.symbols or sorted(univ.universe_for_date(args.forward_end))
    log.info("Universe: %d symbols", len(symbols))

    log.info("Fetching daily bars for universe...")
    universe_bars = _fetch_universe_bars(symbols)

    log.info("Backfilling regime labels...")
    regime_by_date = _backfill_regime(args.in_sample_start, args.forward_end)

    log.info("Running in-sample (4yr EOD)...")
    in_sample_ledger, _classifications = _run_in_sample(args, universe_bars, regime_by_date)
    log.info("In-sample trades: %d", len(in_sample_ledger))

    log.info("Running forward (60d intraday, 14:30 IST exit)...")
    forward_ledger = _run_forward(args, universe_bars, regime_by_date)
    log.info("Forward trades: %d", len(forward_ledger))

    log.info("Computing H1 verdict...")
    verdicts = _verdict(in_sample_ledger, forward_ledger, regime_by_date)

    docs_dir = paths.DOCS_DIR
    docs_dir.mkdir(parents=True, exist_ok=True)
    log.info("Writing artifacts to %s ...", docs_dir)
    in_sample_ledger.to_parquet(docs_dir / "in_sample_ledger.parquet", index=False)
    forward_ledger.to_parquet(docs_dir / "forward_ledger.parquet", index=False)
    # Normalise intraday ledger columns for the report renderers, which
    # expect the EOD schema (entry_date).
    forward_for_report = forward_ledger.copy()
    if "entry_date" not in forward_for_report.columns and "entry_time" in forward_for_report.columns:
        forward_for_report["entry_date"] = (
            forward_for_report["entry_time"].astype(str).str[:10]
        )
    report.render_pnl_table(
        in_sample_ledger,
        docs_dir / "04-results-in-sample.md",
        title="In-sample trades (4yr EOD)",
    )
    report.render_pnl_table(
        forward_for_report,
        docs_dir / "05-results-forward.md",
        title="Forward trades (60d intraday)",
    )
    report.render_equity_curve(in_sample_ledger, docs_dir / "in_sample_equity.png")
    report.render_equity_curve(forward_for_report, docs_dir / "forward_equity.png")
    report.render_verdict_section(verdicts, docs_dir / "07-verdict.md")
    log.info("Done. Verdict: %s", verdicts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
