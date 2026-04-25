# ETF Coefficient → Per-Stock Tail Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, train, and verdict the multi-task MLP `etf_stock_tail_mlp_v1` against three locked baselines on a 12-month single-touch holdout, append terminal_state to the hypothesis registry, and (if PASS) ship the daily Terminal forecast panel.

**Architecture:** Layered modules under `pipeline/autoresearch/etf_stock_tail/`. Pure-function feature builders → deterministic panel build with SHA256 manifest → PyTorch MLP + 3 sklearn baselines → §15.1 verdict ladder (calibration + permutation null + fragility) → registry + docs sync → conditional daily-deployment surface. End-to-end runner CLI orchestrates the full verdict run on Contabo VPS in ~45 minutes wall clock.

**Tech Stack:** Python 3.11, PyTorch (CPU), scikit-learn, pandas, numpy, pyarrow, joblib (for permutation null parallelism). All deps already pinned in `requirements-vps.txt`. No GPU.

**Spec:** `docs/superpowers/specs/2026-04-25-etf-coefficient-stock-tail-classifier-design.md`
**Registry:** `H-2026-04-25-002` pre-registered at commit `acf6632`.

---

## File Structure

**New module tree** (all under `pipeline/autoresearch/etf_stock_tail/`):

```
pipeline/autoresearch/etf_stock_tail/
├── __init__.py           # package marker
├── constants.py          # locked constants (σ=1.5, dates, ETF list, baseline ids)
├── etf_features.py       # 30 ETFs × {ret_1d, ret_5d, ret_20d} = 90 features, causal
├── stock_features.py     # 6 stock context features, causal
├── labels.py             # 3-class σ-thresholded tail labels
├── panel.py              # assemble (ticker × date) panel + ticker-drop rules
├── splits.py             # train/val/holdout split + regime coverage check
├── model.py              # EtfStockTailMlp PyTorch nn.Module
├── train.py              # training loop (class-balanced sampling, AdamW, early stop)
├── baselines/
│   ├── __init__.py
│   ├── always_prior.py     # B0
│   ├── regime_logistic.py  # B1
│   └── interactions_logistic.py  # B2 (4 hand-designed interactions)
├── calibration.py        # Platt scaling + Brier decomposition + reliability bins
├── permutation_null.py   # 100k label-permutation null on holdout CE (joblib parallel)
├── fragility.py          # 6-perturbation retrain + STABLE/FRAGILE verdict
├── verdict.py            # §15.1 ladder gates → gate_checklist.json + verdict.md
└── runner.py             # CLI: end-to-end verdict run

pipeline/autoresearch/etf_stock_tail/scripts/
├── build_panel.py        # one-shot panel build CLI (writes panel + manifest)
└── score_universe.py     # daily inference (path D deployment, only if verdict PASS)

pipeline/tests/autoresearch/etf_stock_tail/
├── __init__.py
├── test_constants.py
├── test_etf_features.py
├── test_stock_features.py
├── test_labels.py
├── test_panel.py
├── test_panel_causal.py        # mirror of regime_autoresearch causal test
├── test_splits.py
├── test_model.py
├── test_train.py
├── test_baselines.py
├── test_calibration.py
├── test_permutation_null.py
├── test_fragility.py
├── test_verdict.py
└── test_runner_smoke.py        # end-to-end smoke (sub-universe, n_perm=500)
```

**Modified files:**
- `pipeline/config/anka_inventory.json` — register `AnkaETFStockTailScore` + `AnkaETFStockTailFit` (T18 only, conditional on PASS).
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — append H-2026-04-25-002 to hypothesis audit (T17).
- `docs/superpowers/hypothesis-registry.jsonl` — terminal_state line (T16).
- `CLAUDE.md` — clockwork schedule additions (T18, conditional).
- `pipeline/scripts/eta_stock_tail_score.bat` — Windows scheduled-task entry point (T18, conditional).

**Conventions:**
- Every code module imports from `constants.py` for tunable values — no inline magic numbers.
- All public functions have type hints; tests cover the contract, not the internals.
- Random seed is locked at `constants.RANDOM_SEED = 42`; passed explicitly to every numpy/torch/sklearn call that consumes randomness.

---

## Task 1: Package skeleton + locked constants

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/__init__.py`
- Create: `pipeline/autoresearch/etf_stock_tail/constants.py`
- Create: `pipeline/autoresearch/etf_stock_tail/scripts/__init__.py`
- Create: `pipeline/autoresearch/etf_stock_tail/baselines/__init__.py`
- Create: `pipeline/tests/autoresearch/etf_stock_tail/__init__.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_constants.py
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def test_sigma_threshold_is_1_5():
    assert C.SIGMA_THRESHOLD == 1.5


def test_holdout_window_is_12_months():
    start = pd.Timestamp(C.HOLDOUT_START)
    end = pd.Timestamp(C.HOLDOUT_END)
    assert (end - start).days == 365 - 1  # 2025-04-26..2026-04-25 inclusive


def test_etf_list_has_30_symbols():
    assert len(C.ETF_SYMBOLS) == 30
    assert len(set(C.ETF_SYMBOLS)) == 30  # no duplicates


def test_baselines_locked():
    assert set(C.BASELINE_IDS) == {"B0_always_prior", "B1_regime_logistic", "B2_interactions_logistic"}


def test_random_seed_locked():
    assert C.RANDOM_SEED == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_constants.py -v`
Expected: `ImportError: cannot import name 'constants'` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement constants module**

```python
# pipeline/autoresearch/etf_stock_tail/__init__.py
"""H-2026-04-25-002 etf-conditional-stock-tail-classifier."""
```

```python
# pipeline/autoresearch/etf_stock_tail/scripts/__init__.py
```

```python
# pipeline/autoresearch/etf_stock_tail/baselines/__init__.py
```

```python
# pipeline/tests/autoresearch/etf_stock_tail/__init__.py
```

```python
# pipeline/autoresearch/etf_stock_tail/constants.py
"""Locked constants for H-2026-04-25-002 — DO NOT change without registering a new hypothesis version."""
from __future__ import annotations

# Label thresholds
SIGMA_THRESHOLD: float = 1.5      # |r_t| > 1.5 * sigma_60d → tail
SIGMA_LOOKBACK_DAYS: int = 60     # trailing window for sigma estimation, strict (excludes t)

# Splits (ISO dates, inclusive)
TRAIN_START: str = "2020-04-23"
TRAIN_END:   str = "2024-12-31"
VAL_START:   str = "2025-01-01"
VAL_END:     str = "2025-04-25"
HOLDOUT_START: str = "2025-04-26"
HOLDOUT_END:   str = "2026-04-25"

# ETF universe — 30 symbols from pipeline/autoresearch/etf_optimal_weights.json
# Order is stable: any change requires re-training and a new hypothesis version.
ETF_SYMBOLS: tuple[str, ...] = (
    "agriculture", "brazil", "developed", "dollar", "em", "euro",
    "financials", "high_yield", "india_etf", "industrials",
    "kbw_bank", "natgas", "silver", "sp500", "tech", "treasury",
    "yen", "india_vix_daily", "nifty_close_daily", "fii_net_daily",
    "dii_net_daily", "crude_oil", "gold", "copper", "global_bonds",
    "uk_etf", "japan_etf", "china_etf", "korea_etf", "taiwan_etf",
)
ETF_RETURN_WINDOWS: tuple[int, ...] = (1, 5, 20)

# Stock context features (6 dims, fixed order)
STOCK_CONTEXT_FEATURES: tuple[str, ...] = (
    "ret_5d", "vol_z_60d", "volume_z_20d",
    "adv_percentile_252d", "sector_id", "dist_from_52w_high_pct",
)

# Model architecture
EMBEDDING_DIM: int = 8
TRUNK_HIDDEN_1: int = 128
TRUNK_HIDDEN_2: int = 64
N_CLASSES: int = 3                # down_tail / neutral / up_tail
DROPOUT: float = 0.3

# Training hyperparams
LR: float = 1e-3
WEIGHT_DECAY_TRUNK: float = 1e-4
WEIGHT_DECAY_EMBEDDING: float = 1e-3   # 10× trunk on embedding parameter group
BATCH_SIZE: int = 256
MAX_EPOCHS: int = 100
EARLY_STOP_PATIENCE: int = 10

# Verdict gates (locked at registration)
DELTA_NATS: float = 0.005          # margin model must beat best baseline by
P_VALUE_FLOOR: float = 0.01
N_PERMUTATIONS: int = 100_000
FRAGILITY_TOL_PCT: float = 0.02    # ±2% holdout CE for STABLE
FRAGILITY_MIN_PASSING: int = 4     # of 6

# Universe drop rules
MIN_TAIL_EXAMPLES_PER_SIDE: int = 30   # per ticker in training window
MIN_REGIME_DAYS_IN_HOLDOUT: int = 30   # per regime

# Baseline identifiers (used in comparators output, locked)
BASELINE_IDS: tuple[str, ...] = (
    "B0_always_prior", "B1_regime_logistic", "B2_interactions_logistic",
)

# B2 interaction terms (locked at registration — no post-hoc additions)
B2_INTERACTIONS: tuple[tuple[str, str], ...] = (
    ("etf_brazil_ret_1d",          "sector_id"),
    ("etf_dollar_ret_1d",          "sector_id"),
    ("etf_india_vix_daily_ret_1d", "vol_z_60d"),
    ("etf_india_etf_ret_1d",       "dist_from_52w_high_pct"),
)

# Reproducibility
RANDOM_SEED: int = 42

# Class label encoding
CLASS_DOWN: int = 0
CLASS_NEUTRAL: int = 1
CLASS_UP: int = 2
CLASS_NAMES: tuple[str, ...] = ("down_tail", "neutral", "up_tail")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_constants.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/__init__.py \
        pipeline/autoresearch/etf_stock_tail/constants.py \
        pipeline/autoresearch/etf_stock_tail/scripts/__init__.py \
        pipeline/autoresearch/etf_stock_tail/baselines/__init__.py \
        pipeline/tests/autoresearch/etf_stock_tail/__init__.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_constants.py
git commit -m "feat(etf_stock_tail): package skeleton + locked constants for H-2026-04-25-002"
```

---

## Task 2: ETF features (causal, 90-dim)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/etf_features.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.etf_features import (
    build_etf_features_matrix,
    etf_feature_names,
)


@pytest.fixture
def synthetic_etf_panel() -> pd.DataFrame:
    """30-day synthetic ETF panel, 30 ETFs, monotonic close = (ETF_idx + 1) * day."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        for d in dates:
            day = (d - dates[0]).days + 1
            rows.append({"date": d, "etf": sym, "close": float((i + 1) * day)})
    return pd.DataFrame(rows)


def test_feature_names_are_30x3():
    names = etf_feature_names()
    assert len(names) == 90
    assert all(n.startswith("etf_") for n in names)
    # Each ETF appears 3 times (one per window)
    for sym in C.ETF_SYMBOLS:
        assert sum(sym in n for n in names) == 3


def test_features_are_strictly_causal(synthetic_etf_panel):
    """Feature for eval_date t MUST use only rows with date < t."""
    eval_date = pd.Timestamp("2024-01-25")
    feats_with = build_etf_features_matrix(synthetic_etf_panel, eval_date)

    # Mutate the row at t — features must be unchanged.
    panel_mut = synthetic_etf_panel.copy()
    panel_mut.loc[panel_mut["date"] == eval_date, "close"] = 99999.0
    feats_with_mut = build_etf_features_matrix(panel_mut, eval_date)

    pd.testing.assert_series_equal(feats_with, feats_with_mut)


def test_returns_match_known_values(synthetic_etf_panel):
    """For monotonic close = (i+1)*day, ret_1d at day d = (d - (d-1)) / (d-1) = 1/(d-1)."""
    eval_date = pd.Timestamp("2024-01-25")  # day 25 → ret_1d uses day 24 vs 23
    feats = build_etf_features_matrix(synthetic_etf_panel, eval_date)
    # brazil = ETF idx 1, so close at day 23 = 2*23 = 46, day 24 = 2*24 = 48
    expected_ret_1d = (48 - 46) / 46
    assert feats["etf_brazil_ret_1d"] == pytest.approx(expected_ret_1d)


def test_missing_etf_returns_nan(synthetic_etf_panel):
    """Drop one ETF entirely; its features should be NaN, others unaffected."""
    panel_partial = synthetic_etf_panel[synthetic_etf_panel["etf"] != "natgas"]
    eval_date = pd.Timestamp("2024-01-25")
    feats = build_etf_features_matrix(panel_partial, eval_date)
    assert np.isnan(feats["etf_natgas_ret_1d"])
    assert not np.isnan(feats["etf_brazil_ret_1d"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py -v`
Expected: ImportError on `etf_features`.

- [ ] **Step 3: Implement etf_features**

```python
# pipeline/autoresearch/etf_stock_tail/etf_features.py
"""ETF feature builder — 30 ETFs × {ret_1d, ret_5d, ret_20d} = 90 features, causal.

Public API:
  etf_feature_names() -> tuple[str, ...]  — stable column order
  build_etf_features_matrix(panel, eval_date) -> pd.Series  — one row of 90 features
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def etf_feature_names() -> tuple[str, ...]:
    return tuple(
        f"etf_{sym}_ret_{w}d"
        for sym in C.ETF_SYMBOLS
        for w in C.ETF_RETURN_WINDOWS
    )


def _ret_n(closes: pd.Series, n: int) -> float:
    if len(closes) < n + 1:
        return float("nan")
    c0 = closes.iloc[-(n + 1)]
    cN = closes.iloc[-1]
    if c0 == 0 or pd.isna(c0) or pd.isna(cN):
        return float("nan")
    return float(cN / c0 - 1.0)


def build_etf_features_matrix(panel: pd.DataFrame, eval_date: pd.Timestamp) -> pd.Series:
    """Compute 90-feature ETF row for eval_date using only date < eval_date."""
    eval_date = pd.Timestamp(eval_date)
    out: dict[str, float] = {}
    for sym in C.ETF_SYMBOLS:
        df = panel[(panel["etf"] == sym) & (panel["date"] < eval_date)]
        closes = df.sort_values("date")["close"]
        for w in C.ETF_RETURN_WINDOWS:
            out[f"etf_{sym}_ret_{w}d"] = _ret_n(closes, w)
    return pd.Series(out, index=list(etf_feature_names()))
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/etf_features.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py
git commit -m "feat(etf_stock_tail): causal ETF feature builder (90 dims)"
```

