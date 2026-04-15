"""Fit the gap-predictor coefficients on multi-year yfinance history.

Pulls ~4 years of daily closes for each driver + Nifty 50, aligns on the
Indian trading calendar, computes overnight-driver-delta features and the
realised Nifty open-gap target, then fits an OLS linear model:

  nifty_gap_pct[t] = a*Nikkei_Δ + b*KOSPI_Δ + c*Brent_Δ + d*SPY_Δ + e*USDINR_Δ + f*VIX_level_z + intercept

where each Δ is close[t-1] -> close[t] of that asset, measured on its own
calendar. The target is (Nifty_open[t] - Nifty_close[t-1]) / Nifty_close[t-1].

Splits 80/20 for in/out of sample, reports coefficients, in-sample and
out-of-sample R², and writes the coefficients to data/gap_model.json for
the live predictor to consume.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PIPELINE_ROOT.parent / "data" / "gap_model.json"


DRIVERS = {
    "NIKKEI":   "^N225",
    "KOSPI":    "^KS11",
    "BRENT":    "BZ=F",
    "SPY":      "^GSPC",
    "USDINR":   "INR=X",
    "INDIAVIX": "^INDIAVIX",
}
NIFTY = "^NSEI"
YEARS = 4


def _fetch(symbol: str, start: str, end: str) -> Dict[str, Dict[str, float]]:
    """Return {date_str: {open, close}}. yfinance cache-friendly."""
    import yfinance as yf  # noqa: WPS433
    hist = yf.Ticker(symbol).history(start=start, end=end)
    if hist.empty:
        return {}
    out = {}
    for idx, row in hist.iterrows():
        out[idx.strftime("%Y-%m-%d")] = {
            "open":  float(row["Open"]),
            "close": float(row["Close"]),
        }
    return out


def _build_dataset() -> List[Dict]:
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")

    print(f"Fetching {YEARS}y history ({start} .. {end})")
    nifty = _fetch(NIFTY, start, end)
    drivers = {name: _fetch(sym, start, end) for name, sym in DRIVERS.items()}
    for name, d in drivers.items():
        print(f"  {name:<10} {len(d)} days")

    # Build per-Indian-trading-day rows
    indian_days = sorted(nifty.keys())
    rows = []
    for i in range(1, len(indian_days)):
        t = indian_days[i]
        t_minus = indian_days[i - 1]

        today_open = nifty[t]["open"]
        prev_close = nifty[t_minus]["close"]
        if prev_close <= 0:
            continue
        gap_pct = (today_open / prev_close - 1) * 100

        # Feature: each driver's last-available delta at or before t
        features = {}
        for name, series in drivers.items():
            dates = sorted(d for d in series if d <= t)
            # Use the most-recent-by-t close and its predecessor
            if len(dates) < 2:
                features[name] = None
                continue
            c_t = series[dates[-1]]["close"]
            c_prev = series[dates[-2]]["close"]
            if c_prev <= 0:
                features[name] = None
                continue
            features[name] = (c_t / c_prev - 1) * 100

        # For INDIAVIX, also capture level (de-meaned z-ish)
        vix_date = max((d for d in drivers["INDIAVIX"] if d <= t), default=None)
        vix_level = drivers["INDIAVIX"][vix_date]["close"] if vix_date else None

        row = {"date": t, "gap_pct": round(gap_pct, 4), **features, "VIX_level": vix_level}
        # Drop rows with any missing feature
        if any(row.get(name) is None for name in DRIVERS) or vix_level is None:
            continue
        rows.append(row)
    return rows


# -------- minimal OLS (no numpy dependency) --------
def _ols(X: List[List[float]], y: List[float]) -> Tuple[List[float], float]:
    """Solve (X^T X) beta = X^T y by Gaussian elimination.

    X must include an intercept column. Returns (beta, r_squared_in_sample).
    """
    n = len(X)
    p = len(X[0])
    # X^T X (p x p)
    XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    # X^T y (p,)
    Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(p)]
    # Augment
    mat = [row + [rhs] for row, rhs in zip(XtX, Xty)]
    # Gaussian elimination with partial pivoting
    for col in range(p):
        piv = max(range(col, p), key=lambda r: abs(mat[r][col]))
        mat[col], mat[piv] = mat[piv], mat[col]
        if abs(mat[col][col]) < 1e-12:
            return [0.0] * p, 0.0
        inv = 1.0 / mat[col][col]
        mat[col] = [v * inv for v in mat[col]]
        for r in range(p):
            if r != col and mat[r][col] != 0:
                factor = mat[r][col]
                mat[r] = [mat[r][c] - factor * mat[col][c] for c in range(p + 1)]
    beta = [row[-1] for row in mat]

    # R²
    y_mean = sum(y) / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    y_hat = [sum(X[i][j] * beta[j] for j in range(p)) for i in range(n)]
    ss_res = sum((y[i] - y_hat[i]) ** 2 for i in range(n))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return beta, r2


def _predict(beta: List[float], X: List[List[float]]) -> List[float]:
    return [sum(X[i][j] * beta[j] for j in range(len(beta))) for i in range(len(X))]


def _r2(y: List[float], y_hat: List[float]) -> float:
    n = len(y)
    if n == 0:
        return 0.0
    y_mean = sum(y) / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((y[i] - y_hat[i]) ** 2 for i in range(n))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def run_fit() -> Dict:
    rows = _build_dataset()
    print(f"\nAligned dataset: {len(rows)} rows")
    if len(rows) < 100:
        print("Too few rows; aborting.")
        return {}

    feature_keys = ["NIKKEI", "KOSPI", "BRENT", "SPY", "USDINR"]
    # VIX as level deviation from 15
    def _row_features(r):
        f = [r[k] for k in feature_keys]
        f.append(max(0.0, r["VIX_level"] - 15.0))  # excess VIX
        f.append(1.0)                              # intercept
        return f

    # Drop rows with extreme gaps (>|5%|) — data errors / circuit breakers
    clean = [r for r in rows if abs(r["gap_pct"]) <= 5.0]
    print(f"After trim (|gap| <= 5%): {len(clean)} rows")

    # Chronological 80/20 split
    split = int(len(clean) * 0.8)
    train = clean[:split]
    test  = clean[split:]

    X_train = [_row_features(r) for r in train]
    y_train = [r["gap_pct"] for r in train]
    X_test  = [_row_features(r) for r in test]
    y_test  = [r["gap_pct"] for r in test]

    beta, r2_in = _ols(X_train, y_train)
    y_hat_test = _predict(beta, X_test)
    r2_out = _r2(y_test, y_hat_test)

    names = feature_keys + ["VIX_excess", "intercept"]
    coeffs = dict(zip(names, beta))

    print(f"\nCoefficients (fitted on {len(train)} train rows):")
    for name, c in coeffs.items():
        print(f"  {name:<12} {c:+.4f}")
    print(f"\nIn-sample  R²: {r2_in:+.4f}")
    print(f"Out-sample R²: {r2_out:+.4f}")

    # Summary: predict vs actual on test set
    abs_errors = [abs(y_test[i] - y_hat_test[i]) for i in range(len(y_test))]
    mae = sum(abs_errors) / len(abs_errors) if abs_errors else 0.0
    # Direction hit rate: did we predict the right sign?
    sign_hits = sum(1 for i in range(len(y_test))
                    if (y_test[i] > 0) == (y_hat_test[i] > 0))
    sign_rate = sign_hits / len(y_test) * 100 if y_test else 0.0

    # Top predicted magnitudes on test set
    worst_actual = sorted(range(len(y_test)), key=lambda i: -abs(y_test[i]))[:10]
    print(f"\nTest set: n={len(y_test)}, MAE={mae:.3f}%, direction accuracy={sign_rate:.0f}%")
    print(f"Top 10 largest actual gaps vs prediction (test set):")
    for idx in worst_actual:
        r = test[idx]
        print(f"  {r['date']}  actual {y_test[idx]:+.2f}%   predicted {y_hat_test[idx]:+.2f}%")

    out = {
        "updated_at":        datetime.now().isoformat(),
        "train_rows":        len(train),
        "test_rows":         len(test),
        "coefficients":      coeffs,
        "r2_in_sample":      round(r2_in, 4),
        "r2_out_of_sample":  round(r2_out, 4),
        "test_mae_pct":      round(mae, 3),
        "test_direction_accuracy_pct": round(sign_rate, 1),
        "feature_order":     feature_keys + ["VIX_excess", "intercept"],
    }
    MODEL_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {MODEL_PATH}")
    return out


if __name__ == "__main__":
    run_fit()
