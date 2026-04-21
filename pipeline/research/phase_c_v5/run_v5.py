# pipeline/research/phase_c_v5/run_v5.py
"""End-to-end V5 orchestrator.

Loads Phase C V4 classifications as the signal source for V5.1-V5.7.
V5.0 uses the reverse-regime profile directly (independent of Phase C).

NOTE: Phase C V4 ledger (opportunity_signals.parquet) was not present at
implementation time (pipeline/data/research/phase_c/ contains only bar
caches, no classified signals).  When Task 22 (V5.1 full backtest) is
complete and the forward-test ledger has been promoted, place the parquet at
PHASE_C_V4_LEDGER and re-run with --force.  Until then, V5.1-V5.7 are
gracefully skipped.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_v5 import paths, ablation, report
from pipeline.research.phase_c_v5 import run_v50
from pipeline.research.phase_c_v5 import basket_builder
from pipeline.research.phase_c_v5 import intraday_basket_simulator
from pipeline.research.phase_c_v5.variants import (
    v51_sector_pair, v52_stock_vs_index, v53_nifty_overlay,
    v54_banknifty_dispersion, v55_leader_routing,
    v56_horizon_sweep, v57_options_overlay,
)
from pipeline.research.phase_c_backtest import fetcher

log = logging.getLogger("v5")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# V4 classified OPPORTUNITY signals — produced by the Phase C forward-test
# ledger (pipeline/data/research/phase_c/opportunity_signals.parquet).
# If the file does not yet exist, V5.1-V5.7 are skipped gracefully.
PHASE_C_V4_LEDGER = paths.PIPELINE_DIR / "data" / "research" / "phase_c" / "opportunity_signals.parquet"


def _load_phase_c_signals() -> pd.DataFrame:
    if not PHASE_C_V4_LEDGER.is_file():
        log.warning("Phase C V4 ledger missing at %s — V5.1-V5.7 will be skipped",
                    PHASE_C_V4_LEDGER)
        return pd.DataFrame()
    return pd.read_parquet(PHASE_C_V4_LEDGER)


def _run_variant(name: str, func, force: bool, **kwargs) -> pd.DataFrame:
    out_path = paths.LEDGERS_DIR / f"{name}.parquet"
    if out_path.is_file() and not force:
        log.info("%s: ledger present, skipping (use --force to rerun)", name)
        return pd.read_parquet(out_path)
    log.info("running %s...", name)
    ledger = func(**kwargs)
    ledger.to_parquet(out_path, index=False)
    log.info("%s: wrote %d trades to %s", name, len(ledger), out_path.name)
    return ledger


def _load_all_bars(symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        try:
            out[s] = fetcher.fetch_daily(s, days=1500)
        except Exception as exc:
            log.warning("bar fetch failed %s: %s", s, exc)
    return out


def main(force: bool = False) -> None:
    paths.ensure_cache()
    # V5.0 first — the MOAT
    run_v50.main(hold_days=5)

    signals = _load_phase_c_signals()
    if signals.empty:
        log.warning("no Phase C signals — skipping V5.1-V5.7")
    else:
        symbols = sorted(set(signals["symbol"].astype(str).tolist()))
        extras = ["NIFTY", "BANKNIFTY", "NIFTYIT", "FINNIFTY"]
        bars = _load_all_bars(symbols + extras)

        # V5.1 needs 1-min bars per signal-day — skip at this pass if not cached
        pairs = basket_builder.build_sector_pairs(signals)
        log.info("v51 pair candidates: %d", len(pairs))
        _run_variant("v51", intraday_basket_simulator.run, force, pairs=pairs)

        _run_variant("v52", v52_stock_vs_index.run, force,
                     signals=signals, symbol_bars=bars, hold_days=1)
        _run_variant("v53", v53_nifty_overlay.run, force,
                     signals=signals, symbol_bars=bars, hold_days=1)
        _run_variant("v54", v54_banknifty_dispersion.run, force,
                     signals=signals, symbol_bars=bars, hold_days=1)
        _run_variant("v55", v55_leader_routing.run, force,
                     signals=signals, symbol_bars=bars, hold_days=1)
        _run_variant("v56", v56_horizon_sweep.run, force,
                     signals=signals, symbol_bars=bars)
        _run_variant("v57", v57_options_overlay.run, force,
                     signals=signals, symbol_bars=bars)

    ledger_map = ablation.load_ledgers_from_dir(paths.LEDGERS_DIR)
    ablation_df = ablation.compute_comparison(ledger_map, n_tests=12, alpha_family=0.01)
    ablation_df.to_csv(paths.LEDGERS_DIR / "ablation.csv", index=False)
    log.info("\n%s", ablation_df.to_string(index=False))

    report.write_report(paths.DOCS_DIR / "phase-c-v5-report.md",
                        ablation=ablation_df, ledger_map=ledger_map)
    log.info("wrote report to %s", paths.DOCS_DIR / "phase-c-v5-report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Rerun all variants even if ledgers exist")
    args = ap.parse_args()
    main(force=args.force)