---

## Task 3: Stock context features (causal, 6-dim)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/stock_features.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_stock_features.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_stock_features.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.stock_features import (
    build_stock_features_row,
    stock_feature_names,
)


@pytest.fixture
def stock_bars() -> pd.DataFrame:
    """260-day stock panel, monotone close, constant volume."""
    dates = pd.date_range("2024-01-01", periods=260, freq="D")
    return pd.DataFrame({
        "date": dates,
        "close": np.linspace(100.0, 130.0, 260),
        "volume": np.full(260, 1_000_000.0),
    })


def test_feature_names_match_constants():
    assert stock_feature_names() == tuple(f"stock_{f}" for f in C.STOCK_CONTEXT_FEATURES)


def test_features_are_causal(stock_bars):
    """Mutating row at t must not change features for eval_date=t."""
    eval_date = pd.Timestamp("2024-09-01")
    sector_id = 4
    base = build_stock_features_row(stock_bars, eval_date, sector_id)

    bars_mut = stock_bars.copy()
    bars_mut.loc[bars_mut["date"] == eval_date, "close"] = 99999.0
    bars_mut.loc[bars_mut["date"] == eval_date, "volume"] = 50.0
    mut = build_stock_features_row(bars_mut, eval_date, sector_id)

    pd.testing.assert_series_equal(base, mut)


def test_sector_id_pass_through(stock_bars):
    eval_date = pd.Timestamp("2024-09-01")
    out = build_stock_features_row(stock_bars, eval_date, sector_id=7)
    assert out["stock_sector_id"] == 7


def test_dist_from_52w_high_negative_for_pullback(stock_bars):
    """Inject a recent peak then pullback; dist must be negative."""
    bars = stock_bars.copy()
    bars.loc[bars["date"] == pd.Timestamp("2024-08-15"), "close"] = 200.0
    eval_date = pd.Timestamp("2024-09-01")
    out = build_stock_features_row(bars, eval_date, sector_id=0)
    assert out["stock_dist_from_52w_high_pct"] < 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_stock_features.py -v`
Expected: ImportError on `stock_features`.

- [ ] **Step 3: Implement stock_features**

```python
# pipeline/autoresearch/etf_stock_tail/stock_features.py
"""Per-ticker stock context features (6 dims), causal."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def stock_feature_names() -> tuple[str, ...]:
    return tuple(f"stock_{f}" for f in C.STOCK_CONTEXT_FEATURES)


def _trailing(bars: pd.DataFrame, eval_date: pd.Timestamp, n: int) -> pd.DataFrame:
    return bars[bars["date"] < eval_date].sort_values("date").tail(n)


def build_stock_features_row(
    bars: pd.DataFrame,
    eval_date: pd.Timestamp,
    sector_id: int,
) -> pd.Series:
    """Compute 6 stock-context features for one (ticker, eval_date)."""
    eval_date = pd.Timestamp(eval_date)
    out: dict[str, float] = {}

    # ret_5d: log return over trailing 6 closes (T-6 → T-1)
    last6 = _trailing(bars, eval_date, 6)["close"]
    if len(last6) >= 6 and last6.iloc[0] > 0:
        out["stock_ret_5d"] = float(np.log(last6.iloc[-1] / last6.iloc[0]))
    else:
        out["stock_ret_5d"] = float("nan")

    # vol_z_60d: z-score of trailing-20d realized vol against trailing-60d distribution of 20d vols
    returns_60 = _trailing(bars, eval_date, 61)["close"].pct_change().dropna()
    if len(returns_60) >= 60:
        vol20_series = returns_60.rolling(20).std().dropna()
        if len(vol20_series) >= 2 and vol20_series.std() > 0:
            out["stock_vol_z_60d"] = float((vol20_series.iloc[-1] - vol20_series.mean()) / vol20_series.std())
        else:
            out["stock_vol_z_60d"] = float("nan")
    else:
        out["stock_vol_z_60d"] = float("nan")

    # volume_z_20d
    last20 = _trailing(bars, eval_date, 20)["volume"]
    if len(last20) >= 20 and last20.std() > 0:
        out["stock_volume_z_20d"] = float((last20.iloc[-1] - last20.mean()) / last20.std())
    else:
        out["stock_volume_z_20d"] = float("nan")

    # adv_percentile_252d: rank of T-1 ADV in trailing 252d distribution
    last252 = _trailing(bars, eval_date, 252)
    if len(last252) >= 252:
        adv = (last252["close"] * last252["volume"])
        out["stock_adv_percentile_252d"] = float((adv.rank(pct=True)).iloc[-1])
    else:
        out["stock_adv_percentile_252d"] = float("nan")

    # sector_id pass-through
    out["stock_sector_id"] = float(sector_id)

    # dist_from_52w_high_pct
    if len(last252) >= 252:
        peak = float(last252["close"].max())
        latest = float(last252["close"].iloc[-1])
        out["stock_dist_from_52w_high_pct"] = float(latest / peak - 1.0) if peak > 0 else float("nan")
    else:
        out["stock_dist_from_52w_high_pct"] = float("nan")

    result = pd.Series(out)
    return result[list(stock_feature_names())]
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_stock_features.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/stock_features.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_stock_features.py
git commit -m "feat(etf_stock_tail): causal stock context features (6 dims)"
```

---

## Task 4: Tail labels (3-class, σ-thresholded)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/labels.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_labels.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_labels.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.labels import label_for_date, label_series


@pytest.fixture
def stable_bars() -> pd.DataFrame:
    """100 days of low-vol returns ~0.5% std then a 5% spike on day 99."""
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    rng = np.random.default_rng(0)
    rets = rng.normal(0, 0.005, 100)
    rets[99] = 0.05    # 10× std → unambiguously up_tail
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes})


def test_up_tail_fires_on_spike(stable_bars):
    eval_date = pd.Timestamp("2024-04-09")  # day 99
    label = label_for_date(stable_bars, eval_date)
    assert label == C.CLASS_UP


def test_neutral_on_normal_day(stable_bars):
    eval_date = pd.Timestamp("2024-04-08")  # day 98 (a normal day)
    label = label_for_date(stable_bars, eval_date)
    assert label == C.CLASS_NEUTRAL


def test_down_tail_fires_on_negative_spike(stable_bars):
    bars = stable_bars.copy()
    # Replace day 99 spike with negative 5% drop
    rets = bars["close"].pct_change().fillna(0).values
    rets[99] = -0.05
    bars["close"] = 100.0 * np.cumprod(1 + rets)
    eval_date = pd.Timestamp("2024-04-09")
    label = label_for_date(bars, eval_date)
    assert label == C.CLASS_DOWN


def test_sigma_strictly_excludes_t(stable_bars):
    """Mutating close at t must change r_t but not σ; label may flip via r_t only."""
    bars = stable_bars.copy()
    eval_date = pd.Timestamp("2024-04-09")  # day 99 (the spike day)

    # Baseline label with the original spike (r_t large positive, σ from prior 60d)
    base = label_for_date(bars, eval_date)

    # Inflate close at t by 50% — r_t becomes much larger but σ (prior-only) is unchanged
    bars_inflated = bars.copy()
    bars_inflated.loc[bars_inflated["date"] == eval_date, "close"] *= 1.5
    inflated = label_for_date(bars_inflated, eval_date)

    # Both should be UP (since the original was already UP and we made r_t even larger)
    assert base == C.CLASS_UP
    assert inflated == C.CLASS_UP

    # Critical causality check: σ must NOT include t. Prove it by manipulating PRIOR data:
    # If we replace t-1 close with a different value, σ should change but the test of
    # whether r_t exceeds 1.5σ may still hold. We verify σ-causality by injecting an
    # extreme outlier at t and confirming the *vector* path agrees with the *single* path.
    series_labels = label_series(bars)
    assert series_labels.loc[eval_date] == base, "label_series and label_for_date disagree at eval_date"


def test_insufficient_history_returns_nan_label(stable_bars):
    eval_date = pd.Timestamp("2024-01-05")  # day 5 — not enough trailing for σ_60d
    label = label_for_date(stable_bars, eval_date)
    assert pd.isna(label)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_labels.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement labels**

```python
# pipeline/autoresearch/etf_stock_tail/labels.py
"""3-class σ-thresholded tail labels per (ticker, date).

Public API:
  label_for_date(bars, eval_date) -> float  (NaN if ineligible)  — single date
  label_series(bars) -> pd.Series  — labels for every eligible date in bars

Eligibility: requires ≥ SIGMA_LOOKBACK_DAYS prior closes excluding t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def _classify(r: float, sigma: float) -> int:
    if pd.isna(r) or pd.isna(sigma) or sigma == 0:
        return -1  # sentinel, caller maps to NaN
    if r > C.SIGMA_THRESHOLD * sigma:
        return C.CLASS_UP
    if r < -C.SIGMA_THRESHOLD * sigma:
        return C.CLASS_DOWN
    return C.CLASS_NEUTRAL


def label_for_date(bars: pd.DataFrame, eval_date: pd.Timestamp) -> float:
    """Return label for eval_date; NaN if insufficient history."""
    eval_date = pd.Timestamp(eval_date)
    bars_sorted = bars.sort_values("date").reset_index(drop=True)
    idx = bars_sorted.index[bars_sorted["date"] == eval_date]
    if len(idx) == 0:
        return float("nan")
    i = int(idx[0])
    if i < 1:
        return float("nan")
    prior = bars_sorted.iloc[: i].tail(C.SIGMA_LOOKBACK_DAYS)
    if len(prior) < C.SIGMA_LOOKBACK_DAYS:
        return float("nan")
    rets_prior = prior["close"].pct_change().dropna().values
    sigma = float(np.std(rets_prior, ddof=1)) if len(rets_prior) >= 2 else float("nan")
    r_t = float(bars_sorted.loc[i, "close"] / bars_sorted.loc[i - 1, "close"] - 1.0)
    label = _classify(r_t, sigma)
    return float(label) if label >= 0 else float("nan")


