"""Tier 1 permutation null framework for H-2026-04-26-001.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md
Backtest standards: docs/superpowers/specs/backtesting-specs.txt §15.1, §9B.2

The hypothesis is that a |z| >= 2.0 sigma-break correlation residual,
faded at 09:30 with ATR(14)*2 stop and TIME_STOP at 14:30, produces a
hit rate well above the population mean. The in-sample 60-day replay
shows 39/42 = 92.86% on the >=2σ slice.

Two null distributions are computed:

* Null A — random sampling from the candidate pool. Sample 42 rows
  uniformly without replacement from the full 388-trade candidate
  pool, compute hit rate, repeat 100,000 times. p_A = fraction of
  permutations with hit rate >= observed.

* Null B — within-ticker day-shuffle. For each of the 42 actual >=2σ
  trades, keep the ticker fixed but draw a random day's pnl_pct from
  that ticker's candidate-pool history. Tickers with fewer than 5
  candidate-day P&Ls are dropped (and n is reduced).

§9B.2 PASS threshold: p < 0.000417 (Bonferroni-adjusted at 0.05/120).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_IN_SAMPLE_CSV = (
    Path("pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv")
)
DEFAULT_OUT_DIR = Path("pipeline/data/research/h_2026_04_26_001/perm_null/")
DEFAULT_N_PERMS = 100_000
DEFAULT_SEED = 20260426
SIGMA_THRESHOLD = 2.0
MIN_TICKER_DAYS = 5
BONFERRONI_THRESHOLD = 0.000417
HYPOTHESIS_ID = "H-2026-04-26-001"


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _load_trades(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = {"ticker", "abs_z", "pnl_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns in {csv_path}: {missing}")
    df = df.dropna(subset=["pnl_pct", "abs_z"]).copy()
    df["hit"] = (df["pnl_pct"] > 0).astype(np.int8)
    return df


def _null_a_random_sampling(
    candidate_pool: pd.DataFrame,
    n_observed: int,
    n_perms: int,
    rng: np.random.Generator,
) -> dict:
    """Null A — random sampling from the candidate pool, no replacement."""
    pool_hits = candidate_pool["hit"].to_numpy(dtype=np.int8)
    pool_n = pool_hits.shape[0]
    if pool_n < n_observed:
        raise ValueError(
            f"candidate pool ({pool_n}) smaller than n_observed ({n_observed})"
        )

    # Vectorized permutation: for each draw, argpartition gives the n_observed
    # smallest random keys (== uniform without-replacement sample).
    perm_hit_rates = np.empty(n_perms, dtype=np.float64)
    # Process in chunks to bound memory (chunk of 10k * 388 ints8 = ~4MB).
    chunk = 10_000
    for start in range(0, n_perms, chunk):
        end = min(start + chunk, n_perms)
        size = end - start
        keys = rng.random((size, pool_n))
        # idx of n_observed smallest keys per row
        idx = np.argpartition(keys, kth=n_observed - 1, axis=1)[:, :n_observed]
        # gather hits
        hits_chunk = pool_hits[idx].sum(axis=1) / n_observed
        perm_hit_rates[start:end] = hits_chunk

    observed_rate = n_observed and (
        candidate_pool["hit"].sum() / max(len(candidate_pool), 1)
    )
    return perm_hit_rates


def _null_b_within_ticker_shuffle(
    candidate_pool: pd.DataFrame,
    sigma_trades: pd.DataFrame,
    n_perms: int,
    rng: np.random.Generator,
    min_days: int = MIN_TICKER_DAYS,
) -> tuple[np.ndarray, dict]:
    """Null B — for each sigma trade, keep ticker fixed, draw a random day's pnl."""
    # Build per-ticker hit array
    ticker_to_hits: dict[str, np.ndarray] = {}
    for tk, sub in candidate_pool.groupby("ticker"):
        ticker_to_hits[tk] = sub["hit"].to_numpy(dtype=np.int8)

    eligible_tickers = []
    dropped_tickers = []
    eligible_arrays = []
    for tk in sigma_trades["ticker"].tolist():
        arr = ticker_to_hits.get(tk, np.array([], dtype=np.int8))
        if arr.shape[0] >= min_days:
            eligible_tickers.append(tk)
            eligible_arrays.append(arr)
        else:
            dropped_tickers.append((tk, int(arr.shape[0])))

    n_effective = len(eligible_tickers)
    if n_effective == 0:
        return np.array([], dtype=np.float64), {
            "n_effective": 0,
            "n_tickers_dropped_due_to_insufficient_days": len(dropped_tickers),
            "dropped_tickers": dropped_tickers,
        }

    # Vectorized: precompute pool sizes per slot, draw random uniforms,
    # and convert to indices via floor(u * size).
    pool_sizes = np.array([a.shape[0] for a in eligible_arrays], dtype=np.int64)
    # Stack hit arrays into a ragged structure: build a 2D matrix where
    # each row is one trade's pool, padded; use direct gather instead.
    perm_hit_rates = np.empty(n_perms, dtype=np.float64)
    chunk = 10_000
    for start in range(0, n_perms, chunk):
        end = min(start + chunk, n_perms)
        size = end - start
        # uniform in [0, 1) per (perm, slot)
        u = rng.random((size, n_effective))
        # convert to integer index per slot
        idx = np.floor(u * pool_sizes[np.newaxis, :]).astype(np.int64)
        # Gather: for each slot j, look up eligible_arrays[j][idx[:, j]]
        hits_acc = np.zeros(size, dtype=np.float64)
        for j, arr in enumerate(eligible_arrays):
            hits_acc += arr[idx[:, j]]
        perm_hit_rates[start:end] = hits_acc / n_effective

    info = {
        "n_effective": n_effective,
        "n_tickers_dropped_due_to_insufficient_days": len(dropped_tickers),
        "dropped_tickers": dropped_tickers,
    }
    return perm_hit_rates, info


