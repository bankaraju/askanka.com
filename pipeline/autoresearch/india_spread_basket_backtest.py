"""H-2026-04-30-spread-basket-001..013 — 5y backtest of 13 INDIA_SPREAD_PAIRS baskets.

Spec: docs/superpowers/specs/2026-04-30-india-spread-pairs-13-basket-backtest-design.md
Data discovery: pipeline/data/research/india_spread_pairs_backtest/data_discovery_2026-04-30.md

Replaces the legacy `pipeline.autoresearch.unified_backtest` for the 13-basket scope.
unified_backtest covered only 6 of 13, was 3y not 5y, and reported Sharpe 13.72
because it deducted no costs. This runner enforces:

- 5y window (2021-04-23 -> 2026-04-22)
- Cost discipline: 20bp round-trip per basket on 4 legs, plus 30bp sensitivity
- Per-regime breakdown via PIT regime tape (NOT the hindsight-contaminated regime_history.csv)
- BH-FDR @ q=0.10 across (13 baskets x 3 holds x 5 regimes = 195 cells)
- Bootstrap stability across 200 random 252-day windows per (basket, regime, hold)
- Verdict bar: post-cost mean > 0 at 20bp AND 30bp, t > 2, BH-FDR survive,
  bootstrap >= 60%, hit >= 55%, MaxDD <= 25%, n >= 10.

Runner CLI

    python -m pipeline.autoresearch.india_spread_basket_backtest \\
        --mode B \\
        --start 2021-04-23 --end 2026-04-22 \\
        --out pipeline/data/research/india_spread_pairs_backtest

Mode A (news-conditional) requires:
- pipeline/data/research/etf_v3/regime_tape_5y_pit.csv (PIT regime tape)
- pipeline/data/news_events_history.json (already exists, 2024-04-23 onwards only)

Mode B (trigger-agnostic structural) runs without news; if regime tape missing,
Mode B still runs but per-regime cells degrade to UNCONDITIONAL.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

log = logging.getLogger("anka.india_spread_basket_backtest")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FNO_HIST = REPO_ROOT / "pipeline" / "data" / "fno_historical"
NEWS_HISTORY = REPO_ROOT / "pipeline" / "data" / "news_events_history.json"
PIT_REGIME = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
DEFAULT_OUT = REPO_ROOT / "pipeline" / "data" / "research" / "india_spread_pairs_backtest"

COST_BPS_DEFAULT = 20.0
COST_BPS_SENSITIVITY = 30.0
HOLD_PERIODS = [1, 3, 5]
BOOTSTRAP_ITERS = 200
BOOTSTRAP_WINDOW_DAYS = 252
ALPHA = 0.05
BH_FDR_Q = 0.10


# ---------------------------------------------------------------------------
# Basket loading from canonical config
# ---------------------------------------------------------------------------
def load_baskets() -> list[dict[str, Any]]:
    """Load the 13 INDIA_SPREAD_PAIRS_DEPRECATED baskets from pipeline.config.

    Returns list of dicts keyed by name/long/short/triggers, with hypothesis_id
    attached as H-2026-04-30-spread-basket-NNN.
    """
    sys.path.insert(0, str(REPO_ROOT / "pipeline"))
    try:
        from config import INDIA_SPREAD_PAIRS_DEPRECATED  # type: ignore
    except ImportError:
        from pipeline.config import INDIA_SPREAD_PAIRS_DEPRECATED  # type: ignore

    out = []
    for i, b in enumerate(INDIA_SPREAD_PAIRS_DEPRECATED, start=1):
        out.append(
            {
                "hypothesis_id": f"H-2026-04-30-spread-basket-{i:03d}",
                "basket_idx": i,
                "name": b["name"],
                "long": list(b["long"]),
                "short": list(b["short"]),
                "triggers": list(b["triggers"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Equity panel loader
# ---------------------------------------------------------------------------
def _read_csv(ticker: str) -> Optional[pd.DataFrame]:
    p = FNO_HIST / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["Date"])
    df = df.set_index("Date").sort_index()
    return df


def load_returns_panel(tickers: Iterable[str], start: date, end: date) -> pd.DataFrame:
    """Build a wide panel of daily log returns for the union of basket legs.

    Index = trading dates in [start, end].
    Columns = ticker symbols. Missing tickers logged but skipped.
    """
    cols: dict[str, pd.Series] = {}
    missing: list[str] = []
    for t in sorted(set(tickers)):
        df = _read_csv(t)
        if df is None:
            missing.append(t)
            continue
        df = df.loc[(df.index.date >= start) & (df.index.date <= end)]
        if df.empty or "Close" not in df.columns:
            missing.append(t)
            continue
        ret = np.log(df["Close"]).diff().rename(t)
        cols[t] = ret
    if missing:
        log.warning("Missing equities (skipped): %s", ", ".join(missing))
    panel = pd.concat(cols, axis=1)
    panel.index = pd.DatetimeIndex(panel.index).normalize()
    return panel.dropna(how="all")


# ---------------------------------------------------------------------------
# PIT regime tape loader
# ---------------------------------------------------------------------------
def load_regime_tape() -> Optional[pd.Series]:
    """Returns a Series of regime labels indexed by trading date, or None if
    tape unavailable. Production rule: never use regime_history.csv (hindsight).
    """
    if not PIT_REGIME.exists():
        log.warning(
            "PIT regime tape not found at %s. Per-regime breakdown disabled. "
            "Run pipeline/scripts/one_off/build_regime_tape_5y_pit.py first to "
            "enable Mode A and regime-conditional Mode B cells.",
            PIT_REGIME,
        )
        return None
    df = pd.read_csv(PIT_REGIME, parse_dates=["date"])
    return pd.Series(df["regime"].values, index=pd.DatetimeIndex(df["date"]).normalize())


# ---------------------------------------------------------------------------
# News trigger replay (Mode A)
# ---------------------------------------------------------------------------
def load_news_history() -> pd.DataFrame:
    """Load news_events_history.json into a DataFrame with parsed published date,
    headline+summary text, and pre-classified trigger keyword (re-runs the
    canonical classifier).
    """
    if not NEWS_HISTORY.exists():
        return pd.DataFrame(columns=["published", "title", "summary", "url", "trigger"])

    with NEWS_HISTORY.open("r", encoding="utf-8") as f:
        items = json.load(f)

    rows = []
    for it in items:
        pub = it.get("published") or ""
        try:
            ts = pd.to_datetime(pub, errors="coerce", utc=True)
        except Exception:
            ts = pd.NaT
        rows.append(
            {
                "published": ts,
                "title": it.get("title", "") or "",
                "summary": "",  # not stored in history
                "url": it.get("url", "") or "",
            }
        )
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["published"])

    # Re-classify each headline through the canonical classifier
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from pipeline.political_signals import classify_event_keywords  # type: ignore
    except ImportError:
        from political_signals import classify_event_keywords  # type: ignore

    triggers = []
    for _, r in df.iterrows():
        cat, _ = classify_event_keywords(r["title"], r["summary"])
        triggers.append(cat)
    df["trigger"] = triggers
    df["date"] = df["published"].dt.tz_convert("Asia/Calcutta").dt.normalize().dt.tz_localize(None)
    return df


def basket_trigger_dates(basket: dict[str, Any], news_df: pd.DataFrame) -> set[pd.Timestamp]:
    """Set of dates on which any of basket['triggers'] fired in news_df."""
    if news_df.empty:
        return set()
    fire = news_df[news_df["trigger"].isin(basket["triggers"])]
    return set(fire["date"].unique())


# ---------------------------------------------------------------------------
# Basket P&L
# ---------------------------------------------------------------------------
@dataclass
class TradeRow:
    basket_idx: int
    basket_name: str
    open_date: pd.Timestamp
    hold_days: int
    regime: str
    pnl_pre_cost_bps: float
    pnl_post_20bp_bps: float
    pnl_post_30bp_bps: float
    n_long_legs: int
    n_short_legs: int
    triggered: bool


def basket_open_legs(basket: dict[str, Any], panel: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Filter basket legs to those present in the equity panel."""
    long_legs = [t for t in basket["long"] if t in panel.columns]
    short_legs = [t for t in basket["short"] if t in panel.columns]
    return long_legs, short_legs


