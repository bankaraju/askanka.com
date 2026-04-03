"""
Anka Research Pipeline — Correlation Regime Break Detection (ML Module)

Detects correlation regime breaks across Indian equity sector pairs using:
  1. Rolling Pearson correlation with Z-score change-point detection
  2. Feature engineering (volatility, dispersion, beta instability, momentum)
  3. XGBoost classifier for fragility scoring

Data: india_historical/ CSVs (~988 rows x 66 tickers, 2022-2026)
"""

import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Packages live in pipeline/lib/
sys.path.insert(0, str(Path(__file__).parent / "lib"))

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import xgboost as xgb

from config import (
    CORRELATION_PAIRS,
    CORR_WINDOW_SHORT,
    CORR_WINDOW_LONG,
    CORR_BREAK_ZSCORE,
    CORR_BREAK_MIN_SHIFT,
    FRAGILITY_FORWARD_WINDOW,
)

# ---------------------------------------------------------------------------
# Logging & Paths
# ---------------------------------------------------------------------------
log = logging.getLogger("anka.corr_regime")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
HIST_DIR = DATA_DIR / "india_historical"
CORR_HISTORY_FILE = DATA_DIR / "correlation_history.json"
FRAGILITY_FILE = DATA_DIR / "fragility_scores.json"
MODEL_META_FILE = DATA_DIR / "fragility_model.json"

# Cache for trained model so --score-only works
_TRAINED_MODEL_CACHE: dict = {}


# ══════════════════════════════════════════════════════════════
# Stage 1: Rolling Correlation
# ══════════════════════════════════════════════════════════════

def load_price_series(ticker: str) -> pd.Series:
    """Load closing prices for a ticker from india_historical/ CSV.

    Returns a pd.Series indexed by date with daily close prices.
    """
    csv_path = HIST_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        log.warning("No historical CSV for %s", ticker)
        return pd.Series(dtype=float)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.sort_values("Date").drop_duplicates(subset="Date")
    return pd.Series(df["Close"].values, index=df["Date"], name=ticker, dtype=float)


def compute_rolling_correlation(
    prices_a: pd.Series,
    prices_b: pd.Series,
    window: int = 21,
) -> pd.Series:
    """Compute rolling Pearson correlation of daily returns.

    First `window-1` values are NaN (insufficient data for rolling window).
    """
    combined = pd.DataFrame({"a": prices_a, "b": prices_b}).dropna()
    if len(combined) < window + 5:
        return pd.Series(dtype=float)

    ret_a = combined["a"].pct_change()
    ret_b = combined["b"].pct_change()

    rolling_corr = ret_a.rolling(window=window).corr(ret_b)
    rolling_corr.name = "rolling_corr"
    return rolling_corr


def detect_change_points(
    rolling_corr: pd.Series,
    zscore_threshold: float = 2.0,
    min_shift: float = 0.3,
) -> list[dict]:
    """Detect days where correlation shifts significantly.

    Uses Z-score of day-over-day correlation change vs rolling std of changes.

    Returns list of dicts with keys: date, old_corr, new_corr, zscore, shift.
    """
    if rolling_corr.empty or rolling_corr.dropna().empty:
        return []

    corr_clean = rolling_corr.dropna()
    daily_change = corr_clean.diff()

    # Rolling stats of the daily change (use 21-day window for stable stats)
    roll_mean = daily_change.rolling(21, min_periods=10).mean()
    roll_std = daily_change.rolling(21, min_periods=10).std()

    # Avoid division by zero
    roll_std = roll_std.replace(0, np.nan)

    z_scores = (daily_change - roll_mean) / roll_std

    breaks = []
    for date, z in z_scores.items():
        if pd.isna(z):
            continue
        if abs(z) < zscore_threshold:
            continue

        shift = daily_change.loc[date]
        if abs(shift) < min_shift:
            continue

        new_corr = corr_clean.loc[date]
        old_corr = new_corr - shift

        breaks.append({
            "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
            "old_corr": round(float(old_corr), 4),
            "new_corr": round(float(new_corr), 4),
            "zscore": round(float(z), 2),
            "shift": round(float(shift), 4),
        })

    return breaks


