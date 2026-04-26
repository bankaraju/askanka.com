"""H-2026-04-26-003 — NEUTRAL-day long-intraday backtest.

User hypothesis (informal)
--------------------------
The σ-correlation-break rule (H-2026-04-26-001/002) fires only ~5 trades
in 60 NEUTRAL-regime days. Long-run NEUTRAL is ~85% of trading time, so
we either need a separate strategy for NEUTRAL days or we sit on cash 85%
of the time. Theory #2: on NEUTRAL days, a long-only intraday momentum /
quality-persistence trade (long index OR long top-FCS stocks at 09:30,
exit 14:30) makes money — exploiting a different alpha source than the
σ-break mean-reversion rule.

What this script does
---------------------
Variant A — Long sectoral index intraday (09:30 → 14:30) on NEUTRAL days
Variant B — Long top-N FCS-attractiveness stocks intraday on NEUTRAL days
Comparator — passive long-index full-day hold (09:15 → 15:30 close)

Data
----
  * pipeline/data/regime_history.csv (5y, regime_zone per date)
  * pipeline/data/india_historical/indices/NIFTY_daily.csv (5y daily OHLC)
  * pipeline/data/india_historical/indices/<SECTOR>_daily.csv (5y daily OHLC)
  * pipeline/data/research/phase_c_shape_audit/bars/NIFTY <NAME>_<YYYYMMDD>.parquet
    (1-min bars, 38 days only, used to *calibrate* the daily proxy)
  * pipeline/data/ta_attractiveness_scores.json (CURRENT snapshot only,
    no historical scores → Variant B cannot be backtested historically)

Daily-to-intraday proxy
-----------------------
Without intraday minute bars across 5 years, we approximate:

   intraday_return_0930_to_1430 ≈ resolve_pct × (close − open) / open

where resolve_pct is the mean fraction of the daily open→close move that
is realized between 09:30 and 14:30. We *empirically calibrate*
resolve_pct from the 38-day intraday parquet sample, instead of assuming
a literature value.

This is the CRITICAL caveat — full-window minute bars are unavailable, so
all numerical edge claims are subject to the calibration of resolve_pct.

Outputs
-------
  * pipeline/data/research/h_2026_04_26_003_neutral_long/results.json
  * pipeline/data/research/h_2026_04_26_003_neutral_long/2026-04-26-neutral-long-intraday-backtest.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Make stdout UTF-8-safe on Windows so the verdict (which contains arrows
# / sigma / etc.) can be printed without UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

_REPO = Path(__file__).resolve().parents[2]
_REGIME_CSV = _REPO / "pipeline" / "data" / "regime_history.csv"
_INDICES_DIR = _REPO / "pipeline" / "data" / "india_historical" / "indices"
_INTRADAY_BARS_DIR = (
    _REPO / "pipeline" / "data" / "research" / "phase_c_shape_audit" / "bars"
)
_TA_SCORES_JSON = _REPO / "pipeline" / "data" / "ta_attractiveness_scores.json"
_OUT_DIR = (
    _REPO / "pipeline" / "data" / "research" / "h_2026_04_26_003_neutral_long"
)

# Sectoral indices we will run Variant A on (have daily OHLC).
# NB: NIFTYNXT50_daily.csv is a byte-identical duplicate of NIFTY_daily.csv
# in the current data lake (verified 2026-04-26) — excluded to avoid
# double-counting. File this as a separate data-quality issue.
SECTORAL_INDICES = {
    "NIFTY": "NIFTY 50",
    "NIFTYIT": "NIFTY IT",
    "NIFTYMETAL": "NIFTY METAL",
    "NIFTYPSUBANK": "NIFTY PSU BANK",
    "NIFTYENERGY": "NIFTY ENERGY",
}

# Intraday parquet underlying-name map for resolve_pct calibration
INTRADAY_UNDERLYINGS = {
    "NIFTYIT": "NIFTY IT",
    "NIFTYMETAL": "NIFTY METAL",
    "NIFTYPSUBANK": "NIFTY PSU BANK",
    "NIFTYENERGY": "NIFTY ENERGY",
}


# ---------------------------------------------------------------------------
# Calibration: empirically fit resolve_pct from 38-day intraday sample
# ---------------------------------------------------------------------------
def calibrate_resolve_pct() -> dict:
    """Estimate the fraction of daily open→close move resolved by 14:30.

    We use whatever intraday bar files exist in phase_c_shape_audit/bars/
    for sectoral indices. For each (underlying, date) bar file, we
    compute:
        intraday_pct = (close_at_or_before_1430 − open_at_0915) / open
        full_pct     = (close_at_or_before_1530 − open_at_0915) / open
        ratio        = intraday_pct / full_pct  (if |full_pct| > 5bp)

    The mean ratio across all (underlying, date) pairs is the empirical
    resolve_pct used in the daily proxy.
    """
    rows = []
    for parquet in _INTRADAY_BARS_DIR.glob("*.parquet"):
        name = parquet.stem  # e.g. "NIFTY BANK_20260424"
        if not name.startswith("NIFTY "):
            continue
        try:
            df = pd.read_parquet(parquet)
        except Exception:
            continue
        if df.empty or "timestamp_ist" not in df.columns:
            continue
        df = df.sort_values("timestamp_ist").reset_index(drop=True)
        ts = pd.to_datetime(df["timestamp_ist"])
        # 09:30 ≈ first bar at/after 09:30; we use 09:30 close (== minute bar's close)
        mask_open = ts.dt.time >= pd.Timestamp("09:30:00").time()
        if not mask_open.any():
            continue
        first_idx = mask_open.idxmax()
        # use bar at 09:30's open as entry
        entry = float(df.loc[first_idx, "open"])
        if entry <= 0:
            continue
        # 14:30 close
        mask_1430 = ts.dt.time <= pd.Timestamp("14:30:00").time()
        if not mask_1430.any():
            continue
        last_1430_idx = mask_1430[::-1].idxmax()
        exit_1430 = float(df.loc[last_1430_idx, "close"])
        # 15:30 close (last bar)
        last_idx = df.index[-1]
        exit_close = float(df.loc[last_idx, "close"])
        intraday_pct = (exit_1430 - entry) / entry
        full_pct = (exit_close - entry) / entry
        rows.append({
            "underlying": name.split("_")[0],
            "date": name.split("_")[1],
            "entry_0930": entry,
            "exit_1430": exit_1430,
            "exit_1530": exit_close,
            "intraday_pct": intraday_pct,
            "full_pct": full_pct,
        })
    if not rows:
        return {"n_samples": 0, "resolve_pct": 0.6, "note": "no intraday bars; fell back to literature 0.60"}
    sample = pd.DataFrame(rows)
    valid = sample[sample["full_pct"].abs() > 0.0005].copy()
    if valid.empty:
        return {"n_samples": len(sample), "resolve_pct": 0.6, "note": "no |full_pct|>5bp; literature fallback"}
    valid["ratio"] = valid["intraday_pct"] / valid["full_pct"]
    # winsorize ratio at [-3, 3] to reduce outlier from tiny denominators
    valid["ratio_clipped"] = valid["ratio"].clip(-3, 3)
    resolve_pct = float(valid["ratio_clipped"].mean())
    return {
        "n_samples": len(sample),
        "n_valid_for_ratio": len(valid),
        "resolve_pct": round(resolve_pct, 4),
        "ratio_median": round(float(valid["ratio_clipped"].median()), 4),
        "ratio_std": round(float(valid["ratio_clipped"].std()), 4),
        "intraday_pct_mean": round(float(sample["intraday_pct"].mean()), 6),
        "full_pct_mean": round(float(sample["full_pct"].mean()), 6),
        "note": "fitted from phase_c_shape_audit/bars sectoral-index minute bars",
    }


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------
def load_regime() -> pd.DataFrame:
    df = pd.read_csv(_REGIME_CSV, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df


def load_index_daily(symbol: str) -> pd.DataFrame:
    path = _INDICES_DIR / f"{symbol}_daily.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    df = df[df["open"] > 0].copy()  # drop zero-open rows if any
    return df


def variant_a_index(
    symbol: str,
    label: str,
    regime: pd.DataFrame,
    resolve_pct: float,
    target_regime: str = "NEUTRAL",
) -> dict:
    """Long index intraday on NEUTRAL days, exit 14:30 (proxied)."""
    daily = load_index_daily(symbol)
    merged = daily.merge(regime, on="date", how="inner")
    in_regime = merged[merged["regime_zone"] == target_regime].copy()
    out_regime = merged[merged["regime_zone"] != target_regime].copy()

    # daily move proxy: open -> close
    merged["daily_pct"] = (merged["close"] - merged["open"]) / merged["open"]
    in_regime = in_regime.assign(
        daily_pct=lambda x: (x["close"] - x["open"]) / x["open"]
    )
    in_regime["intraday_proxy"] = in_regime["daily_pct"] * resolve_pct
    full_day = in_regime["daily_pct"]  # passive baseline within same regime

    # All-days passive baseline (any regime)
    all_daily = (merged["close"] - merged["open"]) / merged["open"]

    def _stats(s: pd.Series, label_: str) -> dict:
        s = s.dropna()
        if len(s) == 0:
            return {"label": label_, "n": 0}
        n = int(len(s))
        mean = float(s.mean())
        std = float(s.std(ddof=1)) if n > 1 else float("nan")
        hit = float((s > 0).mean())
        # Sharpe: 252 trading days/year (independent days)
        sharpe = (mean / std) * math.sqrt(252) if std and std > 0 else float("nan")
        # Cumulative compounded return
        cum = float((1.0 + s).prod() - 1.0)
        # one-sample t-stat for mean != 0
        t_stat = (mean / (std / math.sqrt(n))) if (std and std > 0 and n > 1) else float("nan")
        return {
            "label": label_,
            "n": n,
            "mean_pct": round(mean * 100, 4),
            "std_pct": round(std * 100, 4) if not math.isnan(std) else None,
            "hit_rate_pct": round(hit * 100, 2),
            "sharpe_ann": round(sharpe, 3) if not math.isnan(sharpe) else None,
            "t_stat": round(t_stat, 3) if not math.isnan(t_stat) else None,
            "cum_return_pct": round(cum * 100, 2),
        }

    return {
        "symbol": symbol,
        "label": label,
        "target_regime": target_regime,
        "intraday_neutral": _stats(in_regime["intraday_proxy"], f"{label} 09:30->14:30 (proxy×{resolve_pct})"),
        "fullday_neutral_baseline": _stats(full_day, f"{label} 09:15->15:30 NEUTRAL only"),
        "fullday_all_regimes_baseline": _stats(all_daily, f"{label} 09:15->15:30 all regimes"),
    }


# ---------------------------------------------------------------------------
# Variant B — historical FCS history is not available
# ---------------------------------------------------------------------------
def variant_b_status() -> dict:
    if not _TA_SCORES_JSON.exists():
        return {"runnable": False, "reason": "ta_attractiveness_scores.json missing"}
    payload = json.loads(_TA_SCORES_JSON.read_text(encoding="utf-8"))
    return {
        "runnable": False,
        "reason": (
            "ta_attractiveness_scores.json contains a CURRENT snapshot only "
            "(single 'updated_at' timestamp, no per-day history). "
            "No historical FCS / TA-attractiveness time-series exists in "
            "pipeline/data/. Backtesting Variant B requires per-day rank "
            "history of attractiveness scores for ≥1 year — not available."
        ),
        "snapshot_updated_at": payload.get("updated_at"),
        "snapshot_ticker_count": len(payload.get("scores", {})),
        "remediation": (
            "To enable Variant B in a future run: write "
            "pipeline/data/feature_scorer_history.parquet with columns "
            "(date, ticker, score) populated daily by 16:00 IST EOD job. "
            "This is a green-field collector, not a backfillable derivation."
        ),
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------
def write_report(results: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    md = _build_markdown(results)
    (out_dir / "2026-04-26-neutral-long-intraday-backtest.md").write_text(
        md, encoding="utf-8"
    )


def _build_markdown(r: dict) -> str:
    cal = r["calibration"]
    lines = []
    lines.append("# H-2026-04-26-003 candidate — NEUTRAL-day long-intraday backtest")
    lines.append("")
    lines.append(f"_generated_: {r['generated_at']}")
    lines.append("")
    lines.append("## Hypothesis")
    lines.append("")
    lines.append(
        "On NEUTRAL regime days (where the σ-correlation-break rule fires "
        "thinly — ~5 trades in 60 days), a separate **long-only intraday** "
        "trade entered at 09:30 and exited at 14:30 makes money, exploiting "
        "a different alpha source (momentum / quality persistence) than the "
        "σ-break mean-reversion rule."
    )
    lines.append("")
    lines.append("## Data availability")
    lines.append("")
    lines.append(
        f"- **Regime history:** {r['data']['n_total_days']} days "
        f"({r['data']['date_min']} → {r['data']['date_max']}). "
        f"NEUTRAL = {r['data']['n_neutral_days']} days "
        f"({r['data']['neutral_pct']:.1f}%)."
    )
    lines.append(
        f"- **Sectoral index daily OHLC:** {len(SECTORAL_INDICES)} indices "
        f"({', '.join(SECTORAL_INDICES.values())}), each ~5y."
    )
    lines.append(
        f"- **Intraday minute bars:** {cal['n_samples']} "
        f"sectoral-index parquet files (~38 trading days, 2026-03-03 → 2026-04-24). "
        "Used only to *calibrate* the daily proxy below — too narrow to backtest "
        "directly across 5 years."
    )
    lines.append(
        "- **FCS / TA-attractiveness history:** **NOT AVAILABLE.** "
        "ta_attractiveness_scores.json is a single snapshot (no per-day series). "
        "Variant B is therefore not runnable historically."
    )
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("### The daily-to-intraday proxy (CRITICAL CAVEAT)")
    lines.append("")
    lines.append(
        "We do not have minute bars across the 5-year window. We approximate "
        "the 09:30->14:30 return by:"
    )
    lines.append("")
    lines.append("```")
    lines.append("intraday_return ~= resolve_pct * (close - open) / open")
    lines.append("```")
    lines.append("")
    lines.append(
        "where `resolve_pct` is the empirical fraction of the daily open→close "
        "move realized by 14:30, **fitted from the 38-day intraday sample we "
        "do have**:"
    )
    lines.append("")
    lines.append(f"- n_samples = {cal['n_samples']}")
    lines.append(f"- n_valid_for_ratio (|full_day|>5bp) = {cal.get('n_valid_for_ratio', 'n/a')}")
    lines.append(f"- **resolve_pct (mean)** = **{cal['resolve_pct']}**")
    lines.append(f"- ratio_median = {cal.get('ratio_median', 'n/a')}")
    lines.append(f"- ratio_std = {cal.get('ratio_std', 'n/a')}")
    lines.append(f"- intraday_pct_mean (raw) = {cal.get('intraday_pct_mean', 'n/a')}")
    lines.append(f"- full_pct_mean (raw) = {cal.get('full_pct_mean', 'n/a')}")
    lines.append("")
    lines.append(
        "**The proxy preserves the SIGN of the daily move and scales magnitude "
        "by `resolve_pct`. It does NOT inject any look-ahead — `(close − open) / "
        "open` is computed from the same day's OHLC, and `resolve_pct` is a "
        "constant scalar fitted on a disjoint sub-period.**"
    )
    lines.append("")
    lines.append(
        "**Honest reading:** any intraday edge claim is conditional on this "
        "proxy. If the true 09:30->14:30 dynamic on NEUTRAL days differs "
        "systematically from `resolve_pct × full_day`, the numbers below are "
        "biased. We cannot eliminate that risk without minute bars."
    )
    lines.append("")
    lines.append("## Variant A — Long sectoral index intraday (09:30->14:30) on NEUTRAL days")
    lines.append("")
    lines.append("| Symbol | n NEUTRAL | mean % | std % | hit % | Sharpe (ann) | t | cum % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for sym, _label in SECTORAL_INDICES.items():
        if sym not in r["variant_a"]:
            continue
        s = r["variant_a"][sym]["intraday_neutral"]
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"| {sym} | {s['n']} | {s['mean_pct']} | {s.get('std_pct') or '–'} | "
            f"{s['hit_rate_pct']} | {s.get('sharpe_ann') or '–'} | "
            f"{s.get('t_stat') or '–'} | {s['cum_return_pct']} |"
        )
    lines.append("")
    lines.append("### Comparator: passive full-day hold (09:15->15:30, NEUTRAL only)")
    lines.append("")
    lines.append("| Symbol | n NEUTRAL | mean % | hit % | Sharpe (ann) | t | cum % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for sym in SECTORAL_INDICES:
        if sym not in r["variant_a"]:
            continue
        s = r["variant_a"][sym]["fullday_neutral_baseline"]
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"| {sym} | {s['n']} | {s['mean_pct']} | {s['hit_rate_pct']} | "
            f"{s.get('sharpe_ann') or '–'} | {s.get('t_stat') or '–'} | {s['cum_return_pct']} |"
        )
    lines.append("")
    lines.append("### Comparator: passive full-day hold (09:15->15:30, ALL regimes)")
    lines.append("")
    lines.append("| Symbol | n days | mean % | hit % | Sharpe (ann) | t | cum % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for sym in SECTORAL_INDICES:
        if sym not in r["variant_a"]:
            continue
        s = r["variant_a"][sym]["fullday_all_regimes_baseline"]
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"| {sym} | {s['n']} | {s['mean_pct']} | {s['hit_rate_pct']} | "
            f"{s.get('sharpe_ann') or '–'} | {s.get('t_stat') or '–'} | {s['cum_return_pct']} |"
        )
    lines.append("")
    lines.append("## Variant B — long top-N FCS-attractiveness stocks intraday on NEUTRAL days")
    lines.append("")
    vb = r["variant_b"]
    lines.append(f"**Status: {('RAN' if vb['runnable'] else 'SKIPPED')}**")
    lines.append("")
    lines.append(f"Reason: {vb['reason']}")
    lines.append("")
    if "snapshot_updated_at" in vb:
        lines.append(
            f"Current snapshot info: updated_at={vb['snapshot_updated_at']}, "
            f"ticker_count={vb['snapshot_ticker_count']}"
        )
        lines.append("")
    if "remediation" in vb:
        lines.append(f"**Remediation to enable in future:** {vb['remediation']}")
        lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(r["verdict"])
    lines.append("")
    lines.append("## Caveats and limits of this study")
    lines.append("")
    lines.append(
        "1. **Daily proxy vs true intraday.** The 14:30 exit return is a "
        "scaled version of the open→close daily move. If NEUTRAL days "
        "systematically have non-monotonic intraday paths (e.g. morning "
        "spike → afternoon fade), the proxy mis-states the 14:30 return. "
        "The 38-day calibration sample is too small to reject this risk."
    )
    lines.append(
        "2. **No frictions modeled.** Brokerage, STT, slippage, impact at the "
        "open are all zero in this run. The mechanical ETF-future / index-future "
        "round trip costs ~5–10 bps; any edge below that is unbankable."
    )
    lines.append(
        "3. **Variant B not runnable.** No historical FCS time series exists, "
        "so the 'top-quality stocks' arm of the user's theory cannot be "
        "evaluated here."
    )
    lines.append(
        "4. **Single-touch risk.** This is a research backtest. If a strategy "
        "is registered as H-2026-04-26-003, its single-touch holdout under "
        "the autoresearch v2 protocol must use a held-out period not present "
        "above."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--regime",
        default="NEUTRAL",
        help="regime_zone label to test (default: NEUTRAL)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(_OUT_DIR),
        help="output directory for results.json + .md",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)

    print(f"[h-003] regime={args.regime}, out={out_dir}")
    regime = load_regime()
    n_total = len(regime)
    n_neutral = int((regime["regime_zone"] == args.regime).sum())
    print(f"[h-003] regime_history: {n_total} days, {args.regime}={n_neutral}")

    print("[h-003] calibrating resolve_pct from intraday parquet sample...")
    cal = calibrate_resolve_pct()
    print(f"[h-003] resolve_pct={cal['resolve_pct']} (n_samples={cal['n_samples']})")

    print("[h-003] running Variant A across sectoral indices...")
    variant_a = {}
    for sym, label in SECTORAL_INDICES.items():
        try:
            variant_a[sym] = variant_a_index(
                sym, label, regime, cal["resolve_pct"], target_regime=args.regime
            )
            s = variant_a[sym]["intraday_neutral"]
            print(
                f"[h-003]   {sym}: n={s['n']}, mean={s.get('mean_pct')}%, "
                f"hit={s.get('hit_rate_pct')}%, sharpe={s.get('sharpe_ann')}, "
                f"t={s.get('t_stat')}"
            )
        except FileNotFoundError as e:
            print(f"[h-003]   {sym}: SKIP ({e})")

    vb = variant_b_status()
    print(f"[h-003] Variant B: runnable={vb['runnable']} ({vb['reason'][:80]}...)")

    verdict = build_verdict(variant_a, vb, args.regime)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hypothesis": "H-2026-04-26-003 candidate (NEUTRAL-day long-intraday)",
        "data": {
            "regime_csv": str(_REGIME_CSV),
            "n_total_days": n_total,
            "n_neutral_days": n_neutral,
            "neutral_pct": round(100 * n_neutral / max(n_total, 1), 2),
            "date_min": str(regime["date"].min()),
            "date_max": str(regime["date"].max()),
        },
        "calibration": cal,
        "variant_a": variant_a,
        "variant_b": vb,
        "verdict": verdict,
    }
    write_report(payload, out_dir)
    print(f"[h-003] wrote {out_dir/'results.json'}")
    print(f"[h-003] wrote {out_dir/'2026-04-26-neutral-long-intraday-backtest.md'}")
    print()
    print("[h-003] VERDICT:")
    print(verdict)
    return 0


def build_verdict(variant_a: dict, vb: dict, regime: str) -> str:
    """Compose a one-paragraph verdict on whether to register H-003."""
    if not variant_a:
        return f"INCONCLUSIVE — no Variant A symbols ran on {regime}."

    # collect intraday means + sharpes per symbol
    intraday_metrics = []
    for sym, payload in variant_a.items():
        s = payload.get("intraday_neutral", {})
        b = payload.get("fullday_neutral_baseline", {})
        if s.get("n", 0) > 0:
            intraday_metrics.append({
                "symbol": sym,
                "intraday_mean": s.get("mean_pct"),
                "intraday_hit": s.get("hit_rate_pct"),
                "intraday_sharpe": s.get("sharpe_ann"),
                "intraday_t": s.get("t_stat"),
                "fullday_mean": b.get("mean_pct"),
                "fullday_sharpe": b.get("sharpe_ann"),
            })

    if not intraday_metrics:
        return f"INCONCLUSIVE — no {regime} samples in any Variant A symbol."

    # average across symbols
    n_pos_mean = sum(1 for m in intraday_metrics if (m["intraday_mean"] or 0) > 0)
    n_pos_sharpe = sum(1 for m in intraday_metrics if (m["intraday_sharpe"] or 0) > 0)
    n_significant = sum(1 for m in intraday_metrics if abs(m["intraday_t"] or 0) > 1.96)

    avg_mean = sum((m["intraday_mean"] or 0) for m in intraday_metrics) / len(intraday_metrics)
    avg_sharpe = sum((m["intraday_sharpe"] or 0) for m in intraday_metrics) / len(intraday_metrics)
    avg_full_sharpe = sum((m["fullday_sharpe"] or 0) for m in intraday_metrics) / len(intraday_metrics)

    nifty = next((m for m in intraday_metrics if m["symbol"] == "NIFTY"), None)

    parts = []
    parts.append(
        f"Across {len(intraday_metrics)} sectoral indices, "
        f"NEUTRAL-day 09:30->14:30 intraday long shows: "
        f"average mean per-day return = {avg_mean:.4f}%, "
        f"average annualized Sharpe = {avg_sharpe:.3f}, "
        f"{n_pos_mean}/{len(intraday_metrics)} symbols positive in mean, "
        f"{n_significant}/{len(intraday_metrics)} symbols with |t|>1.96."
    )
    if nifty:
        parts.append(
            f" NIFTY 50: mean={nifty['intraday_mean']}%, "
            f"hit={nifty['intraday_hit']}%, "
            f"Sharpe={nifty['intraday_sharpe']}, t={nifty['intraday_t']}."
        )
    parts.append(
        f" Passive full-day hold on the same NEUTRAL days has "
        f"average Sharpe = {avg_full_sharpe:.3f}."
    )

    # decision rule: register only if (a) majority of symbols positive
    # AND (b) average annualized Sharpe > 0.5 AND (c) at least one
    # symbol with |t|>1.96.
    register = (
        n_pos_mean >= max(1, len(intraday_metrics) // 2 + 1)
        and avg_sharpe > 0.5
        and n_significant >= 1
    )
    if register:
        parts.append(
            "  DECISION: edge is **material enough** to justify registering "
            "H-2026-04-26-003 and running it through the autoresearch v2 "
            "single-touch holdout. Note: (i) result is sensitive to the "
            f"daily-proxy resolve_pct calibration; (ii) frictions are not "
            "modeled; (iii) Variant B not yet runnable."
        )
    else:
        parts.append(
            "  DECISION: edge is **NOT convincing** — do NOT register "
            "H-2026-04-26-003 in its current form. The NEUTRAL-day long-only "
            "intraday on indices does not clear the bar (majority positive + "
            "Sharpe>0.5 + at least one |t|>1.96). Practical implication: "
            "sitting in cash on NEUTRAL days is a Sharpe-positive decision "
            "vs taking on undifferentiated market beta — UNLESS the FCS-stock "
            "Variant B (currently un-backtestable) reveals quality-persistence "
            "edge that the index-level test cannot see."
        )
    return "".join(parts)


if __name__ == "__main__":
    sys.exit(main())