def compute_basket_pnl(
    basket: dict[str, Any],
    panel: pd.DataFrame,
    open_date: pd.Timestamp,
    hold_days: int,
) -> Optional[tuple[float, int, int]]:
    """Equal-notional, dollar-neutral basket return over [open_date+1, open_date+hold_days].

    Uses log returns summed over the hold period for each leg, averaged across
    long/short sides, dollar-neutralized as (mean_long - mean_short).

    Returns (pre_cost_bps, n_long, n_short) or None if not enough data.
    """
    long_legs, short_legs = basket_open_legs(basket, panel)
    if not long_legs or not short_legs:
        return None

    try:
        idx = panel.index.get_loc(open_date)
    except KeyError:
        return None
    if idx + hold_days >= len(panel):
        return None

    window = panel.iloc[idx + 1 : idx + 1 + hold_days]
    if len(window) < hold_days:
        return None

    long_ret = window[long_legs].sum(axis=0).mean()
    short_ret = window[short_legs].sum(axis=0).mean()
    if pd.isna(long_ret) or pd.isna(short_ret):
        return None

    pnl_log = long_ret - short_ret  # dollar-neutral pair return
    pnl_bps = pnl_log * 1e4
    return float(pnl_bps), len(long_legs), len(short_legs)


def replay_basket(
    basket: dict[str, Any],
    panel: pd.DataFrame,
    regime_tape: Optional[pd.Series],
    open_dates: Iterable[pd.Timestamp],
    triggered_set: Optional[set[pd.Timestamp]],
) -> list[TradeRow]:
    """For each open_date and each hold horizon, compute basket P&L."""
    rows: list[TradeRow] = []
    for d in sorted(open_dates):
        for h in HOLD_PERIODS:
            res = compute_basket_pnl(basket, panel, d, h)
            if res is None:
                continue
            pnl_bps, nl, ns = res
            # Per spec: 5 bps per leg per round-trip; basket round-trip cost
            # is sum across legs. Spec defaults (20bp / 30bp) are flat
            # per-basket figures, not per-leg. To honor the spec's stated
            # 20 bps for a 4-leg basket we use the flat cost directly.
            cost_20 = COST_BPS_DEFAULT
            cost_30 = COST_BPS_SENSITIVITY
            regime = "ALL"
            if regime_tape is not None and d in regime_tape.index:
                regime = str(regime_tape.loc[d])
            rows.append(
                TradeRow(
                    basket_idx=basket["basket_idx"],
                    basket_name=basket["name"],
                    open_date=d,
                    hold_days=h,
                    regime=regime,
                    pnl_pre_cost_bps=pnl_bps,
                    pnl_post_20bp_bps=pnl_bps - cost_20,
                    pnl_post_30bp_bps=pnl_bps - cost_30,
                    n_long_legs=nl,
                    n_short_legs=ns,
                    triggered=(triggered_set is None) or (d in triggered_set),
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Aggregation, BH-FDR, bootstrap
# ---------------------------------------------------------------------------
@dataclass
class CellAggregate:
    basket_idx: int
    basket_name: str
    regime: str
    hold_days: int
    mode: str  # "A" or "B"
    n_events: int
    mean_pre_bps: float
    mean_post_20bp_bps: float
    mean_post_30bp_bps: float
    hit_rate_post_20bp: float
    sharpe_post_20bp: float
    max_dd_post_20bp_bps: float
    t_stat: float
    p_value: float
    bh_fdr_pass: Optional[bool] = None
    bootstrap_stability_pct: Optional[float] = None
    verdict: str = ""


def _t_test_one_sample(x: np.ndarray) -> tuple[float, float]:
    if len(x) < 2:
        return 0.0, 1.0
    mean = float(np.mean(x))
    std = float(np.std(x, ddof=1))
    if std == 0.0:
        return 0.0, 1.0
    t = mean / (std / math.sqrt(len(x)))
    # two-sided p from t-distribution survival; use scipy if available
    try:
        from scipy import stats  # type: ignore

        p = float(2.0 * stats.t.sf(abs(t), df=len(x) - 1))
    except ImportError:
        # Fallback: normal approximation (conservative for small n)
        p = float(2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0)))))
    return t, p