def label_regimes(
    rolling_corr: pd.Series,
    breaks: list[dict],
    forward_window: int = 5,
) -> pd.Series:
    """Label each date as regime state.

    0 = STABLE, 1 = PRE_BREAK (within forward_window days before a break), 2 = BREAK.
    """
    labels = pd.Series(0, index=rolling_corr.index, dtype=int, name="regime")

    if not breaks:
        return labels

    # Parse break dates
    break_dates = []
    for b in breaks:
        d = pd.Timestamp(b["date"])
        if d in labels.index:
            break_dates.append(d)

    # Mark BREAK days
    for bd in break_dates:
        labels.loc[bd] = 2

    # Mark PRE_BREAK: forward_window trading days before each break
    sorted_index = labels.index.sort_values()
    index_list = sorted_index.tolist()

    for bd in break_dates:
        try:
            pos = index_list.index(bd)
        except ValueError:
            continue
        start = max(0, pos - forward_window)
        for i in range(start, pos):
            if labels.iloc[i] == 0:  # don't overwrite BREAK
                labels.iloc[i] = 1

    return labels


# ══════════════════════════════════════════════════════════════
# Stage 2: Full History
# ══════════════════════════════════════════════════════════════

def compute_all_pair_correlations(
    pairs: list[dict] | None = None,
    windows: list[int] | None = None,
) -> dict:
    """Compute rolling correlations + detect breaks for all pairs.

    Returns dict keyed by pair name with:
      - corr_weekly: weekly-sampled correlation time series
      - breaks: list of detected change points
      - current_corr: latest correlation value
      - label_counts: count of each regime label
    """
    if pairs is None:
        pairs = CORRELATION_PAIRS
    if windows is None:
        windows = [CORR_WINDOW_SHORT, CORR_WINDOW_LONG]

    results = {}

    for pair in pairs:
        name = pair["name"]
        log.info("Computing correlations for %s (%s vs %s)", name, pair["a"], pair["b"])

        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])

        if prices_a.empty or prices_b.empty:
            log.warning("Missing price data for %s, skipping", name)
            continue

        # Use short window for primary analysis
        rc = compute_rolling_correlation(prices_a, prices_b, window=windows[0])
        if rc.empty:
            continue

        breaks = detect_change_points(rc, CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT)
        labels = label_regimes(rc, breaks, FRAGILITY_FORWARD_WINDOW)

        # Weekly sample for JSON storage
        corr_clean = rc.dropna()
        weekly = corr_clean.resample("W-FRI").last().dropna()

        current_corr = float(corr_clean.iloc[-1]) if len(corr_clean) > 0 else None

        label_counts = {
            "stable": int((labels == 0).sum()),
            "pre_break": int((labels == 1).sum()),
            "break": int((labels == 2).sum()),
        }

        results[name] = {
            "corr_weekly": {
                d.strftime("%Y-%m-%d"): round(float(v), 4)
                for d, v in weekly.items()
            },
            "breaks": breaks,
            "current_corr": round(current_corr, 4) if current_corr is not None else None,
            "label_counts": label_counts,
            "pair": pair,
        }

    return results


def save_correlation_history(results: dict) -> None:
    """Save correlation history to data/correlation_history.json."""
    # Strip non-serializable pair config for clean JSON
    out = {}
    for name, data in results.items():
        out[name] = {
            "corr_weekly": data["corr_weekly"],
            "breaks": data["breaks"],
            "current_corr": data["current_corr"],
            "label_counts": data["label_counts"],
        }

    payload = {
        "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "pairs": out,
    }
    CORR_HISTORY_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Saved correlation history to %s", CORR_HISTORY_FILE)


# ══════════════════════════════════════════════════════════════
# Stage 3: Feature Engineering
# ══════════════════════════════════════════════════════════════

def _load_volume_series(ticker: str) -> pd.Series:
    """Load Volume from india_historical/ CSV."""
    csv_path = HIST_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    df = df.sort_values("Date").drop_duplicates(subset="Date")
    return pd.Series(df["Volume"].values, index=df["Date"], name=f"{ticker}_vol", dtype=float)