def _summarize_perms(arr: np.ndarray) -> dict:
    if arr.size == 0:
        return {
            "perm_hit_rates_min": None,
            "perm_hit_rates_max": None,
            "perm_hit_rates_mean": None,
            "perm_hit_rates_p50": None,
            "perm_hit_rates_p95": None,
            "perm_hit_rates_p99": None,
        }
    return {
        "perm_hit_rates_min": float(np.min(arr)),
        "perm_hit_rates_max": float(np.max(arr)),
        "perm_hit_rates_mean": float(np.mean(arr)),
        "perm_hit_rates_p50": float(np.percentile(arr, 50)),
        "perm_hit_rates_p95": float(np.percentile(arr, 95)),
        "perm_hit_rates_p99": float(np.percentile(arr, 99)),
    }


def main(
    in_sample_csv: Path = DEFAULT_IN_SAMPLE_CSV,
    n_perms: int = DEFAULT_N_PERMS,
    seed: int = DEFAULT_SEED,
    sigma_threshold: float = SIGMA_THRESHOLD,
    min_ticker_days: int = MIN_TICKER_DAYS,
) -> dict:
    """Compute Tier 1 permutation null p-values and return a JSON-ready dict."""
    t0 = time.perf_counter()
    in_sample_csv = Path(in_sample_csv)
    df = _load_trades(in_sample_csv)
    sigma_trades = df[df["abs_z"] >= sigma_threshold].copy()
    n_observed = len(sigma_trades)
    if n_observed == 0:
        raise ValueError(
            f"no trades with abs_z >= {sigma_threshold} in {in_sample_csv}"
        )
    observed_hits = int(sigma_trades["hit"].sum())
    observed_hit_rate = observed_hits / n_observed

    rng = np.random.default_rng(seed)

    # Null A
    perm_a = _null_a_random_sampling(
        candidate_pool=df,
        n_observed=n_observed,
        n_perms=n_perms,
        rng=rng,
    )
    # p-value: P(perm_rate >= observed)
    p_a = float(np.mean(perm_a >= observed_hit_rate - 1e-12))

    # Null B (independent rng draws from same generator — fine, both are
    # consumed in deterministic order after Null A)
    perm_b, b_info = _null_b_within_ticker_shuffle(
        candidate_pool=df,
        sigma_trades=sigma_trades,
        n_perms=n_perms,
        rng=rng,
        min_days=min_ticker_days,
    )
    if perm_b.size > 0:
        # Recompute the comparable observed hit rate over only the
        # surviving (non-dropped) sigma trades, to keep Null B internally
        # consistent. The classic bench-line is the original 92.86% but
        # since N changes we report both.
        eligible_tickers_set = {
            t for t in sigma_trades["ticker"].tolist()
            if (t, ) not in {(d[0], ) for d in b_info["dropped_tickers"]}
        }
        sigma_eff = sigma_trades[sigma_trades["ticker"].isin(eligible_tickers_set)]
        observed_hits_eff = int(sigma_eff["hit"].sum())
        observed_rate_eff = observed_hits_eff / len(sigma_eff) if len(sigma_eff) else 0.0
        p_b = float(np.mean(perm_b >= observed_rate_eff - 1e-12))
    else:
        observed_rate_eff = None
        observed_hits_eff = 0
        p_b = None

    elapsed = time.perf_counter() - t0

    summary_a = _summarize_perms(perm_a)
    summary_b = _summarize_perms(perm_b)

    out = {
        "hypothesis_id": HYPOTHESIS_ID,
        "in_sample_csv": str(in_sample_csv).replace("\\", "/"),
        "sigma_threshold": sigma_threshold,
        "n_observed_trades": int(n_observed),
        "observed_hits": int(observed_hits),
        "observed_hit_rate_pct": round(float(observed_hit_rate * 100), 4),
        "n_perms": int(n_perms),
        "seed": int(seed),
        "candidate_pool_size": int(len(df)),
        "null_a_random_sampling": {
            "p_value": p_a,
            **summary_a,
        },
        "null_b_within_ticker_shuffle": {
            "min_ticker_days": int(min_ticker_days),
            "n_effective": int(b_info["n_effective"]),
            "n_tickers_dropped_due_to_insufficient_days": int(
                b_info["n_tickers_dropped_due_to_insufficient_days"]
            ),
            "dropped_tickers": [
                {"ticker": t, "pool_size": n} for (t, n) in b_info["dropped_tickers"]
            ],
            "observed_hits_eff": int(observed_hits_eff),
            "observed_hit_rate_eff_pct": (
                round(float(observed_rate_eff * 100), 4)
                if observed_rate_eff is not None
                else None
            ),
            "p_value": p_b,
            **summary_b,
        },
        "bonferroni_threshold": BONFERRONI_THRESHOLD,
        "verdict_p_lt_0_000417": bool(
            p_a is not None and p_a < BONFERRONI_THRESHOLD
        ),
        "verdict_null_b_p_lt_0_000417": bool(
            p_b is not None and p_b < BONFERRONI_THRESHOLD
        ),
        "compute_time_seconds": round(elapsed, 3),
    }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tier 1 permutation null for H-2026-04-26-001."
    )
    parser.add_argument(
        "--in-sample-csv",
        type=Path,
        default=DEFAULT_IN_SAMPLE_CSV,
        help="In-sample candidate trades CSV (default: %(default)s)",
    )
    parser.add_argument(
        "--n-perms",
        type=int,
        default=DEFAULT_N_PERMS,
        help="Number of permutations (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="RNG seed (default: %(default)s)",
    )
    parser.add_argument(
        "--sigma-threshold",
        type=float,
        default=SIGMA_THRESHOLD,
        help="abs_z threshold for the observed slice (default: %(default)s)",
    )
    parser.add_argument(
        "--min-ticker-days",
        type=int,
        default=MIN_TICKER_DAYS,
        help="Minimum candidate-day pool per ticker for Null B (default: %(default)s)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for the JSON summary (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    summary = main(
        in_sample_csv=args.in_sample_csv,
        n_perms=args.n_perms,
        seed=args.seed,
        sigma_threshold=args.sigma_threshold,
        min_ticker_days=args.min_ticker_days,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "perm_null_t1_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