def _max_drawdown_bps(returns_bps: np.ndarray) -> float:
    if len(returns_bps) == 0:
        return 0.0
    cum = np.cumsum(returns_bps)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    return float(dd.min())


def aggregate_cells(rows: list[TradeRow], mode: str) -> list[CellAggregate]:
    df = pd.DataFrame([r.__dict__ for r in rows])
    if df.empty:
        return []
    out: list[CellAggregate] = []
    for (bi, bn, rg, h), g in df.groupby(["basket_idx", "basket_name", "regime", "hold_days"]):
        x_pre = g["pnl_pre_cost_bps"].values
        x_20 = g["pnl_post_20bp_bps"].values
        x_30 = g["pnl_post_30bp_bps"].values
        t, p = _t_test_one_sample(x_20)
        std_20 = float(np.std(x_20, ddof=1)) if len(x_20) > 1 else 0.0
        sharpe = float(np.mean(x_20) / std_20) if std_20 > 0 else 0.0
        out.append(
            CellAggregate(
                basket_idx=int(bi),
                basket_name=str(bn),
                regime=str(rg),
                hold_days=int(h),
                mode=mode,
                n_events=int(len(g)),
                mean_pre_bps=float(np.mean(x_pre)),
                mean_post_20bp_bps=float(np.mean(x_20)),
                mean_post_30bp_bps=float(np.mean(x_30)),
                hit_rate_post_20bp=float((x_20 > 0).mean()),
                sharpe_post_20bp=sharpe,
                max_dd_post_20bp_bps=_max_drawdown_bps(x_20),
                t_stat=t,
                p_value=p,
            )
        )
    return out