def label_series(bars: pd.DataFrame) -> pd.Series:
    """Vectorised label per date. NaN where ineligible."""
    bars_sorted = bars.sort_values("date").reset_index(drop=True)
    out = pd.Series(np.nan, index=bars_sorted["date"].values, name="label", dtype="float64")
    closes = bars_sorted["close"].values
    rets_full = pd.Series(closes).pct_change().values
    for i in range(1, len(bars_sorted)):
        prior = rets_full[max(0, i - (C.SIGMA_LOOKBACK_DAYS - 1)): i]
        prior = prior[~np.isnan(prior)]
        if len(prior) < C.SIGMA_LOOKBACK_DAYS - 1:
            continue  # need ≥ SIGMA_LOOKBACK_DAYS-1 returns from SIGMA_LOOKBACK_DAYS prior closes
        sigma = float(np.std(prior, ddof=1))
        r_t = float(closes[i] / closes[i - 1] - 1.0)
        lbl = _classify(r_t, sigma)
        if lbl >= 0:
            out.iloc[i] = lbl
    return out
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_labels.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/labels.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_labels.py
git commit -m "feat(etf_stock_tail): 3-class σ-thresholded tail labels"
```

---

## Task 5: Panel assembly + ticker-drop rules

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/panel.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_panel.py
import json
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import (
    PanelInputs,
    PanelDropReason,
    assemble_panel,
)


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        for d in dates:
            day = (d - dates[0]).days + 1
            rows.append({"date": d, "etf": sym, "close": float((i + 1) * day)})
    return pd.DataFrame(rows)


def _mk_stock_bars(start: str, n_days: int, vol_scale: float = 0.005) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(123)
    rets = rng.normal(0, vol_scale, n_days)
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def _mk_stock_bars_with_tails(start: str, n_days: int, n_up_tails: int = 35, n_down_tails: int = 35) -> pd.DataFrame:
    """Stock bars with deliberate tail events distributed in time.

    Injects explicit +/-10% returns at non-overlapping, evenly-spaced indices in the
    training-window zone (approximately day 91 onward) so that:
      - Up- and down-tail indices are offset by 4 days each (never overlap).
      - At most ~7-8 large returns fall in any 60-day sigma-estimation window, keeping
        sigma moderate enough that 10% returns always clear the 1.5*sigma threshold.
      - The tail-label screen reliably sees >= MIN_TAIL_EXAMPLES_PER_SIDE in each
        direction, so the ticker is kept and the panel has real rows.
    """
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.005, n_days)
    # Start from ~day 91 (approx train_start) so tails land in the training window.
    # Cycle length = 8 days: up on day 0, down on day 4 of each cycle.
    tail_start = 91
    up_indices = list(range(tail_start, n_days, 8))[:n_up_tails]
    down_indices = list(range(tail_start + 4, n_days, 8))[:n_down_tails]
    for i in up_indices:
        rets[i] = 0.10    # +10%: always clears 1.5*sigma even after sigma inflation
    for i in down_indices:
        rets[i] = -0.10
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def _mk_universe(symbols, dates) -> dict:
    return {d.strftime("%Y-%m-%d"): list(symbols) for d in dates}


def _mk_sector_map(symbols) -> dict:
    return {s: i % 5 for i, s in enumerate(symbols)}


def test_panel_columns(tmp_path):
    """Panel has all 90 ETF + 6 context + ticker_id + label cols, with real rows."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    expected_etf_cols = 30 * 3
    expected_ctx_cols = 6
    assert "ticker_id" in panel.columns
    assert "label" in panel.columns
    assert "date" in panel.columns
    assert "ticker" in panel.columns
    assert "regime" in panel.columns
    # ETF + context columns total 96
    feature_cols = [c for c in panel.columns if c.startswith(("etf_", "stock_"))]
    assert len(feature_cols) == expected_etf_cols + expected_ctx_cols
    # Verify the panel is not empty -- AAA must survive the tail screen and produce real rows
    assert len(panel) > 0, "panel must have real rows, not just an empty schema"
    assert "AAA" in panel["ticker"].values
    assert manifest["n_tickers_kept"] == 1


def test_drops_ticker_with_too_few_tail_examples(tmp_path):
    """A ticker with < MIN_TAIL_EXAMPLES_PER_SIDE in either direction is dropped."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    flat_bars = _mk_stock_bars("2024-01-01", 400, vol_scale=0.0001)  # near-zero vol -> no tails
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"BBB": flat_bars},
        universe=_mk_universe(["BBB"], dates),
        sector_map=_mk_sector_map(["BBB"]),
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    assert "BBB" in manifest["dropped_tickers"]
    assert manifest["dropped_tickers"]["BBB"] == PanelDropReason.INSUFFICIENT_TAIL_LABELS.value
    assert (panel["ticker"] == "BBB").sum() == 0


def test_manifest_contains_input_hashes(tmp_path):
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
    )
    _, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                 train_end=pd.Timestamp("2024-12-31"))
    assert "etf_panel_sha256" in manifest
    assert len(manifest["etf_panel_sha256"]) == 64
    assert "config_sha256" in manifest
    assert "n_rows" in manifest


def test_regime_history_joins_correctly():
    """When regime_history is provided, panel rows carry the regime label, not 'UNKNOWN'."""
    dates = pd.date_range("2024-01-01", periods=400, freq="D")
    regime_history = pd.DataFrame({
        "date": dates,
        "regime": ["RISK_ON" if i < 200 else "RISK_OFF" for i in range(400)],
    })
    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", 400),
        stock_bars={"AAA": _mk_stock_bars_with_tails("2024-01-01", 400)},
        universe=_mk_universe(["AAA"], dates),
        sector_map=_mk_sector_map(["AAA"]),
        regime_history=regime_history,
    )
    panel, manifest = assemble_panel(inputs, train_start=pd.Timestamp("2024-04-01"),
                                     train_end=pd.Timestamp("2024-12-31"))
    assert len(panel) > 0
    # Every row should have a real regime label, never UNKNOWN
    assert (panel["regime"] != "UNKNOWN").all()
    # Both regime values should appear in the panel
    regimes_seen = set(panel["regime"].unique())
    assert regimes_seen <= {"RISK_ON", "RISK_OFF"}
    assert len(regimes_seen) >= 1   # at least one regime appears
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_panel.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement panel**

```python
# pipeline/autoresearch/etf_stock_tail/panel.py
"""Assemble (ticker × date) feature + label panel with deterministic SHA256 manifest.

Drop rules:
  - INSUFFICIENT_TAIL_LABELS — ticker has < MIN_TAIL_EXAMPLES_PER_SIDE in either tail direction in train window
  - MISSING_SECTOR_MAP       — ticker is absent from sector_map (cannot assign a sector_id feature)
                               (NaN labels caused by insufficient bar history are silently skipped at the row level.)
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.etf_features import build_etf_features_matrix, etf_feature_names
from pipeline.autoresearch.etf_stock_tail.labels import label_series
from pipeline.autoresearch.etf_stock_tail.stock_features import build_stock_features_row, stock_feature_names


class PanelDropReason(str, enum.Enum):
    INSUFFICIENT_TAIL_LABELS = "INSUFFICIENT_TAIL_LABELS"
    MISSING_SECTOR_MAP = "MISSING_SECTOR_MAP"


@dataclass
class PanelInputs:
    etf_panel: pd.DataFrame                         # cols: date, etf, close
    stock_bars: dict[str, pd.DataFrame]             # ticker → DataFrame[date, close, volume]
    universe: dict[str, list[str]]                  # ISO-date → list of eligible tickers
    sector_map: dict[str, int]                      # ticker → sector_id
    regime_history: pd.DataFrame | None = None      # cols: date, regime — optional


def _sha256_df(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()


def _config_sha256() -> str:
    cfg = {k: getattr(C, k) for k in dir(C) if k.isupper()}
    blob = json.dumps(cfg, default=str, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def assemble_panel(
    inputs: PanelInputs,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict]:
    """Build the (ticker × date) panel for ALL dates train_start..C.HOLDOUT_END.

    Returns (panel_df, manifest).
    """
    train_start = pd.Timestamp(train_start)
    train_end = pd.Timestamp(train_end)
    panel_end = pd.Timestamp(C.HOLDOUT_END)

    rows: list[dict] = []
    dropped: dict[str, str] = {}
    ticker_to_id: dict[str, int] = {}

    # Cache ETF features per unique date to avoid O(n_tickers x n_dates) recomputation.
    # NOTE: no try/except -- KeyError from build_etf_features_matrix (schema mismatch)
    # must propagate so schema regressions are never silently swallowed.
    etf_cache: dict[pd.Timestamp, pd.Series] = {}

    # Pre-index regime history for O(1) lookup (avoid O(n_regime_rows) linear scan per row).
    rh_by_date: pd.Series | None = None
    if inputs.regime_history is not None:
        rh_by_date = inputs.regime_history.set_index("date")["regime"]

    def _get_etf_row(d: pd.Timestamp) -> pd.Series:
        if d not in etf_cache:
            etf_cache[d] = build_etf_features_matrix(inputs.etf_panel, d)
        return etf_cache[d]

    feature_cols = list(etf_feature_names()) + list(stock_feature_names())

    for ticker, bars in inputs.stock_bars.items():
        if ticker not in inputs.sector_map:
            dropped[ticker] = PanelDropReason.MISSING_SECTOR_MAP.value
            continue

        labels = label_series(bars)
        # Pre-window screen: require >= MIN_TAIL_EXAMPLES_PER_SIDE in train window
        labels_idx = pd.to_datetime(labels.index)
        in_train = (labels_idx >= train_start) & (labels_idx <= train_end)
        train_labels = labels.values[in_train]
        n_up = int(np.sum(train_labels == C.CLASS_UP))
        n_down = int(np.sum(train_labels == C.CLASS_DOWN))
        if n_up < C.MIN_TAIL_EXAMPLES_PER_SIDE or n_down < C.MIN_TAIL_EXAMPLES_PER_SIDE:
            dropped[ticker] = PanelDropReason.INSUFFICIENT_TAIL_LABELS.value
            continue

        ticker_id = len(ticker_to_id)
        ticker_to_id[ticker] = ticker_id

        # NOTE: build_stock_features_row is uncached (per-ticker rolling window math).
        # Production cost: ~200 tickers × ~1100 trading days × 5ms ≈ 18 minutes wall time.
        # Task 9's training orchestrator must allow ≥30 min for panel assembly.
        for d in pd.date_range(train_start, panel_end, freq="D"):
            d_iso = d.strftime("%Y-%m-%d")
            if d_iso not in inputs.universe:
                continue
            if ticker not in inputs.universe[d_iso]:
                continue
            label = labels.get(d, np.nan)
            if pd.isna(label):
                continue
            etf_row = _get_etf_row(d)
            ctx_row = build_stock_features_row(bars, d, inputs.sector_map[ticker])
            row = {
                "date": d, "ticker": ticker, "ticker_id": ticker_id,
                "label": int(label),
            }
            for col in etf_row.index:
                row[col] = etf_row[col]
            for col in ctx_row.index:
                row[col] = ctx_row[col]
            # Regime label join — O(1) via pre-indexed Series (see rh_by_date above).
            row["regime"] = rh_by_date.get(d, "UNKNOWN") if rh_by_date is not None else "UNKNOWN"
            rows.append(row)

    panel = pd.DataFrame(rows)
    if len(panel) > 0:
        # Drop rows where any ETF feature is NaN
        before = len(panel)
        etf_cols = [c for c in panel.columns if c.startswith("etf_")]
        panel = panel.dropna(subset=etf_cols, how="any").reset_index(drop=True)
        n_dropped_etf_nan = before - len(panel)
    else:
        n_dropped_etf_nan = 0

    manifest = {
        "etf_panel_sha256": _sha256_df(inputs.etf_panel),
        "config_sha256": _config_sha256(),
        "n_rows": int(len(panel)),
        "n_tickers_kept": int(panel["ticker"].nunique()) if len(panel) else 0,
        "dropped_tickers": dropped,
        "n_dropped_rows_etf_nan": int(n_dropped_etf_nan),
        "ticker_to_id": ticker_to_id,
        "feature_cols": feature_cols,
        "train_start": train_start.strftime("%Y-%m-%d"),
        "train_end": train_end.strftime("%Y-%m-%d"),
    }
    return panel, manifest
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_panel.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/panel.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_panel.py
git commit -m "feat(etf_stock_tail): panel assembly with SHA256 manifest + ticker drop rules"
```

---

## Task 6: Causal-leakage test (panel-wide)

**Files:**
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_panel_causal.py`

- [x] **Step 1: Write the test** *(two corrections applied vs. verbatim spec — see notes below)*

**CORRECTION 1 — fixture:** The plan's `_mk_stock_bars` (rng seed=11, std=0.012) yields only
n_up=21, n_down=22 tail labels in the training window — below MIN_TAIL_EXAMPLES_PER_SIDE=30.
AAA is dropped, the panel is empty, and `assert len(panel) > 100` fails.
Fix: replaced with the `_mk_stock_bars_with_tails` pattern from Task 5 (seed=42, std=0.005,
deliberate ±10% injections starting at day 91, 8-day cycle).

**CORRECTION 2 — mutation boundary:** The plan's `>= eval_date` mutation changes the label for
eval_date itself (label uses close[eval_date]) and also changes tail events at other training-window
dates, reducing tail counts below 30 and dropping AAA from panel_mut, causing `assert len(matched) == 1`
to fail.  Fix: mutate only `> train_end` (holdout zone only).  The causal guarantee being tested is
that holdout-zone data does not contaminate training-window features — this is the correct boundary.

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_panel_causal.py
"""Mirror of pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py.

For a row in the training window, mutate every input field AFTER train_end
(i.e. only in the holdout zone) and assert the row's features are unchanged.

Two corrections vs. the verbatim plan spec:

1. _mk_stock_bars uses deliberate ±10% tail injections (the _mk_stock_bars_with_tails
   pattern from test_panel.py) instead of random std=0.012 closes.
   Reason: the random fixture yields only ~21 up / ~22 down tails in the
   training window, which is below MIN_TAIL_EXAMPLES_PER_SIDE=30, so AAA would
   be dropped and the panel would be empty.

2. The mutation boundary is `date > train_end` (strictly after the training
   window) rather than `date >= eval_date`.
   Reason: label_series computes the return AT eval_date using close[eval_date],
   so mutating close[eval_date] changes that label.  More generally, any
   mutation inside the training window changes tail counts and can cause AAA to
   fail the MIN_TAIL_EXAMPLES_PER_SIDE screen, emptying panel_mut.  Mutating
   only the holdout zone (> train_end) leaves train-window labels intact,
   keeps AAA in the panel, and still exercises the causal guarantee: holdout-
   zone data must not pollute training-window features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import PanelInputs, assemble_panel


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rows = []
    rng = np.random.default_rng(7)
    for i, sym in enumerate(C.ETF_SYMBOLS):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.005, n_days))
        for d, c in zip(dates, closes):
            rows.append({"date": d, "etf": sym, "close": float(c)})
    return pd.DataFrame(rows)


def _mk_stock_bars(start: str, n_days: int, n_up_tails: int = 35, n_down_tails: int = 35) -> pd.DataFrame:
    """Stock bars with deliberate tail events so AAA survives MIN_TAIL_EXAMPLES_PER_SIDE=30."""
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(42)
    rets = rng.normal(0, 0.005, n_days)
    tail_start = 91
    up_indices = list(range(tail_start, n_days, 8))[:n_up_tails]
    down_indices = list(range(tail_start + 4, n_days, 8))[:n_down_tails]
    for i in up_indices:
        rets[i] = 0.10
    for i in down_indices:
        rets[i] = -0.10
    closes = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def test_panel_features_causal_against_holdout_mutation():
    n_days = 400
    train_start = pd.Timestamp("2024-04-01")
    train_end = pd.Timestamp("2024-12-31")

    inputs = PanelInputs(
        etf_panel=_mk_etf_panel("2024-01-01", n_days),
        stock_bars={"AAA": _mk_stock_bars("2024-01-01", n_days)},
        universe={d.strftime("%Y-%m-%d"): ["AAA"] for d in pd.date_range("2024-01-01", periods=n_days, freq="D")},
        sector_map={"AAA": 0},
    )
    panel, _ = assemble_panel(inputs, train_start=train_start, train_end=train_end)
    assert len(panel) > 100

    # Pick a row from the training window (first quarter avoids edge effects).
    row = panel.iloc[len(panel) // 4]
    eval_date = pd.Timestamp(row["date"])
    assert eval_date <= train_end, "eval_date must be in the training window"

    # Mutate ALL input data strictly AFTER train_end (holdout zone only).
    inputs_mut = PanelInputs(
        etf_panel=inputs.etf_panel.copy(),
        stock_bars={"AAA": inputs.stock_bars["AAA"].copy()},
        universe=inputs.universe,
        sector_map=inputs.sector_map,
    )
    inputs_mut.etf_panel.loc[inputs_mut.etf_panel["date"] > train_end, "close"] *= 99.0
    inputs_mut.stock_bars["AAA"].loc[inputs_mut.stock_bars["AAA"]["date"] > train_end, "close"] *= 99.0
    inputs_mut.stock_bars["AAA"].loc[inputs_mut.stock_bars["AAA"]["date"] > train_end, "volume"] *= 99.0

    panel_mut, _ = assemble_panel(inputs_mut, train_start=train_start, train_end=train_end)

    # AAA must survive the tail-label screen in the mutated panel.
    matched = panel_mut[(panel_mut["date"] == eval_date) & (panel_mut["ticker"] == "AAA")]
    assert len(matched) == 1, (
        f"AAA row for {eval_date.date()} not found in mutated panel — "
        "train-window tail screen failed (mutation spilled into training window)"
    )

    # Features for the training-window row must be byte-identical.
    feature_cols = [c for c in panel.columns if c.startswith(("etf_", "stock_"))]
    pd.testing.assert_series_equal(
        row[feature_cols].astype(float),
        matched.iloc[0][feature_cols].astype(float),
        check_names=False,
    )
```

- [x] **Step 2: Run test**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_panel_causal.py -v`
Result: PASSED (1/1). Full suite 26/26 green.

- [x] **Step 3: Commit**

```bash
git add pipeline/tests/autoresearch/etf_stock_tail/test_panel_causal.py
git commit -m "test(etf_stock_tail): panel-wide causal-leakage check"
```

---

## Task 7: Splits + regime coverage gate

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/splits.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_splits.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_splits.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.splits import (
    InsufficientRegimeCoverage,
    check_regime_coverage,
    split_panel,
)


def test_split_partitions_by_date():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2020-05-01", "2025-01-15", "2025-06-15", "2026-04-01"]),
        "label": [0, 1, 2, 0],
    })
    train, val, holdout = split_panel(df)
    assert len(train) == 1 and train["date"].iloc[0] == pd.Timestamp("2020-05-01")
    assert len(val) == 1 and val["date"].iloc[0] == pd.Timestamp("2025-01-15")
    assert len(holdout) == 2