def engineer_features(
    prices_a: pd.Series,
    prices_b: pd.Series,
    vol_a: pd.Series | None = None,
    vol_b: pd.Series | None = None,
) -> pd.DataFrame:
    """Build feature matrix for correlation regime prediction.

    Returns DataFrame with ~24 feature columns, indexed by date.
    """
    combined = pd.DataFrame({"a": prices_a, "b": prices_b}).dropna()
    if len(combined) < 65:
        return pd.DataFrame()

    ret_a = combined["a"].pct_change()
    ret_b = combined["b"].pct_change()

    feats = pd.DataFrame(index=combined.index)

    # --- Realized volatility ---
    feats["ret_a_5d_vol"] = ret_a.rolling(5).std()
    feats["ret_b_5d_vol"] = ret_b.rolling(5).std()
    feats["ret_a_21d_vol"] = ret_a.rolling(21).std()
    feats["ret_b_21d_vol"] = ret_b.rolling(21).std()

    # --- Vol ratio (spike detection) ---
    feats["vol_ratio_a"] = feats["ret_a_5d_vol"] / feats["ret_a_21d_vol"]
    feats["vol_ratio_b"] = feats["ret_b_5d_vol"] / feats["ret_b_21d_vol"]

    # --- Rolling correlations ---
    feats["corr_21"] = ret_a.rolling(21).corr(ret_b)
    feats["corr_63"] = ret_a.rolling(63).corr(ret_b)

    # --- Correlation rate of change ---
    feats["corr_change_5d"] = feats["corr_21"].diff(5)
    feats["corr_change_21d"] = feats["corr_21"].diff(21)

    # --- Correlation divergence ---
    feats["corr_divergence"] = feats["corr_21"] - feats["corr_63"]

    # --- Dispersion (cross-sectional return spread volatility) ---
    spread = ret_a - ret_b
    feats["dispersion_5d"] = spread.rolling(5).std()
    feats["dispersion_21d"] = spread.rolling(21).std()
    feats["dispersion_ratio"] = feats["dispersion_5d"] / feats["dispersion_21d"]

    # --- Volume shock ---
    if vol_a is not None and not vol_a.empty:
        va = vol_a.reindex(combined.index)
        feats["volume_shock_a"] = va / va.rolling(20).mean()
    else:
        feats["volume_shock_a"] = np.nan

    if vol_b is not None and not vol_b.empty:
        vb = vol_b.reindex(combined.index)
        feats["volume_shock_b"] = vb / vb.rolling(20).mean()
    else:
        feats["volume_shock_b"] = np.nan

    # --- Rolling beta & instability ---
    cov_ab = ret_a.rolling(21).cov(ret_b)
    var_b = ret_b.rolling(21).var()
    feats["beta_21"] = cov_ab / var_b
    feats["beta_instability"] = feats["beta_21"].rolling(21).std()

    # --- Return momentum ---
    feats["ret_a_5d"] = combined["a"].pct_change(5)
    feats["ret_b_5d"] = combined["b"].pct_change(5)
    feats["ret_a_21d"] = combined["a"].pct_change(21)
    feats["ret_b_21d"] = combined["b"].pct_change(21)

    # --- Spread momentum (return divergence) ---
    feats["spread_momentum_5d"] = feats["ret_a_5d"] - feats["ret_b_5d"]
    feats["spread_momentum_21d"] = feats["ret_a_21d"] - feats["ret_b_21d"]

    # Replace inf with NaN
    feats.replace([np.inf, -np.inf], np.nan, inplace=True)

    return feats


# ══════════════════════════════════════════════════════════════
# Stage 4: XGBoost Model
# ══════════════════════════════════════════════════════════════