def benjamini_hochberg(p_values: list[float], q: float = BH_FDR_Q) -> list[bool]:
    """Returns a boolean list indicating which hypotheses survive BH-FDR at level q."""
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    threshold_idx = -1
    for k, i in enumerate(order, start=1):
        bh = (k / n) * q
        if p_values[i] <= bh:
            threshold_idx = k
    survive = [False] * n
    if threshold_idx > 0:
        for k, i in enumerate(order, start=1):
            if k <= threshold_idx:
                survive[i] = True
    return survive


def assign_verdict(c: CellAggregate) -> str:
    if c.n_events < 10:
        return "INSUFFICIENT_N"
    if c.mean_post_20bp_bps <= 0 or c.mean_post_30bp_bps <= 0:
        return "FAIL_POSTCOST"
    if c.t_stat <= 2.0:
        return "FAIL_TSTAT"
    if c.bh_fdr_pass is False:
        return "FAIL_BH_FDR"
    if c.bootstrap_stability_pct is not None and c.bootstrap_stability_pct < 60:
        return "FAIL_STABILITY"
    if c.hit_rate_post_20bp < 0.55:
        return "FAIL_HITRATE"
    if c.max_dd_post_20bp_bps < -2500:  # 25% in bps
        return "FAIL_MAXDD"
    return "PASS"