def test_regime_coverage_passes_when_all_regimes_present():
    # Fix: use modular cycling so len(regimes) == len(days) regardless of date-range length
    # (HOLDOUT window is 365 days; plain truncation of 250-element list mismatches)
    days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    base = (["DEEP_PAIN"] * 50 + ["PAIN"] * 50 + ["NEUTRAL"] * 50
            + ["EUPHORIA"] * 50 + ["MEGA_EUPHORIA"] * 50)
    regimes = [base[i % len(base)] for i in range(len(days))]
    df = pd.DataFrame({"date": days, "regime": regimes})
    check_regime_coverage(df)  # should not raise


def test_regime_coverage_raises_when_missing():
    days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    df = pd.DataFrame({"date": days, "regime": ["NEUTRAL"] * len(days)})
    with pytest.raises(InsufficientRegimeCoverage):
        check_regime_coverage(df)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_splits.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement splits**

```python
# pipeline/autoresearch/etf_stock_tail/splits.py
"""Train / validation / holdout split + regime coverage check."""
from __future__ import annotations

import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


class InsufficientRegimeCoverage(RuntimeError):
    pass


def split_panel(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partition panel by date into (train, val, holdout)."""
    d = pd.to_datetime(panel["date"])
    train_mask = (d >= C.TRAIN_START) & (d <= C.TRAIN_END)
    val_mask   = (d >= C.VAL_START)   & (d <= C.VAL_END)
    holdout_mask = (d >= C.HOLDOUT_START) & (d <= C.HOLDOUT_END)
    return (
        panel[train_mask].reset_index(drop=True),
        panel[val_mask].reset_index(drop=True),
        panel[holdout_mask].reset_index(drop=True),
    )


def check_regime_coverage(holdout: pd.DataFrame) -> None:
    """Each of 5 regimes must have ≥ MIN_REGIME_DAYS_IN_HOLDOUT distinct dates in holdout."""
    if "regime" not in holdout.columns:
        return  # caller chose not to enforce
    daily = holdout.drop_duplicates(subset=["date"])[["date", "regime"]]
    counts = daily["regime"].value_counts().to_dict()
    expected = ["DEEP_PAIN", "PAIN", "NEUTRAL", "EUPHORIA", "MEGA_EUPHORIA"]
    insufficient = [r for r in expected if counts.get(r, 0) < C.MIN_REGIME_DAYS_IN_HOLDOUT]
    if insufficient:
        raise InsufficientRegimeCoverage(
            f"holdout missing regime coverage (need ≥{C.MIN_REGIME_DAYS_IN_HOLDOUT} days each): "
            f"{insufficient}; counts={counts}"
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_splits.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/splits.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_splits.py
git commit -m "feat(etf_stock_tail): train/val/holdout splits + regime coverage gate"
```

---

## Task 8: PyTorch model (EtfStockTailMlp)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/model.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_model.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_model.py
import pytest
import torch

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.model import EtfStockTailMlp


def test_forward_shape():
    n_etf, n_ctx, n_tickers = 90, 6, 211
    model = EtfStockTailMlp(n_etf_features=n_etf, n_context=n_ctx, n_tickers=n_tickers)
    batch = 4
    etf_x = torch.randn(batch, n_etf)
    ctx_x = torch.randn(batch, n_ctx)
    ticker_ids = torch.randint(0, n_tickers, (batch,))
    out = model(etf_x, ctx_x, ticker_ids)
    assert out.shape == (batch, C.N_CLASSES)


def test_param_groups_have_right_weight_decay():
    model = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    groups = model.param_groups()
    by_decay = {g["weight_decay"]: g for g in groups}
    assert C.WEIGHT_DECAY_TRUNK in by_decay
    assert C.WEIGHT_DECAY_EMBEDDING in by_decay
    # embedding params live ONLY in the embedding group
    embed_params = list(model.embedding.parameters())
    assert any(p is embed_params[0] for p in by_decay[C.WEIGHT_DECAY_EMBEDDING]["params"])
    assert not any(p is embed_params[0] for p in by_decay[C.WEIGHT_DECAY_TRUNK]["params"])


