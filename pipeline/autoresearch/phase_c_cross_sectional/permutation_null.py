"""Section 9B.2 streaming label-permutation null for H-2026-04-24-003.

For each of n_shuffles shuffles of y_train:
  1. Refit Lasso at fixed alpha (no CV — would explode runtime and change the test).
  2. Predict on X_test.
  3. Recompute epsilon from shuffled training preds.
  4. Apply trading rule: LONG if pred>eps, SHORT if pred<-eps, else FLAT.
  5. Subtract S1 cost (cost_pct = 0.30 per project baseline).
  6. Compute S1 Sharpe on non-FLAT signed returns, subtract strongest_naive_sharpe.
  7. Return scalar margin.

The margin vs observed is streamed into a running count for p-value.
Parallelised via concurrent.futures.ProcessPoolExecutor on n_workers.
"""
from __future__ import annotations

import concurrent.futures as cf
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler


def _sharpe(returns_pct: np.ndarray, ann_factor: int = 252) -> float:
    arr = returns_pct[~np.isnan(returns_pct)]
    if arr.size < 2 or arr.std(ddof=1) == 0:
        return 0.0
    return float(arr.mean() / arr.std(ddof=1) * np.sqrt(ann_factor))


def single_shuffle_margin(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test_gross: pd.Series,
    *,
    strongest_naive_sharpe: float,
    alpha: float,
    seed: int,
    cost_pct: float,
) -> float:
    rng = np.random.default_rng(seed)
    y_shuffled = rng.permutation(y_train.to_numpy(float))
    X_tr = X_train.to_numpy(float)
    X_te = X_test.to_numpy(float)
    scaler = StandardScaler().fit(X_tr)
    model = Lasso(alpha=alpha, max_iter=50_000, random_state=seed)
    model.fit(scaler.transform(X_tr), y_shuffled)
    train_preds = model.predict(scaler.transform(X_tr))
    test_preds = model.predict(scaler.transform(X_te))
    eps = float(0.5 * np.median(np.abs(train_preds)))
    sign = np.where(test_preds > eps, 1.0,
                    np.where(test_preds < -eps, -1.0, 0.0))
    pnl_gross = sign * y_test_gross.to_numpy(float)
    # only non-FLAT trades incur cost
    pnl_net = np.where(sign == 0.0, 0.0, pnl_gross - cost_pct)
    # Sharpe only over traded events
    traded = pnl_net[sign != 0.0]
    sharpe = _sharpe(traded)
    return float(sharpe - strongest_naive_sharpe)


def _worker(args):
    return single_shuffle_margin(**args)


def run_label_permutation_null(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test_gross: pd.Series,
    *,
    strongest_naive_sharpe: float,
    observed_margin: float,
    alpha: float,
    n_shuffles: int,
    seed: int,
    cost_pct: float = 0.30,
    n_workers: int | None = None,
) -> dict:
    n_workers = n_workers or max(1, (os.cpu_count() or 2) - 1)
    ss = np.random.SeedSequence(seed).spawn(n_shuffles)
    seeds = [int(s.generate_state(1)[0]) for s in ss]

    jobs = [
        dict(
            X_train=X_train, y_train=y_train,
            X_test=X_test, y_test_gross=y_test_gross,
            strongest_naive_sharpe=strongest_naive_sharpe,
            alpha=alpha, seed=sd, cost_pct=cost_pct,
        )
        for sd in seeds
    ]

    margins = np.empty(n_shuffles, dtype=np.float32)
    if n_workers == 1:
        for i, j in enumerate(jobs):
            margins[i] = _worker(j)
    else:
        with cf.ProcessPoolExecutor(max_workers=n_workers) as ex:
            for i, m in enumerate(ex.map(_worker, jobs, chunksize=64)):
                margins[i] = m

    n_ge = int((margins >= observed_margin).sum())
    p = (n_ge + 1) / (n_shuffles + 1)
    return {
        "p_value": float(p),
        "observed_margin": float(observed_margin),
        "n_shuffles_completed": int(n_shuffles),
        "n_workers": int(n_workers),
        "strongest_naive_sharpe": float(strongest_naive_sharpe),
        "alpha_used": float(alpha),
        "cost_pct": float(cost_pct),
        "margin_samples_preview": margins[:50].tolist(),
        "margin_p50": float(np.median(margins)),
        "margin_p95": float(np.quantile(margins, 0.95)),
        "margin_p99": float(np.quantile(margins, 0.99)),
    }