# ---------------------------------------------------------------------------
# Bootstrap stability
# ---------------------------------------------------------------------------
def bootstrap_stability(
    basket: dict[str, Any],
    panel: pd.DataFrame,
    regime_tape: Optional[pd.Series],
    open_dates: list[pd.Timestamp],
    triggered_set: Optional[set[pd.Timestamp]],
    iters: int = BOOTSTRAP_ITERS,
    rng_seed: int = 42,
) -> dict[tuple[str, int], float]:
    """For each (regime, hold) cell, measure fraction of bootstrap samples
    where post-20bp mean > 0. Each sample = a random 252-day calendar window.
    """
    if len(open_dates) == 0 or len(panel) < BOOTSTRAP_WINDOW_DAYS + 5:
        return {}
    rng = np.random.default_rng(rng_seed)
    counts: dict[tuple[str, int], int] = {}
    totals: dict[tuple[str, int], int] = {}

    panel_dates = list(panel.index)
    max_start = len(panel_dates) - BOOTSTRAP_WINDOW_DAYS

    for _ in range(iters):
        s = rng.integers(0, max_start)
        win_start = panel_dates[s]
        win_end = panel_dates[s + BOOTSTRAP_WINDOW_DAYS - 1]
        sample_dates = [d for d in open_dates if win_start <= d <= win_end]
        if not sample_dates:
            continue
        rows = replay_basket(basket, panel, regime_tape, sample_dates, triggered_set)
        if not rows:
            continue
        df = pd.DataFrame([r.__dict__ for r in rows])
        for (rg, h), g in df.groupby(["regime", "hold_days"]):
            key = (str(rg), int(h))
            x = g["pnl_post_20bp_bps"].values
            if len(x) < 5:
                continue
            totals[key] = totals.get(key, 0) + 1
            if float(np.mean(x)) > 0:
                counts[key] = counts.get(key, 0) + 1

    return {
        k: 100.0 * counts.get(k, 0) / totals.get(k, 1) for k in totals
    }


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------
def run_mode(
    mode: str,
    start: date,
    end: date,
    out_dir: Path,
    skip_bootstrap: bool = False,
) -> dict[str, Any]:
    assert mode in ("A", "B"), "mode must be A or B"
    out_dir.mkdir(parents=True, exist_ok=True)

    baskets = load_baskets()
    universe = sorted({t for b in baskets for t in b["long"] + b["short"]})
    panel = load_returns_panel(universe, start, end)
    regime_tape = load_regime_tape()
    if regime_tape is not None:
        regime_tape = regime_tape.loc[(regime_tape.index >= pd.Timestamp(start)) & (regime_tape.index <= pd.Timestamp(end))]

    if mode == "A":
        if not NEWS_HISTORY.exists():
            log.error("Mode A requires news_events_history.json")
            return {"status": "abort_no_news"}
        news_df = load_news_history()
        news_df = news_df[(news_df["date"] >= pd.Timestamp(start)) & (news_df["date"] <= pd.Timestamp(end))]
    else:
        news_df = pd.DataFrame()

    all_rows: list[TradeRow] = []
    bootstrap_by_basket: dict[int, dict[tuple[str, int], float]] = {}
    for b in baskets:
        if mode == "A":
            triggered = basket_trigger_dates(b, news_df)
            open_dates = sorted(triggered & set(panel.index))
            triggered_set = triggered
        else:
            open_dates = list(panel.index)
            triggered_set = None
        log.info("basket #%d %s: %d open dates (mode %s)", b["basket_idx"], b["name"], len(open_dates), mode)
        rows = replay_basket(b, panel, regime_tape, open_dates, triggered_set)
        all_rows.extend(rows)
        if not skip_bootstrap and rows:
            bootstrap_by_basket[b["basket_idx"]] = bootstrap_stability(
                b, panel, regime_tape, open_dates, triggered_set
            )

    cells = aggregate_cells(all_rows, mode=mode)

    # BH-FDR across all cells in this mode
    p_vals = [c.p_value for c in cells]
    bh_results = benjamini_hochberg(p_vals, q=BH_FDR_Q)
    for c, ok in zip(cells, bh_results):
        c.bh_fdr_pass = bool(ok)
        if c.basket_idx in bootstrap_by_basket:
            c.bootstrap_stability_pct = bootstrap_by_basket[c.basket_idx].get(
                (c.regime, c.hold_days)
            )
        c.verdict = assign_verdict(c)

    # Write per-event CSV
    per_event_path = out_dir / f"per_event_mode{mode}_{date.today().isoformat()}.csv"
    pd.DataFrame([r.__dict__ for r in all_rows]).to_csv(per_event_path, index=False)

    # Write summary CSV
    summary_path = out_dir / f"summary_mode{mode}_{date.today().isoformat()}.csv"
    pd.DataFrame([c.__dict__ for c in cells]).to_csv(summary_path, index=False)

    return {
        "status": "ok",
        "mode": mode,
        "n_events": len(all_rows),
        "n_cells": len(cells),
        "per_event_path": str(per_event_path.relative_to(REPO_ROOT)),
        "summary_path": str(summary_path.relative_to(REPO_ROOT)),
        "verdicts": {
            "PASS": sum(1 for c in cells if c.verdict == "PASS"),
            "FAIL": sum(1 for c in cells if c.verdict.startswith("FAIL")),
            "INSUFFICIENT_N": sum(1 for c in cells if c.verdict == "INSUFFICIENT_N"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mode", choices=["A", "B", "both"], default="both",
                        help="A=news-conditional (2024+), B=trigger-agnostic 5y, both=run sequentially")
    parser.add_argument("--start", type=lambda s: date.fromisoformat(s), default=date(2021, 4, 23))
    parser.add_argument("--end", type=lambda s: date.fromisoformat(s), default=date(2026, 4, 22))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    summary: dict[str, Any] = {"runs": []}
    modes = ["A", "B"] if args.mode == "both" else [args.mode]
    if "A" in modes:
        # Mode A is restricted to 2024-2026 per data discovery
        a_start = max(args.start, date(2024, 4, 23))
        result = run_mode("A", a_start, args.end, args.out, skip_bootstrap=args.skip_bootstrap)
        summary["runs"].append({"mode": "A", **result, "window": [a_start.isoformat(), args.end.isoformat()]})
    if "B" in modes:
        result = run_mode("B", args.start, args.end, args.out, skip_bootstrap=args.skip_bootstrap)
        summary["runs"].append({"mode": "B", **result, "window": [args.start.isoformat(), args.end.isoformat()]})

    summary_path = args.out / f"run_summary_{date.today().isoformat()}.json"
    args.out.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