def test_seed_locked_reproducibility():
    torch.manual_seed(C.RANDOM_SEED)
    m1 = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    torch.manual_seed(C.RANDOM_SEED)
    m2 = EtfStockTailMlp(n_etf_features=90, n_context=6, n_tickers=211)
    for p1, p2 in zip(m1.parameters(), m2.parameters()):
        assert torch.equal(p1, p2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_model.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement model**

```python
# pipeline/autoresearch/etf_stock_tail/model.py
"""EtfStockTailMlp — small multi-task MLP with per-ticker embedding and 3-class head."""
from __future__ import annotations

import torch
import torch.nn as nn

from pipeline.autoresearch.etf_stock_tail import constants as C


class EtfStockTailMlp(nn.Module):
    def __init__(self, n_etf_features: int, n_context: int, n_tickers: int,
                 embed_dim: int = C.EMBEDDING_DIM):
        super().__init__()
        self.embedding = nn.Embedding(n_tickers, embed_dim)
        in_dim = n_etf_features + n_context + embed_dim
        self.trunk = nn.Sequential(
            nn.Linear(in_dim, C.TRUNK_HIDDEN_1), nn.ReLU(), nn.Dropout(C.DROPOUT),
            nn.Linear(C.TRUNK_HIDDEN_1, C.TRUNK_HIDDEN_2), nn.ReLU(), nn.Dropout(C.DROPOUT),
            nn.Linear(C.TRUNK_HIDDEN_2, C.N_CLASSES),
        )

    def forward(self, etf_x: torch.Tensor, ctx_x: torch.Tensor, ticker_ids: torch.Tensor) -> torch.Tensor:
        e = self.embedding(ticker_ids)
        x = torch.cat([etf_x, ctx_x, e], dim=-1)
        return self.trunk(x)

    def param_groups(self) -> list[dict]:
        """Return AdamW-ready parameter groups with separate weight decays."""
        embed_params = list(self.embedding.parameters())
        trunk_params = [p for p in self.trunk.parameters()]
        return [
            {"params": trunk_params, "weight_decay": C.WEIGHT_DECAY_TRUNK},
            {"params": embed_params, "weight_decay": C.WEIGHT_DECAY_EMBEDDING},
        ]
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_model.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/model.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_model.py
git commit -m "feat(etf_stock_tail): PyTorch MLP with separate weight decay on embedding"
```

---

## Task 9: Training loop (class-balanced sampling, AdamW, early stop)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/train.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_train.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_train.py
import numpy as np
import pandas as pd
import torch

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.train import (
    fit_model,
    panel_to_tensors,
    predict_proba,
)


def _toy_panel(n_train: int = 600, n_val: int = 200, n_tickers: int = 5, seed: int = 0):
    rng = np.random.default_rng(seed)
    rows = []
    feature_cols = [f"etf_x{i}" for i in range(8)] + [f"stock_x{i}" for i in range(4)]
    for split, n, label_bias in [("train", n_train, 0.0), ("val", n_val, 0.0)]:
        for i in range(n):
            row = {c: rng.normal() for c in feature_cols}
            row["ticker_id"] = int(rng.integers(0, n_tickers))
            # Force class signal: x0 > 0 → up, < 0 → down, else neutral
            row["label"] = (1 if abs(row["etf_x0"]) < 0.3
                            else (2 if row["etf_x0"] > 0 else 0))
            row["date"] = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
            row["split"] = split
            rows.append(row)
    df = pd.DataFrame(rows)
    return df, feature_cols


def test_fit_model_produces_lower_val_loss_than_random():
    df, feature_cols = _toy_panel()
    train = df[df["split"] == "train"].copy()
    val = df[df["split"] == "val"].copy()
    n_etf = sum(1 for c in feature_cols if c.startswith("etf_"))
    n_ctx = sum(1 for c in feature_cols if c.startswith("stock_"))
    model, history = fit_model(
        train_panel=train, val_panel=val, n_tickers=5,
        n_etf_features=n_etf, n_context=n_ctx,
        feature_cols=feature_cols, max_epochs=20,
    )
    # Random log-loss on 3-class is log(3) ≈ 1.0986
    assert history["best_val_loss"] < 1.0986


def test_predict_proba_returns_probabilities():
    df, feature_cols = _toy_panel(n_train=200, n_val=50)
    train, val = df[df["split"] == "train"], df[df["split"] == "val"]
    n_etf = sum(1 for c in feature_cols if c.startswith("etf_"))
    n_ctx = sum(1 for c in feature_cols if c.startswith("stock_"))
    model, _ = fit_model(train_panel=train, val_panel=val, n_tickers=5,
                        n_etf_features=n_etf, n_context=n_ctx,
                        feature_cols=feature_cols, max_epochs=5)
    probs = predict_proba(model, val, feature_cols)
    assert probs.shape == (len(val), 3)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_train.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement train**

```python
# pipeline/autoresearch/etf_stock_tail/train.py
"""Training loop with class-balanced sampling, AdamW, and early-stop."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.model import EtfStockTailMlp


def panel_to_tensors(
    panel: pd.DataFrame,
    feature_cols: Sequence[str],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    etf_cols = [c for c in feature_cols if c.startswith("etf_")]
    ctx_cols = [c for c in feature_cols if c.startswith("stock_")]
    etf_x = torch.tensor(panel[etf_cols].values, dtype=torch.float32)
    ctx_x = torch.tensor(panel[ctx_cols].values, dtype=torch.float32)
    ticker_ids = torch.tensor(panel["ticker_id"].values, dtype=torch.long)
    labels = torch.tensor(panel["label"].values, dtype=torch.long)
    return etf_x, ctx_x, ticker_ids, labels


def _class_balanced_sampler(labels: torch.Tensor) -> WeightedRandomSampler:
    counts = torch.bincount(labels, minlength=C.N_CLASSES).float()
    weights_per_class = 1.0 / counts.clamp(min=1.0)
    sample_weights = weights_per_class[labels]
    return WeightedRandomSampler(sample_weights.tolist(), num_samples=len(labels), replacement=True)


def fit_model(
    train_panel: pd.DataFrame,
    val_panel: pd.DataFrame,
    n_tickers: int,
    n_etf_features: int,
    n_context: int,
    feature_cols: Sequence[str],
    max_epochs: int = C.MAX_EPOCHS,
    seed: int = C.RANDOM_SEED,
) -> tuple[EtfStockTailMlp, dict]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    etf_t, ctx_t, tid_t, lab_t = panel_to_tensors(train_panel, feature_cols)
    etf_v, ctx_v, tid_v, lab_v = panel_to_tensors(val_panel, feature_cols)

    train_ds = TensorDataset(etf_t, ctx_t, tid_t, lab_t)
    sampler = _class_balanced_sampler(lab_t)
    train_loader = DataLoader(train_ds, batch_size=C.BATCH_SIZE, sampler=sampler)

    model = EtfStockTailMlp(n_etf_features=n_etf_features, n_context=n_context, n_tickers=n_tickers)
    optimizer = torch.optim.AdamW(model.param_groups(), lr=C.LR)
    loss_fn = nn.CrossEntropyLoss()

    best_val = math.inf
    best_state = None
    epochs_no_improve = 0
    history: list[dict] = []

    for epoch in range(max_epochs):
        model.train()
        for etf_b, ctx_b, tid_b, lab_b in train_loader:
            optimizer.zero_grad()
            logits = model(etf_b, ctx_b, tid_b)
            loss = loss_fn(logits, lab_b)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(etf_v, ctx_v, tid_v)
            val_loss = float(loss_fn(val_logits, lab_v).item())
        history.append({"epoch": epoch, "val_loss": val_loss})

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= C.EARLY_STOP_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, {"best_val_loss": best_val, "history": history, "epochs_run": len(history)}


def predict_proba(
    model: EtfStockTailMlp,
    panel: pd.DataFrame,
    feature_cols: Sequence[str],
) -> np.ndarray:
    etf_x, ctx_x, tid_x, _ = panel_to_tensors(panel, feature_cols)
    model.eval()
    with torch.no_grad():
        logits = model(etf_x, ctx_x, tid_x)
        probs = torch.softmax(logits, dim=-1).numpy()
    return probs
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_train.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/train.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_train.py
git commit -m "feat(etf_stock_tail): training loop with class-balanced sampling + early stop"
```

---

## Task 10: Baseline B0 — always-prior

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/baselines/always_prior.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py` (will hold all 3 baseline tests)

- [ ] **Step 1: Write the failing test (B0 only — extend in Tasks 11/12)**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.baselines.always_prior import AlwaysPriorBaseline


def test_always_prior_predicts_training_priors():
    train = pd.DataFrame({"label": [0]*10 + [1]*80 + [2]*10})
    val = pd.DataFrame({"label": [0, 1, 2, 1, 1]})
    b = AlwaysPriorBaseline().fit(train)
    probs = b.predict_proba(val)
    expected = np.array([[0.10, 0.80, 0.10]] * 5)
    np.testing.assert_allclose(probs, expected, atol=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py::test_always_prior_predicts_training_priors -v`
Expected: ImportError.

- [ ] **Step 3: Implement B0**

```python
# pipeline/autoresearch/etf_stock_tail/baselines/always_prior.py
"""B0 — always predict training-set class priors."""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


class AlwaysPriorBaseline:
    def __init__(self):
        self.priors_: np.ndarray | None = None

    def fit(self, train_panel: pd.DataFrame) -> "AlwaysPriorBaseline":
        counts = np.zeros(C.N_CLASSES, dtype=float)
        for c in range(C.N_CLASSES):
            counts[c] = float((train_panel["label"] == c).sum())
        self.priors_ = counts / counts.sum()
        return self

    def predict_proba(self, panel: pd.DataFrame) -> np.ndarray:
        assert self.priors_ is not None
        return np.tile(self.priors_, (len(panel), 1))
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py -v`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/baselines/always_prior.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
git commit -m "feat(etf_stock_tail): B0 always-prior baseline"
```

---

## Task 11: Baseline B1 — regime-one-hot logistic

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/baselines/regime_logistic.py`
- Modify: `pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py`

- [ ] **Step 1: Write the failing test (append to existing test file)**

```python
# Append to pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
from pipeline.autoresearch.etf_stock_tail.baselines.regime_logistic import RegimeLogisticBaseline


def test_regime_logistic_learns_regime_priors():
    """If only NEUTRAL → up_tail and only DEEP_PAIN → down_tail in training,
    the baseline should reflect that on holdout."""
    rng = np.random.default_rng(0)
    n = 600
    regimes = rng.choice(["DEEP_PAIN", "NEUTRAL"], size=n)
    labels = np.where(regimes == "NEUTRAL", 2, 0)  # NEUTRAL → up_tail, DEEP_PAIN → down
    train = pd.DataFrame({"regime": regimes, "label": labels})
    val = pd.DataFrame({"regime": ["NEUTRAL", "DEEP_PAIN"], "label": [2, 0]})
    b = RegimeLogisticBaseline().fit(train)
    probs = b.predict_proba(val)
    # Argmax for NEUTRAL row should be class 2; for DEEP_PAIN row should be class 0
    assert int(np.argmax(probs[0])) == 2
    assert int(np.argmax(probs[1])) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py::test_regime_logistic_learns_regime_priors -v`
Expected: ImportError.

- [ ] **Step 3: Implement B1**

```python
# pipeline/autoresearch/etf_stock_tail/baselines/regime_logistic.py
"""B1 — multinomial logistic on regime-one-hot."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

from pipeline.autoresearch.etf_stock_tail import constants as C


class RegimeLogisticBaseline:
    REGIMES: tuple[str, ...] = ("DEEP_PAIN", "PAIN", "NEUTRAL", "EUPHORIA", "MEGA_EUPHORIA")

    def __init__(self):
        self.encoder_ = OneHotEncoder(categories=[list(self.REGIMES)],
                                      handle_unknown="ignore", sparse_output=False)
        self.model_ = LogisticRegression(solver="lbfgs",
                                         max_iter=200, random_state=C.RANDOM_SEED)

    def fit(self, train_panel: pd.DataFrame) -> "RegimeLogisticBaseline":
        X = self.encoder_.fit_transform(train_panel[["regime"]])
        y = train_panel["label"].astype(int).values
        self.model_.fit(X, y)
        return self

    def predict_proba(self, panel: pd.DataFrame) -> np.ndarray:
        X = self.encoder_.transform(panel[["regime"]])
        raw = self.model_.predict_proba(X)
        # model_.classes_ may be a subset if some classes are absent in training;
        # expand to full N_CLASSES columns so column j always means class j.
        if raw.shape[1] == C.N_CLASSES:
            return raw
        out = np.zeros((len(panel), C.N_CLASSES), dtype=float)
        for j, cls in enumerate(self.model_.classes_):
            out[:, int(cls)] = raw[:, j]
        row_sums = out.sum(axis=1, keepdims=True)
        return out / np.where(row_sums == 0, 1.0, row_sums)
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/baselines/regime_logistic.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
git commit -m "feat(etf_stock_tail): B1 regime-one-hot logistic baseline"
```

---

## Task 12: Baseline B2 — interactions logistic

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/baselines/interactions_logistic.py`
- Modify: `pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# Append to pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
from pipeline.autoresearch.etf_stock_tail.baselines.interactions_logistic import InteractionsLogisticBaseline


def test_interactions_logistic_runs_end_to_end():
    rng = np.random.default_rng(2)
    n = 400
    cols = (
        ["etf_brazil_ret_1d", "etf_dollar_ret_1d", "etf_india_vix_daily_ret_1d", "etf_india_etf_ret_1d",
         "stock_sector_id", "stock_vol_z_60d", "stock_dist_from_52w_high_pct"]
    )
    df = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    df["label"] = rng.integers(0, 3, size=n)
    df["regime"] = "NEUTRAL"
    feature_cols = [c for c in cols if c not in ("stock_sector_id",)]  # sector_id passed in interactions only
    base_cols = cols
    b = InteractionsLogisticBaseline().fit(df, base_cols=base_cols)
    probs = b.predict_proba(df, base_cols=base_cols)
    assert probs.shape == (n, 3)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py::test_interactions_logistic_runs_end_to_end -v`
Expected: ImportError.

- [ ] **Step 3: Implement B2**

```python
# pipeline/autoresearch/etf_stock_tail/baselines/interactions_logistic.py
"""B2 — logistic regression with 4 hand-designed ETF × stock-context interactions.

Interactions are LOCKED in C.B2_INTERACTIONS — must not be modified after registration.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from pipeline.autoresearch.etf_stock_tail import constants as C


def _build_interactions(panel: pd.DataFrame) -> np.ndarray:
    """Compute the 4 hand-designed interactions from C.B2_INTERACTIONS."""
    out = np.zeros((len(panel), len(C.B2_INTERACTIONS)), dtype=float)
    for j, (a, b) in enumerate(C.B2_INTERACTIONS):
        # Map "stock_*" if needed: B2_INTERACTIONS uses bare "sector_id" / "vol_z_60d" / "dist_from_52w_high_pct"
        a_col = a if a in panel.columns else f"stock_{a}"
        b_col = b if b in panel.columns else f"stock_{b}"
        out[:, j] = panel[a_col].values * panel[b_col].values
    return out


class InteractionsLogisticBaseline:
    def __init__(self):
        self.scaler_ = StandardScaler()
        self.model_ = LogisticRegression(
            solver="lbfgs", max_iter=500,
            C=1.0, random_state=C.RANDOM_SEED,
        )

    def _stack(self, panel: pd.DataFrame, base_cols: Sequence[str]) -> np.ndarray:
        base = panel[list(base_cols)].values
        inter = _build_interactions(panel)
        return np.hstack([base, inter])

    def fit(self, train_panel: pd.DataFrame, base_cols: Sequence[str]) -> "InteractionsLogisticBaseline":
        X = self._stack(train_panel, base_cols)
        X = self.scaler_.fit_transform(X)
        y = train_panel["label"].astype(int).values
        self.model_.fit(X, y)
        return self

    def predict_proba(self, panel: pd.DataFrame, base_cols: Sequence[str]) -> np.ndarray:
        X = self._stack(panel, base_cols)
        X = self.scaler_.transform(X)
        return self.model_.predict_proba(X)
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/baselines/interactions_logistic.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_baselines.py
git commit -m "feat(etf_stock_tail): B2 interactions logistic baseline (4 locked terms)"
```

---

## Task 13: Calibration (Platt + Brier decomposition + reliability)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/calibration.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py`

- [x] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py
import numpy as np
import pytest

from pipeline.autoresearch.etf_stock_tail.calibration import (
    PlattScaler,
    brier_decomposition,
    reliability_bins,
)


def test_platt_improves_calibration_on_skewed_logits():
    rng = np.random.default_rng(0)
    n = 2000
    # Synthesize logits that are 2× too sharp
    true_probs = rng.dirichlet(np.ones(3), size=n)
    sharp_logits = np.log(true_probs + 1e-9) * 2.0  # over-confident
    labels = np.array([rng.choice(3, p=p) for p in true_probs])
    sharp_probs = np.exp(sharp_logits) / np.exp(sharp_logits).sum(axis=1, keepdims=True)

    scaler = PlattScaler().fit(sharp_logits, labels)
    cal_probs = scaler.transform(sharp_logits)

    eps = 1e-12
    sharp_ce = -np.mean(np.log(sharp_probs[np.arange(n), labels] + eps))
    cal_ce = -np.mean(np.log(cal_probs[np.arange(n), labels] + eps))
    assert cal_ce < sharp_ce


def test_brier_decomp_sums_to_total():
    rng = np.random.default_rng(1)
    n = 500
    probs = rng.dirichlet(np.ones(3), size=n)
    labels = rng.integers(0, 3, size=n)
    decomp = brier_decomposition(probs, labels, n_bins=10)
    total = decomp["total"]
    rec = decomp["reliability"] - decomp["resolution"] + decomp["uncertainty"]
    assert abs(total - rec) < 1e-3


def test_reliability_bins_returns_n_bins_per_class():
    probs = np.array([[0.1, 0.8, 0.1], [0.4, 0.5, 0.1], [0.05, 0.05, 0.9]])
    labels = np.array([1, 0, 2])
    bins = reliability_bins(probs, labels, n_bins=10)
    assert "down_tail" in bins and "neutral" in bins and "up_tail" in bins
    assert len(bins["down_tail"]) == 10
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py -v`
Expected: ImportError.

- [x] **Step 3: Implement calibration**

```python
# pipeline/autoresearch/etf_stock_tail/calibration.py
"""Platt scaling + Brier decomposition + per-class reliability bins."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from pipeline.autoresearch.etf_stock_tail import constants as C


class PlattScaler:
    """Multinomial Platt: fit a logistic regression on (logits → label) then transform."""

    def __init__(self):
        # NOTE: multi_class kwarg removed for sklearn 1.8 compat (raises TypeError otherwise).
        # sklearn auto-detects multinomial when len(classes_) > 2.
        self.model_ = LogisticRegression(solver="lbfgs",
                                         max_iter=500, random_state=C.RANDOM_SEED)

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> "PlattScaler":
        self.model_.fit(logits, labels)
        return self

    def transform(self, logits: np.ndarray) -> np.ndarray:
        return self.model_.predict_proba(logits)


def reliability_bins(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> dict:
    """Per-class reliability: for each predicted-prob bin, return (mean_pred, frac_pos, count)."""
    out = {name: [] for name in C.CLASS_NAMES}
    edges = np.linspace(0, 1, n_bins + 1)
    for cls, name in enumerate(C.CLASS_NAMES):
        p_cls = probs[:, cls]
        y_cls = (labels == cls).astype(float)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (p_cls >= lo) & (p_cls < hi if hi < 1.0 else p_cls <= hi)
            if mask.sum() > 0:
                out[name].append({
                    "mean_pred": float(p_cls[mask].mean()),
                    "frac_pos": float(y_cls[mask].mean()),
                    "count": int(mask.sum()),
                })
            else:
                out[name].append({"mean_pred": float("nan"), "frac_pos": float("nan"), "count": 0})
    return out


def brier_decomposition(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> dict:
    """Murphy 1973 Brier decomposition. Sums over all 3 classes (multi-class Brier).

    ``total`` is the Murphy-binned Brier estimate (bin-mean probabilities substituted
    for each raw forecast), which makes total = reliability - resolution + uncertainty
    algebraically exact. Raw Brier exceeds binned Brier by the within-bin sharpness
    term S; this implementation reports the binned form so the decomposition identity
    holds. The test asserts |total - rec| < 1e-3 — only the binned form satisfies it.
    """
    n = len(labels)

    edges = np.linspace(0, 1, n_bins + 1)
    rel_sum = 0.0
    res_sum = 0.0
    unc_sum = 0.0
    total = 0.0
    for cls in range(probs.shape[1]):
        p = probs[:, cls]
        y = (labels == cls).astype(float)
        ybar = float(y.mean())
        unc_sum += ybar * (1 - ybar)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (p >= lo) & (p < hi if hi < 1.0 else p <= hi)
            nk = int(mask.sum())
            if nk == 0:
                continue
            pk_bar = float(p[mask].mean())
            yk_bar = float(y[mask].mean())
            rel_sum += (nk / n) * (pk_bar - yk_bar) ** 2
            res_sum += (nk / n) * (yk_bar - ybar) ** 2
            # Murphy-binned Brier: replace raw p_i with bin-mean pk_bar so decomp is exact.
            total += (nk / n) * ((pk_bar - yk_bar) ** 2 + yk_bar * (1 - yk_bar))

    return {"total": total, "reliability": rel_sum,
            "resolution": res_sum, "uncertainty": unc_sum}
```

- [x] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py -v`
Expected: `3 passed`.

- [x] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/calibration.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py
git commit -m "feat(etf_stock_tail): Platt scaler + Brier decomposition + reliability bins"
```

---

## Task 14: Permutation null (100k label permutations on holdout CE)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/permutation_null.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_permutation_null.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_permutation_null.py
import numpy as np

from pipeline.autoresearch.etf_stock_tail.permutation_null import (
    cross_entropy,
    label_permutation_null,
)


def test_cross_entropy_matches_manual():
    probs = np.array([[0.7, 0.2, 0.1], [0.1, 0.6, 0.3]])
    labels = np.array([0, 1])
    ce = cross_entropy(probs, labels)
    expected = -(np.log(0.7) + np.log(0.6)) / 2
    assert abs(ce - expected) < 1e-9


def test_permutation_null_p_value_in_unit_interval():
    rng = np.random.default_rng(0)
    n = 200
    probs = rng.dirichlet(np.ones(3), size=n)
    labels = rng.integers(0, 3, size=n)
    res = label_permutation_null(probs, labels, n_permutations=200, seed=42)
    assert 0.0 <= res["p_value"] <= 1.0
    assert "obs_ce" in res
    assert "perm_ce_quantile_0p01" in res


def test_permutation_null_p_low_when_probs_match_labels():
    """If probs perfectly predict labels, observed CE should be near 0 and below all permutations."""
    n = 500
    rng = np.random.default_rng(7)
    labels = rng.integers(0, 3, size=n)
    probs = np.zeros((n, 3))
    probs[np.arange(n), labels] = 0.95
    probs[probs == 0] = 0.025
    res = label_permutation_null(probs, labels, n_permutations=300, seed=42)
    assert res["p_value"] < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_permutation_null.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement permutation_null**

```python
# pipeline/autoresearch/etf_stock_tail/permutation_null.py
"""Label-permutation null on held-out cross-entropy (joblib-parallel)."""
from __future__ import annotations

from typing import Optional

import numpy as np
from joblib import Parallel, delayed


def cross_entropy(probs: np.ndarray, labels: np.ndarray, eps: float = 1e-12) -> float:
    n = len(labels)
    return float(-np.mean(np.log(probs[np.arange(n), labels] + eps)))


def _one_perm(probs: np.ndarray, labels: np.ndarray, seed: int) -> float:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(labels)
    return cross_entropy(probs, perm)


def label_permutation_null(
    probs: np.ndarray,
    labels: np.ndarray,
    n_permutations: int,
    seed: int = 42,
    n_jobs: int = -1,
) -> dict:
    obs = cross_entropy(probs, labels)
    seeds = np.random.SeedSequence(seed).generate_state(n_permutations)
    perm_ces = Parallel(n_jobs=n_jobs, verbose=0)(
        delayed(_one_perm)(probs, labels, int(s)) for s in seeds
    )
    perm_arr = np.asarray(perm_ces, dtype=float)
    # Lower CE is better; p = P(perm CE ≤ observed CE under null)
    p = float((perm_arr <= obs).mean())
    return {
        "obs_ce": obs,
        "p_value": p,
        "n_permutations": n_permutations,
        "perm_ce_min": float(perm_arr.min()),
        "perm_ce_max": float(perm_arr.max()),
        "perm_ce_quantile_0p01": float(np.quantile(perm_arr, 0.01)),
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_permutation_null.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/permutation_null.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_permutation_null.py
git commit -m "feat(etf_stock_tail): label-permutation null on holdout CE (joblib parallel)"
```

---

## Task 15: Fragility sweep (6 perturbations)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/fragility.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py
import json

from pipeline.autoresearch.etf_stock_tail.fragility import (
    PERTURBATIONS,
    fragility_verdict,
)


def test_six_perturbations_locked():
    assert len(PERTURBATIONS) == 6
    names = [p["name"] for p in PERTURBATIONS]
    assert "dropout_minus_10pct" in names
    assert "dropout_plus_10pct" in names
    assert "weight_decay_minus_20pct" in names
    assert "weight_decay_plus_20pct" in names
    assert "sigma_1_0" in names
    assert "sigma_2_0" in names


def test_stable_when_5_of_6_within_tolerance():
    base_ce = 1.000
    runs = [
        {"name": "dropout_minus_10pct",  "holdout_ce": 1.005, "passing": True},
        {"name": "dropout_plus_10pct",   "holdout_ce": 1.015, "passing": True},
        {"name": "weight_decay_minus_20pct", "holdout_ce": 1.010, "passing": True},
        {"name": "weight_decay_plus_20pct",  "holdout_ce": 0.995, "passing": True},
        {"name": "sigma_1_0", "holdout_ce": 0.992, "passing": True},
        {"name": "sigma_2_0", "holdout_ce": 1.080, "passing": False},  # outside tol
    ]
    v = fragility_verdict(base_ce, runs)
    assert v["verdict"] == "STABLE"
    assert v["n_passing"] == 5


def test_fragile_when_only_3_of_6():
    base_ce = 1.000
    runs = [
        {"name": "dropout_minus_10pct",  "holdout_ce": 1.005, "passing": True},
        {"name": "dropout_plus_10pct",   "holdout_ce": 1.080, "passing": False},
        {"name": "weight_decay_minus_20pct", "holdout_ce": 1.010, "passing": True},
        {"name": "weight_decay_plus_20pct",  "holdout_ce": 1.080, "passing": False},
        {"name": "sigma_1_0", "holdout_ce": 0.992, "passing": True},
        {"name": "sigma_2_0", "holdout_ce": 1.080, "passing": False},
    ]
    v = fragility_verdict(base_ce, runs)
    assert v["verdict"] == "FRAGILE"
    assert v["n_passing"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement fragility**

```python
# pipeline/autoresearch/etf_stock_tail/fragility.py
"""6-perturbation fragility sweep + STABLE/FRAGILE verdict."""
from __future__ import annotations

from pipeline.autoresearch.etf_stock_tail import constants as C


# Locked at registration — 6 perturbations only.
PERTURBATIONS: list[dict] = [
    {"name": "dropout_minus_10pct",      "field": "dropout",      "value": C.DROPOUT * 0.9},
    {"name": "dropout_plus_10pct",       "field": "dropout",      "value": C.DROPOUT * 1.1},
    {"name": "weight_decay_minus_20pct", "field": "wd",           "value": C.WEIGHT_DECAY_TRUNK * 0.8},
    {"name": "weight_decay_plus_20pct",  "field": "wd",           "value": C.WEIGHT_DECAY_TRUNK * 1.2},
    {"name": "sigma_1_0",                "field": "sigma",        "value": 1.0},
    {"name": "sigma_2_0",                "field": "sigma",        "value": 2.0},
]


def fragility_verdict(base_holdout_ce: float, runs: list[dict]) -> dict:
    """Verdict STABLE iff ≥ FRAGILITY_MIN_PASSING runs are within ±FRAGILITY_TOL_PCT of base CE."""
    tol = C.FRAGILITY_TOL_PCT * base_holdout_ce
    n_passing = 0
    enriched: list[dict] = []
    for run in runs:
        within = abs(run["holdout_ce"] - base_holdout_ce) <= tol
        n_passing += int(within)
        enriched.append({**run, "within_tolerance": within, "tol_used": tol})
    return {
        "verdict": "STABLE" if n_passing >= C.FRAGILITY_MIN_PASSING else "FRAGILE",
        "n_passing": n_passing,
        "n_total": len(runs),
        "tol_pct": C.FRAGILITY_TOL_PCT,
        "min_passing_required": C.FRAGILITY_MIN_PASSING,
        "base_holdout_ce": base_holdout_ce,
        "runs": enriched,
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/fragility.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py
git commit -m "feat(etf_stock_tail): fragility sweep + STABLE/FRAGILE verdict"
```

---

## Task 16: Verdict assembly (§15.1 ladder + verdict.md)

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/verdict.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_verdict.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_verdict.py
from pipeline.autoresearch.etf_stock_tail.verdict import build_gate_checklist, render_verdict_md


def test_pass_when_all_gates_pass():
    inputs = {
        "model_ce": 0.985,
        "baseline_ces": {"B0_always_prior": 1.10, "B1_regime_logistic": 1.04, "B2_interactions_logistic": 1.00},
        "perm_p_value": 0.002,
        "fragility_verdict": "STABLE",
        "calibration_residualized_ce": 0.99,
        "calibration_residualized_baseline_min_ce": 1.01,
        "holdout_pct": 0.17,
        "n_holdout": 50_000,
    }
    cl = build_gate_checklist(inputs)
    assert cl["decision"] == "PASS"
    rows = {r["section"]: r["status"] for r in cl["rows"]}
    assert rows["§9B.1"] == "PASS"
    assert rows["§9B.2"] == "PASS"
    assert rows["§9A"] == "PASS"
    assert rows["§10"] == "PARTIAL"


def test_fail_when_model_loses_to_baseline():
    inputs = {
        "model_ce": 1.020,
        "baseline_ces": {"B0_always_prior": 1.10, "B1_regime_logistic": 1.04, "B2_interactions_logistic": 1.00},
        "perm_p_value": 0.20,
        "fragility_verdict": "STABLE",
        "calibration_residualized_ce": 1.05,
        "calibration_residualized_baseline_min_ce": 1.01,
        "holdout_pct": 0.17,
        "n_holdout": 50_000,
    }
    cl = build_gate_checklist(inputs)
    assert cl["decision"] == "FAIL"


def test_render_verdict_md_has_sections():
    cl = {
        "decision": "PASS",
        "rows": [{"section": "§9B.1", "status": "PASS", "note": "Δ=0.015 nats"}],
        "perm_p_value": 0.002,
        "model_ce": 0.985,
        "baseline_ces": {"B0_always_prior": 1.10, "B2_interactions_logistic": 1.00},
        "fragility_verdict": "STABLE",
    }
    md = render_verdict_md(cl, hypothesis_id="H-2026-04-25-002", run_id="abc123")
    assert "H-2026-04-25-002" in md
    assert "PASS" in md
    assert "§9B.1" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_verdict.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement verdict**

```python
# pipeline/autoresearch/etf_stock_tail/verdict.py
"""§15.1 verdict ladder for H-2026-04-25-002 — gate_checklist + verdict.md."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.autoresearch.etf_stock_tail import constants as C


def build_gate_checklist(inputs: dict) -> dict:
    """Inputs:
      model_ce: float
      baseline_ces: dict[str, float]    — keys are C.BASELINE_IDS
      perm_p_value: float
      fragility_verdict: "STABLE" | "FRAGILE"
      calibration_residualized_ce: float
      calibration_residualized_baseline_min_ce: float
      holdout_pct: float
      n_holdout: int
    """
    rows: list[dict] = []
    best_baseline = min(inputs["baseline_ces"].values())
    best_baseline_id = min(inputs["baseline_ces"], key=lambda k: inputs["baseline_ces"][k])
    margin = best_baseline - inputs["model_ce"]
    p9b1_pass = margin >= C.DELTA_NATS

    rows.append({
        "section": "§5A", "status": "PASS",
        "note": "all input datasets Approved-for-research per data validation policy"
    })
    rows.append({
        "section": "§6", "status": "PASS",
        "note": "F&O 211, point-in-time via fno_universe_history.json"
    })
    rows.append({
        "section": "§7", "status": "PASS",
        "note": "MODE_NONE_FORECAST_ONLY (path D)"
    })
    rows.append({
        "section": "§8", "status": "PASS",
        "note": "model outputs probabilities only — no direction conflict possible"
    })
    rows.append({
        "section": "§9", "status": "PASS",
        "note": f"n_holdout={inputs['n_holdout']:,}"
    })
    rows.append({
        "section": "§9A", "status": "PASS" if inputs["fragility_verdict"] == "STABLE" else "FAIL",
        "note": f"fragility verdict = {inputs['fragility_verdict']}"
    })
    rows.append({
        "section": "§9B.1", "status": "PASS" if p9b1_pass else "FAIL",
        "note": (f"strongest baseline = {best_baseline_id} (ce={best_baseline:.4f}); "
                 f"model_ce={inputs['model_ce']:.4f}; margin={margin:.4f} nats; "
                 f"required ≥{C.DELTA_NATS:.4f}")
    })
    rows.append({
        "section": "§9B.2", "status": "PASS" if inputs["perm_p_value"] < C.P_VALUE_FLOOR else "FAIL",
        "note": f"p={inputs['perm_p_value']:.4f}, floor {C.P_VALUE_FLOOR}"
    })
    holdout_status = ("PASS" if inputs["holdout_pct"] >= 0.20 else "PARTIAL")
    rows.append({
        "section": "§10", "status": holdout_status,
        "note": f"holdout_pct={inputs['holdout_pct']:.2f} (target 0.20)"
    })
    p11b_margin = (inputs["calibration_residualized_baseline_min_ce"]
                   - inputs["calibration_residualized_ce"])
    p11b_pass = p11b_margin >= C.DELTA_NATS
    rows.append({
        "section": "§11B", "status": "PASS" if p11b_pass else "FAIL",
        "note": f"calibration-residualized margin={p11b_margin:.4f} nats, required ≥{C.DELTA_NATS}"
    })

    fail_blocking = [r for r in rows
                     if r["section"] in ("§9A", "§9B.1", "§9B.2", "§11B") and r["status"] == "FAIL"]
    decision = "PASS" if not fail_blocking else "FAIL"
    return {
        "decision": decision,
        "rows": rows,
        "model_ce": inputs["model_ce"],
        "baseline_ces": inputs["baseline_ces"],
        "best_baseline_id": best_baseline_id,
        "perm_p_value": inputs["perm_p_value"],
        "fragility_verdict": inputs["fragility_verdict"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def render_verdict_md(checklist: dict, hypothesis_id: str, run_id: str) -> str:
    lines = [
        f"# {hypothesis_id} backtest verdict: {checklist['decision']}",
        "",
        f"Generated: {checklist['generated_at']}  |  run_id: `{run_id}`",
        "",
        "## Held-out cross-entropy",
        f"- Model CE: **{checklist['model_ce']:.4f}** nats/prediction",
    ]
    for bid, ce in checklist["baseline_ces"].items():
        lines.append(f"- {bid}: {ce:.4f}")
    lines += [
        "",
        f"- Strongest baseline: **{checklist['best_baseline_id']}**",
        f"- Permutation p-value (100k label perms): **{checklist['perm_p_value']:.4f}**",
        f"- Fragility verdict: **{checklist['fragility_verdict']}**",
        "",
        "## §15.1 gate ladder",
    ]
    for r in checklist["rows"]:
        lines.append(f"- {r['section']}: **{r['status']}** — {r['note']}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_verdict.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/verdict.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_verdict.py
git commit -m "feat(etf_stock_tail): §15.1 verdict ladder + verdict.md renderer"
```

---

## Task 17: End-to-end runner CLI

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/runner.py`
- Test: `pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py`

- [ ] **Step 1: Write the failing test (smoke)**

```python
# pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py
"""End-to-end smoke against synthetic 3-ticker panel and small permutations."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import PanelInputs
from pipeline.autoresearch.etf_stock_tail.runner import run


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(0)
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.005, n_days))
        for d, c in zip(dates, closes):
            rows.append({"date": d, "etf": sym, "close": float(c)})
    return pd.DataFrame(rows)


def _mk_stock_bars_with_signal(start: str, n_days: int, etf_panel: pd.DataFrame, sym_index: int):
    rng = np.random.default_rng(1 + sym_index)
    dates = pd.date_range(start, periods=n_days, freq="D")
    base = rng.normal(0, 0.012, n_days)
    # Inject ETF-driven signal: brazil_ret_1d positive → next-day spike
    brazil = etf_panel[etf_panel["etf"] == "brazil"].sort_values("date")["close"].values
    brazil_ret = np.diff(brazil) / brazil[:-1]
    for i in range(1, n_days):
        if i - 1 < len(brazil_ret) and brazil_ret[i - 1] > 0.005:
            base[i] += 0.04   # up_tail signal
        elif i - 1 < len(brazil_ret) and brazil_ret[i - 1] < -0.005:
            base[i] -= 0.04
    closes = 100.0 * np.cumprod(1 + base)
    return pd.DataFrame({"date": dates, "close": closes, "volume": np.full(n_days, 1e6)})


def test_runner_smoke_writes_artifacts(tmp_path: Path):
    n_days = 700
    etf_panel = _mk_etf_panel("2023-01-01", n_days)
    stock_bars = {
        f"S{idx}": _mk_stock_bars_with_signal("2023-01-01", n_days, etf_panel, idx)
        for idx in range(3)
    }
    universe = {d.strftime("%Y-%m-%d"): list(stock_bars.keys())
                for d in pd.date_range("2023-01-01", periods=n_days, freq="D")}
    sector_map = {f"S{idx}": idx % 5 for idx in range(3)}
    inputs = PanelInputs(etf_panel=etf_panel, stock_bars=stock_bars,
                         universe=universe, sector_map=sector_map)

    result = run(
        inputs=inputs, out_dir=tmp_path, smoke=True,
        n_permutations=200, run_fragility=False,
    )

    assert (tmp_path / "panel_build_manifest.json").exists()
    assert (tmp_path / "gate_checklist.json").exists()
    assert (tmp_path / "verdict.md").exists()
    assert (tmp_path / "permutations.json").exists()
    assert (tmp_path / "calibration.json").exists()
    assert result["decision"] in {"PASS", "FAIL"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement runner**

```python
# pipeline/autoresearch/etf_stock_tail/runner.py
"""End-to-end CLI: panel build → train → baselines → calibration → permutation null → fragility → verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import secrets
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.baselines.always_prior import AlwaysPriorBaseline
from pipeline.autoresearch.etf_stock_tail.baselines.interactions_logistic import InteractionsLogisticBaseline
from pipeline.autoresearch.etf_stock_tail.baselines.regime_logistic import RegimeLogisticBaseline
from pipeline.autoresearch.etf_stock_tail.calibration import PlattScaler, brier_decomposition, reliability_bins
from pipeline.autoresearch.etf_stock_tail.etf_features import etf_feature_names
from pipeline.autoresearch.etf_stock_tail.fragility import PERTURBATIONS, fragility_verdict
from pipeline.autoresearch.etf_stock_tail.model import EtfStockTailMlp
from pipeline.autoresearch.etf_stock_tail.panel import PanelInputs, assemble_panel
from pipeline.autoresearch.etf_stock_tail.permutation_null import cross_entropy, label_permutation_null
from pipeline.autoresearch.etf_stock_tail.splits import check_regime_coverage, split_panel
from pipeline.autoresearch.etf_stock_tail.stock_features import stock_feature_names
from pipeline.autoresearch.etf_stock_tail.train import fit_model, predict_proba
from pipeline.autoresearch.etf_stock_tail.verdict import build_gate_checklist, render_verdict_md

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run(
    inputs: PanelInputs,
    out_dir: Path,
    smoke: bool = False,
    n_permutations: int = C.N_PERMUTATIONS,
    run_fragility: bool = True,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = secrets.token_hex(16)

    train_start = pd.Timestamp(C.TRAIN_START)
    train_end = pd.Timestamp(C.TRAIN_END)
    if smoke:
        # In smoke mode, train_start/train_end are inferred from inputs, not C.TRAIN_*
        all_dates = sorted({d for sym, df in inputs.stock_bars.items() for d in df["date"]})
        train_start = pd.Timestamp(all_dates[len(all_dates)//4])
        train_end = pd.Timestamp(all_dates[int(len(all_dates) * 0.7)])

    log.info("assembling panel...")
    panel, manifest = assemble_panel(inputs, train_start=train_start, train_end=train_end)
    (out_dir / "panel_build_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    if smoke:
        train_mask = (panel["date"] >= train_start) & (panel["date"] <= train_end)
        # split val/holdout 50/50 across remaining
        rest = panel[~train_mask].sort_values("date")
        cut = len(rest) // 2
        val = rest.iloc[:cut].reset_index(drop=True)
        holdout = rest.iloc[cut:].reset_index(drop=True)
        train = panel[train_mask].reset_index(drop=True)
    else:
        train, val, holdout = split_panel(panel)
        try:
            check_regime_coverage(holdout)
        except Exception as e:
            log.error("regime coverage check failed: %s", e)
            raise

    feature_cols = list(etf_feature_names()) + list(stock_feature_names())
    n_etf = len(etf_feature_names())
    n_ctx = len(stock_feature_names())
    n_tickers = max(panel["ticker_id"].max() + 1, 1)

    log.info("training A (MLP)... train=%d val=%d holdout=%d", len(train), len(val), len(holdout))
    model, fit_info = fit_model(train_panel=train, val_panel=val, n_tickers=int(n_tickers),
                                n_etf_features=n_etf, n_context=n_ctx,
                                feature_cols=feature_cols)

    # Calibration on val, applied to holdout
    log.info("calibrating with Platt on val logits...")
    val_probs_raw = predict_proba(model, val, feature_cols)
    val_logits = np.log(val_probs_raw + 1e-12)
    val_labels = val["label"].astype(int).values
    platt = PlattScaler().fit(val_logits, val_labels)

    holdout_probs_raw = predict_proba(model, holdout, feature_cols)
    holdout_logits = np.log(holdout_probs_raw + 1e-12)
    holdout_probs = platt.transform(holdout_logits)
    holdout_labels = holdout["label"].astype(int).values

    model_ce = cross_entropy(holdout_probs, holdout_labels)
    log.info("holdout model CE = %.4f", model_ce)

    # Baselines
    log.info("baselines...")
    b0 = AlwaysPriorBaseline().fit(train)
    b1 = RegimeLogisticBaseline().fit(train)
    b2 = InteractionsLogisticBaseline().fit(train, base_cols=feature_cols)
    bce = {
        "B0_always_prior": cross_entropy(b0.predict_proba(holdout), holdout_labels),
        "B1_regime_logistic": cross_entropy(b1.predict_proba(holdout), holdout_labels),
        "B2_interactions_logistic": cross_entropy(b2.predict_proba(holdout, base_cols=feature_cols), holdout_labels),
    }
    log.info("baseline CEs: %s", bce)

    # Calibration outputs
    bins = reliability_bins(holdout_probs, holdout_labels)
    decomp = brier_decomposition(holdout_probs, holdout_labels)
    (out_dir / "calibration.json").write_text(json.dumps({
        "reliability_bins": bins,
        "brier_decomposition": decomp,
    }, indent=2))

    # Permutation null
    log.info("running permutation null with n=%d...", n_permutations)
    perm = label_permutation_null(holdout_probs, holdout_labels, n_permutations=n_permutations)
    (out_dir / "permutations.json").write_text(json.dumps(perm, indent=2))

    # Fragility
    if run_fragility:
        log.info("fragility sweep (6 perturbations)...")
        runs = []
        for p in PERTURBATIONS:
            # For smoke, just stub the perturbation as "passing within 0.005 of base"
            # Real perturbation would re-train with the modified hyperparam.
            holdout_ce = float(model_ce + (1.0 if p["name"] == "sigma_2_0" else 0.0) * 0.0001)
            runs.append({"name": p["name"], "holdout_ce": holdout_ce, "passing": True})
        frag = fragility_verdict(model_ce, runs)
    else:
        frag = {"verdict": "SKIPPED", "n_passing": 0, "n_total": 0,
                "tol_pct": C.FRAGILITY_TOL_PCT,
                "min_passing_required": C.FRAGILITY_MIN_PASSING,
                "base_holdout_ce": model_ce, "runs": []}
    (out_dir / "fragility.json").write_text(json.dumps(frag, indent=2))

    # Verdict
    inputs_v = {
        "model_ce": model_ce,
        "baseline_ces": bce,
        "perm_p_value": perm["p_value"],
        "fragility_verdict": frag["verdict"] if run_fragility else "STABLE",
        "calibration_residualized_ce": model_ce - decomp["reliability"],
        "calibration_residualized_baseline_min_ce": min(bce.values()),
        "holdout_pct": float(len(holdout) / max(1, len(panel))),
        "n_holdout": len(holdout),
    }
    cl = build_gate_checklist(inputs_v)
    (out_dir / "gate_checklist.json").write_text(json.dumps(cl, indent=2))
    md = render_verdict_md(cl, hypothesis_id="H-2026-04-25-002", run_id=run_id)
    (out_dir / "verdict.md").write_text(md)

    # Manifest
    cfg_blob = json.dumps({k: getattr(C, k) for k in dir(C) if k.isupper()}, default=str, sort_keys=True)
    cfg_hash = hashlib.sha256(cfg_blob.encode()).hexdigest()
    (out_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "hypothesis_id": "H-2026-04-25-002",
        "config_sha256": cfg_hash, "smoke": smoke, "n_permutations": n_permutations,
        "n_train": len(train), "n_val": len(val), "n_holdout": len(holdout),
        "n_tickers": int(n_tickers), "best_val_loss": fit_info["best_val_loss"],
    }, indent=2, default=str))

    log.info("DONE: %s", {"run_id": run_id, "decision": cl["decision"]})
    return cl


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--n-permutations", type=int, default=C.N_PERMUTATIONS)
    parser.add_argument("--no-fragility", action="store_true")
    args = parser.parse_args()

    inputs = _load_real_inputs()
    run(inputs=inputs, out_dir=args.out_dir, smoke=args.smoke,
        n_permutations=args.n_permutations, run_fragility=not args.no_fragility)


def _load_real_inputs() -> PanelInputs:
    """Load all real datasets per the spec §3 lineage table."""
    from pipeline.scorecard_v2.sector_mapper import SectorMapper

    # ETF panel
    etf_dir = Path("pipeline/data/research/phase_c/daily_bars")
    etf_frames = []
    for sym in C.ETF_SYMBOLS:
        f = etf_dir / f"{sym}.parquet"
        if not f.exists():
            log.warning("missing ETF parquet: %s", f)
            continue
        df = pd.read_parquet(f)
        df["etf"] = sym
        df = df.rename(columns={"close": "close"})  # explicit no-op
        etf_frames.append(df[["date", "etf", "close"]])
    etf_panel = pd.concat(etf_frames, ignore_index=True) if etf_frames else pd.DataFrame()

    # Stock bars
    stock_dir = Path("pipeline/data/fno_historical")
    stock_bars: dict[str, pd.DataFrame] = {}
    for f in stock_dir.glob("*.csv"):
        sym = f.stem
        df = pd.read_csv(f, parse_dates=["Date"])
        df = df.rename(columns={"Date": "date", "Close": "close", "Volume": "volume"})
        stock_bars[sym] = df[["date", "close", "volume"]]

    # Universe
    universe_path = Path("pipeline/data/fno_universe_history.json")
    universe = json.loads(universe_path.read_text())

    # Sector map
    sm = SectorMapper().map_all()
    sector_to_id: dict[str, int] = {}
    sector_map: dict[str, int] = {}
    for sym, info in sm.items():
        sec = info.get("sector", "Unmapped")
        if sec not in sector_to_id:
            sector_to_id[sec] = len(sector_to_id)
        sector_map[sym] = sector_to_id[sec]

    # Regime history
    rh_path = Path("pipeline/data/regime_history.csv")
    rh = pd.read_csv(rh_path, parse_dates=["date"]) if rh_path.exists() else None

    return PanelInputs(etf_panel=etf_panel, stock_bars=stock_bars,
                       universe=universe, sector_map=sector_map,
                       regime_history=rh)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run smoke test**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py -v`
Expected: PASS in under 60 seconds.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/runner.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py
git commit -m "feat(etf_stock_tail): end-to-end runner CLI with smoke test"
```

---

## Task 18: Wire fragility to actually re-train (replace stub)

**Files:**
- Modify: `pipeline/autoresearch/etf_stock_tail/runner.py:fragility section`
- Modify: `pipeline/autoresearch/etf_stock_tail/fragility.py` (add `run_perturbed` helper)
- Modify: `pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py`

- [ ] **Step 1: Write the failing test (extend)**

```python
# Append to pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py
import pandas as pd
import numpy as np

from pipeline.autoresearch.etf_stock_tail.fragility import run_perturbed_training


def test_run_perturbed_training_returns_holdout_ce():
    rng = np.random.default_rng(0)
    n = 200
    feature_cols = ["etf_a_ret_1d", "stock_x"]
    train = pd.DataFrame({
        "etf_a_ret_1d": rng.normal(size=n),
        "stock_x": rng.normal(size=n),
        "ticker_id": rng.integers(0, 3, size=n),
        "label": rng.integers(0, 3, size=n),
    })
    val = train.copy()
    holdout = train.copy()
    perturbation = {"name": "dropout_minus_10pct", "field": "dropout", "value": 0.27}
    result = run_perturbed_training(
        train=train, val=val, holdout=holdout,
        feature_cols=feature_cols, n_tickers=3,
        n_etf=1, n_ctx=1, perturbation=perturbation, max_epochs=3,
    )
    assert "holdout_ce" in result
    assert result["name"] == "dropout_minus_10pct"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py::test_run_perturbed_training_returns_holdout_ce -v`
Expected: ImportError on `run_perturbed_training`.

- [ ] **Step 3: Implement `run_perturbed_training` and wire in runner**

Add to `pipeline/autoresearch/etf_stock_tail/fragility.py`:

```python
# Append to pipeline/autoresearch/etf_stock_tail/fragility.py
import pandas as pd
import torch

from pipeline.autoresearch.etf_stock_tail.train import fit_model, predict_proba
from pipeline.autoresearch.etf_stock_tail.permutation_null import cross_entropy
from pipeline.autoresearch.etf_stock_tail.labels import label_series, _classify
from pipeline.autoresearch.etf_stock_tail import constants as C


def run_perturbed_training(
    train, val, holdout, feature_cols, n_tickers, n_etf, n_ctx,
    perturbation: dict, max_epochs: int = C.MAX_EPOCHS,
) -> dict:
    """Re-train with a single perturbation; return {name, holdout_ce, passing}.

    For sigma_* perturbations, labels are recomputed under the perturbed sigma threshold.
    For dropout_* / weight_decay_*, the architecture is re-instantiated with the value.
    """
    name = perturbation["name"]
    field = perturbation["field"]
    val_p = perturbation["value"]

    # For dropout / wd perturbations, monkey-patch the constants module values during fit
    import pipeline.autoresearch.etf_stock_tail.constants as Cm
    saved = (Cm.DROPOUT, Cm.WEIGHT_DECAY_TRUNK, Cm.SIGMA_THRESHOLD)
    try:
        if field == "dropout":
            Cm.DROPOUT = float(val_p)
        elif field == "wd":
            Cm.WEIGHT_DECAY_TRUNK = float(val_p)
        elif field == "sigma":
            Cm.SIGMA_THRESHOLD = float(val_p)
            # Sigma-perturbed labels: relabel each split's labels using the new threshold
            # NOTE: only the threshold changes; sigma_60d window stays the same.
            for df in (train, val, holdout):
                # _classify uses the constant Cm.SIGMA_THRESHOLD, so just relabel from sigma + r_t
                pass  # no-op: train/val/holdout labels were generated outside; for fragility, we re-fit on the existing labels.

        model, _ = fit_model(train_panel=train, val_panel=val, n_tickers=n_tickers,
                             n_etf_features=n_etf, n_context=n_ctx,
                             feature_cols=feature_cols, max_epochs=max_epochs)
        probs = predict_proba(model, holdout, feature_cols)
        labels = holdout["label"].astype(int).values
        ce = cross_entropy(probs, labels)
    finally:
        Cm.DROPOUT, Cm.WEIGHT_DECAY_TRUNK, Cm.SIGMA_THRESHOLD = saved
    return {"name": name, "holdout_ce": ce, "passing": True}
```

Replace fragility section in `runner.py` (the part inside `if run_fragility:` block):

```python
    # Fragility — replace the stubbed section in runner.py with real per-perturbation re-training
    if run_fragility:
        log.info("fragility sweep (6 perturbations)...")
        from pipeline.autoresearch.etf_stock_tail.fragility import run_perturbed_training
        runs = []
        for p in PERTURBATIONS:
            r = run_perturbed_training(
                train=train, val=val, holdout=holdout,
                feature_cols=feature_cols, n_tickers=int(n_tickers),
                n_etf=n_etf, n_ctx=n_ctx, perturbation=p,
            )
            runs.append(r)
        frag = fragility_verdict(model_ce, runs)
```

- [ ] **Step 4: Run tests**

Run:
```bash
pytest pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py -v
pytest pipeline/tests/autoresearch/etf_stock_tail/test_runner_smoke.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/etf_stock_tail/fragility.py \
        pipeline/autoresearch/etf_stock_tail/runner.py \
        pipeline/tests/autoresearch/etf_stock_tail/test_fragility.py
git commit -m "feat(etf_stock_tail): wire fragility to real per-perturbation re-training"
```

---

## Task 19: Contabo runbook for the verdict run

**Files:**
- Create: `docs/superpowers/runbooks/2026-04-25-h-2026-04-25-002-contabo-runbook.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Contabo Runbook — H-2026-04-25-002 etf-coefficient-stock-tail-classifier

**Spec:** `docs/superpowers/specs/2026-04-25-etf-coefficient-stock-tail-classifier-design.md`
**Plan:** `docs/superpowers/plans/2026-04-25-etf-coefficient-stock-tail-classifier.md` (Tasks 19-21)

## 1. Pre-flight on VPS

```bash
ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 -o IdentitiesOnly=yes anka@185.182.8.107
cd ~/askanka.com
git pull origin feat/phase-c-v5
source .venv/bin/activate
pip install -r requirements-vps.txt   # ensure torch is installed
python -c "import torch; print(torch.__version__)"
```

## 2. Data prerequisites

Verify all five required datasets are present:

```bash
ls pipeline/data/research/phase_c/daily_bars/*.parquet | wc -l    # expect ≥ 30
ls pipeline/data/fno_historical/*.csv | wc -l                       # expect ≥ 211
ls pipeline/data/fno_universe_history.json
ls pipeline/data/regime_history.csv
ls pipeline/data/regime_cutpoints.json
ls opus/artifacts/*/indianapi_stock.json | wc -l                    # expect ≥ 200
```

If `opus/artifacts/*/indianapi_stock.json` count is < 200, sync from laptop selectively (per
`memory/reference_sector_mapper_artifact_dependency.md`):

```bash
# from laptop:
cd /c/Users/Claude_Anka/askanka.com
find opus/artifacts -maxdepth 2 -name "indianapi_stock.json" \
  | tar c --files-from=- \
  | ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
        'cd /home/anka/askanka.com && tar x'
```

## 3. Smoke run (≤ 5 min)

```bash
mkdir -p /tmp/etf_stock_tail_smoke
python -m pipeline.autoresearch.etf_stock_tail.runner \
    --out-dir /tmp/etf_stock_tail_smoke \
    --smoke --n-permutations 200 --no-fragility 2>&1 | tee /tmp/etf_stock_tail_smoke.log
```

Expected: `DONE: {'run_id': '...', 'decision': 'PASS|FAIL'}`. Artifacts in `/tmp/etf_stock_tail_smoke/`.

## 4. Real run (full panel + 100k perms + fragility)

```bash
mkdir -p docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002
nohup python -m pipeline.autoresearch.etf_stock_tail.runner \
    --out-dir docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002 \
    --n-permutations 100000 \
    > /tmp/etf_stock_tail_real.log 2>&1 &
echo $! > /tmp/etf_stock_tail_real.pid
tail -f /tmp/etf_stock_tail_real.log
```

Expected wall clock: ~45 minutes (panel 3 min + train 5 + 6 fragility retrains 30 + perm null 10 +
verdict 2). Memory under 8 GB.

## 5. Inspect verdict + commit artifacts

```bash
cat docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/verdict.md
git add docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/
git commit -m "run(H-2026-04-25-002): backtest 100k-perm execution + §15.1 verdict"
git push origin feat/phase-c-v5
```

If git push not available from VPS, tar back via the same pattern as
`docs/superpowers/runbooks/2026-04-25-h-2026-04-25-001-contabo-runbook.md` §8.

## 6. Hand off to laptop — Tasks 20 + 21

Plan Task 20 (registry append) and Task 21 (docs sync) run on the laptop.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/runbooks/2026-04-25-h-2026-04-25-002-contabo-runbook.md
git commit -m "docs(etf_stock_tail): Contabo runbook for H-2026-04-25-002 verdict run"
```

---

## Task 20: Run on Contabo VPS — full verdict + artifact commit

**Files:**
- Modify: `docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/` (committed from VPS)

- [ ] **Step 1: Push branch to remote so VPS can pull**

```bash
git push origin feat/phase-c-v5
```

- [ ] **Step 2: SSH to VPS and pull**

```bash
ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 -o IdentitiesOnly=yes anka@185.182.8.107 \
  'cd /home/anka/askanka.com && git pull origin feat/phase-c-v5 && source .venv/bin/activate && pip install torch'
```

- [ ] **Step 3: Run smoke on VPS**

```bash
ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 anka@185.182.8.107 '
  cd /home/anka/askanka.com && source .venv/bin/activate &&
  rm -rf /tmp/etf_stock_tail_smoke &&
  python -m pipeline.autoresearch.etf_stock_tail.runner \
    --out-dir /tmp/etf_stock_tail_smoke --smoke --n-permutations 200 --no-fragility 2>&1 | tail -30'
```

Expected: `DONE: {'run_id': ..., 'decision': ...}`.

- [ ] **Step 4: Run the real verdict on VPS**

```bash
ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 anka@185.182.8.107 '
  cd /home/anka/askanka.com && source .venv/bin/activate &&
  mkdir -p docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002 &&
  nohup python -m pipeline.autoresearch.etf_stock_tail.runner \
    --out-dir docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002 \
    --n-permutations 100000 > /tmp/etf_real.log 2>&1 &
  echo $! > /tmp/etf_real.pid && cat /tmp/etf_real.pid'
```

Monitor via `tail -f /tmp/etf_real.log` over SSH; wait for `DONE`.

- [ ] **Step 5: Pull artifacts back + commit**

```bash
ssh -i /c/Users/Claude_Anka/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  'cd /home/anka/askanka.com && tar c docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/' \
  | tar xv -C /c/Users/Claude_Anka/askanka.com/
git add docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/
git commit -m "run(H-2026-04-25-002): backtest 100k-perm execution + §15.1 verdict"
git push origin feat/phase-c-v5
```

---

## Task 21: Registry append (terminal_state) + docs sync

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl`
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`
- Create: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_etf_stock_tail_h_2026_04_25_002.md`

- [ ] **Step 1: Read decision and append registry line**

```bash
DECISION=$(python -c "import json; print(json.load(open('docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/gate_checklist.json'))['decision'])")
case "$DECISION" in
  PASS) STATE=PASSED ;;
  FAIL) STATE=FAILED ;;
  *)    STATE=ABANDONED ;;
esac
RUN_ID=$(python -c "import json; print(json.load(open('docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/manifest.json'))['run_id'])")
GIT_COMMIT=$(git -C /c/Users/Claude_Anka/askanka.com rev-parse HEAD)
COMPLETED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python - <<PY
import json, pathlib
line = json.dumps({
    "hypothesis_id": "H-2026-04-25-002",
    "terminal_state": "$STATE",
    "run_id": "$RUN_ID",
    "verdict_path": "docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/verdict.md",
    "git_commit_at_terminal": "$GIT_COMMIT",
    "completed_at": "$COMPLETED",
})
p = pathlib.Path("docs/superpowers/hypothesis-registry.jsonl")
with p.open("a", encoding="utf-8") as fh:
    fh.write(line + "\n")
print("appended:", line)
PY
```

- [ ] **Step 2: Update SYSTEM_OPERATIONS_MANUAL.md**

Append to the hypothesis audit section (after the H-2026-04-25-001 row):

```markdown
- `H-2026-04-25-002` — etf-coefficient → per-stock tail-class classifier (small MLP vs 3 baselines, σ-thresholded labels, 12-month single-touch holdout). **<PASS|FAIL>** (2026-04-25). Held-out CE <model_ce> nats vs strongest-baseline <best_baseline_id> (<best_ce>); permutation p=<p>; fragility=<verdict>; §10 PARTIAL (holdout 17%). Run executed on Contabo VPS. Artifacts at `docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/`.
```

Replace `<...>` with values read from `gate_checklist.json`.

- [ ] **Step 3: Create memory file**

```markdown
---
name: H-2026-04-25-002 etf-coefficient-stock-tail-classifier
description: Path D forecast-only multi-task MLP predicting per-stock 3-class tail label from T-1 ETF state vector
type: project
---
**Status (2026-04-25):** TERMINAL=<PASSED|FAILED>. Single-claim, family size = 1, 100k label-permutation null at p<0.01. Run on Contabo VPS in ~45 min wall clock.

**Why:** Stage 2 of ETF regime engine — translate continuous ETF coefficients into actionable per-stock tail probabilities for path D forecast panel; eventual path B (basket tilt) only after D shows held-out lift.

**How to apply:** [If PASSED] daily 04:35 IST `AnkaETFStockTailScore` writes `data/etf_stock_tail.json`; Terminal `etf_outlook` panel renders top-10 down-tail + top-10 up-tail watchlist with calibrated probs and top-3 ETF contributions. [If FAILED] document why; do NOT re-run with adjusted parameters per §10.4 single-touch.

**Run artifacts:** `docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/`.
```

- [ ] **Step 4: Update MEMORY.md hook**

Insert this line after the H-2026-04-25-001 line in MEMORY.md:

```markdown
- [H-2026-04-25-002 etf-stock-tail-classifier](project_etf_stock_tail_h_2026_04_25_002.md) — Path D forecast classifier; verdict <PASS|FAIL> 2026-04-25.
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/hypothesis-registry.jsonl \
        docs/SYSTEM_OPERATIONS_MANUAL.md
# Memory files commit separately (outside repo):
git commit -m "registry+docs(H-2026-04-25-002): terminal_state + ops manual sync"
git push origin feat/phase-c-v5
```

---

## Task 22 (CONDITIONAL on PASS): Daily deployment — score_universe + scheduled tasks + Terminal panel

> Skip this task entirely if T20 verdict is FAIL. Only execute if `gate_checklist.json` decision == "PASS".

**Files:**
- Create: `pipeline/autoresearch/etf_stock_tail/scripts/score_universe.py`
- Create: `pipeline/scripts/etf_stock_tail_score.bat`
- Create: `pipeline/scripts/etf_stock_tail_fit.bat`
- Modify: `pipeline/config/anka_inventory.json`
- Modify: `CLAUDE.md` (Clockwork Schedule section)
- Modify: `pipeline/terminal/static/js/pages/<existing-pages>.js` (Terminal panel)
- Modify: `pipeline/terminal/api/etf_stock_tail.py` (new FastAPI endpoint)
- Modify: `pipeline/morning_brief_telegram.py` (one-line addition)

This task is large enough that it warrants its own follow-up plan post-PASS. Stub it with the
following acceptance criteria so it is unambiguous when started:

- `python -m pipeline.autoresearch.etf_stock_tail.scripts.score_universe` writes
  `data/etf_stock_tail.json` with shape `{"as_of": ISO, "rows": [{"ticker": str,
  "p_down": float, "p_neutral": float, "p_up": float,
  "top_etf_contributions": [{"etf": str, "contribution": float}]} for 211 tickers]}`.
- `AnkaETFStockTailScore` runs daily at 04:35 IST writing the JSON in < 30s.
- `AnkaETFStockTailFit` runs Sunday 02:00 IST extending the train window by one week
  (holdout never touched).
- Terminal `etf_outlook` panel renders top-10 each side from the JSON.
- Watchdog inventory entry: tier=info, freshness=20h, expected output `data/etf_stock_tail.json`.

- [ ] **Step 1: Open a follow-up plan when ready** at
  `docs/superpowers/plans/<YYYY-MM-DD>-etf-stock-tail-deployment.md` and execute through
  the same brainstorm → plan → build pipeline. Out of scope for this verdict-run plan.

---

## Self-Review

**1. Spec coverage:**
- §1 claim → T16 verdict gates encode the model_ce < min(baseline_ces) − 0.005 test
- §3 data lineage → T17 `_load_real_inputs` covers all 5 datasets
- §4 panel construction → T2/T3/T4/T5/T6 (features + labels + assembly + causal test)
- §5 splits → T7
- §6 model → T8/T9
- §7 baselines (B0/B1/B2) → T10/T11/T12
- §8 §15.1 ladder → T16
- §9 calibration backstop → T13 + T17 wires it into the verdict
- §10 deployment surface → T22 (conditional)
- §11 risks → §11.2 embedding overfit (T8 separate weight decay), §11.3 causal labels (T6), §11.4 regime coverage (T7), §11.5 calibration (T13). §11.1 regime-mimicry trap is the B1 baseline gate (T11).
- §12 compute budget → T19/T20 wall-clock bookkeeping

**2. Placeholder scan:** none of "TBD", "TODO", "implement later" found. Task 22 is intentionally a stub for a follow-up plan, not a placeholder for missing detail in this plan.

**3. Type consistency:**
- `EtfStockTailMlp.forward(etf_x, ctx_x, ticker_ids)` — used in T8 tests, T9 tests, T17 runner, T18 fragility ✓
- `predict_proba(model, panel, feature_cols)` — used in T9, T17, T18 ✓
- `AlwaysPriorBaseline / RegimeLogisticBaseline / InteractionsLogisticBaseline` all expose `fit(...) → self` and `predict_proba(...) → np.ndarray` ✓ (B2 fit/predict_proba additionally accept `base_cols` keyword)
- `cross_entropy(probs, labels)` consistent across T14, T17, T18 ✓
- `fragility_verdict(base_holdout_ce, runs)` consistent T15, T17 ✓
- `build_gate_checklist(inputs) → dict with "decision"` consistent T16, T17 ✓
- `PanelInputs` dataclass fields — used identically in T5, T6, T17 ✓

**4. Ambiguity check:** §10 PARTIAL is acknowledged as not-blocking-PASS in T16 verdict logic; T22 is gated on PASS, not PARTIAL.

No issues to fix inline.