def _build_training_data(
    pairs: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Pool features + binary labels across all pairs.

    Label: 1 = PRE_BREAK or BREAK, 0 = STABLE.
    """
    if pairs is None:
        pairs = CORRELATION_PAIRS

    all_features = []
    all_labels = []

    for pair in pairs:
        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])
        if prices_a.empty or prices_b.empty:
            continue

        vol_a = _load_volume_series(pair["a"])
        vol_b = _load_volume_series(pair["b"])

        feats = engineer_features(prices_a, prices_b, vol_a, vol_b)
        if feats.empty:
            continue

        # Compute labels
        rc = compute_rolling_correlation(prices_a, prices_b, window=CORR_WINDOW_SHORT)
        if rc.empty:
            continue

        breaks = detect_change_points(rc, CORR_BREAK_ZSCORE, CORR_BREAK_MIN_SHIFT)
        regime_labels = label_regimes(rc, breaks, FRAGILITY_FORWARD_WINDOW)

        # Align features and labels on common index
        common_idx = feats.index.intersection(regime_labels.index)
        feats_aligned = feats.loc[common_idx]
        labels_aligned = regime_labels.loc[common_idx]

        # Binary: 1 = pre-break or break, 0 = stable
        binary_labels = (labels_aligned >= 1).astype(int)

        # Drop rows with NaN features
        valid_mask = feats_aligned.notna().all(axis=1)
        feats_clean = feats_aligned.loc[valid_mask]
        labels_clean = binary_labels.loc[valid_mask]

        if len(feats_clean) > 0:
            all_features.append(feats_clean)
            all_labels.append(labels_clean)

    if not all_features:
        return pd.DataFrame(), pd.Series(dtype=int)

    X = pd.concat(all_features, axis=0)
    y = pd.concat(all_labels, axis=0)
    return X, y


def train_fragility_model(min_pairs: int = 5) -> dict:
    """Train XGBoost classifier with walk-forward 80/20 split.

    Handles class imbalance via scale_pos_weight.
    Caches model in _TRAINED_MODEL_CACHE.

    Returns dict with training metrics and feature importance.
    """
    global _TRAINED_MODEL_CACHE

    X, y = _build_training_data()

    if X.empty or len(X) < 100:
        raise ValueError(f"Insufficient training data: {len(X)} rows")

    # Walk-forward split (time-ordered: first 80% train, last 20% test)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    # Class imbalance handling
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    scale_weight = n_neg / max(n_pos, 1)

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_weight,
        eval_metric="logloss",
        verbosity=0,
        use_label_encoder=False,
    )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    # Feature importance (sorted descending)
    importance = dict(zip(X.columns, model.feature_importances_))
    importance_sorted = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    # Cache
    _TRAINED_MODEL_CACHE["model"] = model
    _TRAINED_MODEL_CACHE["feature_names"] = list(X.columns)
    _TRAINED_MODEL_CACHE["trained_at"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    result = {
        "trained_at": _TRAINED_MODEL_CACHE["trained_at"],
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "class_balance": {"stable": int(n_neg), "break_events": int(n_pos)},
        "scale_pos_weight": round(float(scale_weight), 2),
        "accuracy": round(float(acc), 4),
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "f1_score": round(float(f1), 4),
        "feature_importance": {k: round(float(v), 4) for k, v in importance_sorted.items()},
    }

    # Save model metadata
    MODEL_META_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info("Model trained: acc=%.3f prec=%.3f rec=%.3f f1=%.3f", acc, prec, rec, f1)

    return result


def score_current_fragility(
    pairs: list[dict] | None = None,
) -> dict:
    """Score latest row of features for each pair using cached model.

    Returns dict keyed by pair name with fragility_score (0-100),
    probability, top_drivers, and current_corr_21.
    """
    if "model" not in _TRAINED_MODEL_CACHE:
        raise RuntimeError("No trained model in cache. Run train_fragility_model() first.")

    model = _TRAINED_MODEL_CACHE["model"]
    feature_names = _TRAINED_MODEL_CACHE["feature_names"]

    if pairs is None:
        pairs = CORRELATION_PAIRS

    scores = {}

    for pair in pairs:
        name = pair["name"]
        prices_a = load_price_series(pair["a"])
        prices_b = load_price_series(pair["b"])
        if prices_a.empty or prices_b.empty:
            continue

        vol_a = _load_volume_series(pair["a"])
        vol_b = _load_volume_series(pair["b"])

        feats = engineer_features(prices_a, prices_b, vol_a, vol_b)
        if feats.empty:
            continue

        # Use only the columns the model was trained on
        feats = feats.reindex(columns=feature_names)

        # Get latest valid row
        latest_valid = feats.dropna()
        if latest_valid.empty:
            continue

        latest_row = latest_valid.iloc[[-1]]

        # Predict
        prob = float(model.predict_proba(latest_row)[:, 1][0])
        fragility_score = round(prob * 100, 1)

        # Top drivers: features with highest absolute value * importance
        importances = dict(zip(feature_names, model.feature_importances_))
        row_values = latest_row.iloc[0]
        # Weight by (abs_z_approx * feature_importance) — simple ranking
        driver_scores = {}
        for feat in feature_names:
            imp = importances.get(feat, 0)
            val = abs(float(row_values[feat])) if not pd.isna(row_values[feat]) else 0
            driver_scores[feat] = imp * val

        top_drivers = sorted(driver_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        top_drivers = [{"feature": f, "contribution": round(float(s), 4)} for f, s in top_drivers]

        # Current 21-day correlation
        current_corr_21 = float(latest_valid["corr_21"].iloc[-1]) if "corr_21" in latest_valid.columns else None

        scores[name] = {
            "fragility_score": fragility_score,
            "probability": round(prob, 4),
            "top_drivers": top_drivers,
            "current_corr_21": round(current_corr_21, 4) if current_corr_21 is not None else None,
            "scored_date": latest_valid.index[-1].strftime("%Y-%m-%d"),
        }

    return scores


def save_fragility_scores(scores: dict) -> None:
    """Save fragility scores to data/fragility_scores.json."""
    payload = {
        "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "model_trained_at": _TRAINED_MODEL_CACHE.get("trained_at", "unknown"),
        "scores": scores,
    }
    FRAGILITY_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Saved fragility scores to %s", FRAGILITY_FILE)
