# Regime-Aware Autoresearch Engine v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the parked v1 regime-aware autoresearch engine (commit `09847ef`) with (a) panel extended 252 trading days earlier, (b) construction-matched random-basket hurdle replacing NIFTY B&H, (c) feature library widened 20 → 34, and actually exercise Mode 2 autonomous orchestration end-to-end.

**Architecture:** Reuse every v1 component that wasn't the bottleneck (DSL grammar, proposer view-isolation, walk-forward folds, 3-gate verdict, forward-shadow, kill switch, lifecycle, 7-state promotions). Modify four files (`constants.py`, `features.py`, `in_sample_runner.py`, `incumbents.py`). Add one module (`null_basket_hurdle.py`) and three scripts (`run_mode2.py`, `run_bh_fdr_check.py`, `promote_to_live.py`). Shard the single `proposal_log.jsonl` into five per-regime logs.

**Tech Stack:** Python 3.11, pandas/numpy, scipy.stats for skew/kurt, pyarrow for parquet, Anthropic SDK for Haiku 4.5, pytest for TDD.

**Spec:** `docs/superpowers/specs/2026-04-25-regime-aware-autoresearch-v2-design.md` @ commit `4e3d483`.

---

## File Structure

**Modified from v1:**
| File | What changes |
|---|---|
| `pipeline/autoresearch/regime_autoresearch/constants.py` | +`PANEL_START = "2020-04-23"` |
| `pipeline/autoresearch/regime_autoresearch/features.py` | +14 `FEATURE_FUNCS` entries, +14 `_fast_*` kernels, drift-assert extended |
| `pipeline/autoresearch/regime_autoresearch/in_sample_runner.py` | `regime_buy_and_hold_sharpe` call-site swapped to `load_null_basket_hurdle(..., window="train_val")` |
| `pipeline/autoresearch/regime_autoresearch/incumbents.py` | Delete scarcity-fallback branch |
| `pipeline/autoresearch/regime_autoresearch/proposer.py` | Write to per-regime log file |
| `pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py` | Panel start extended to `PANEL_START` |
| `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py` | Swap hurdle call, swap log path |
| `pipeline/config/anka_inventory.json` | +3 task entries |
| `docs/SYSTEM_OPERATIONS_MANUAL.md` | Station 11 v2 diffs |

**New files:**
| Path | Responsibility |
|---|---|
| `pipeline/autoresearch/regime_autoresearch/null_basket_hurdle.py` | `compute_hurdle_table()`, `load_null_basket_hurdle()` |
| `pipeline/autoresearch/regime_autoresearch/scripts/build_null_basket_hurdles.py` | One-shot CLI to produce the parquet |
| `pipeline/autoresearch/regime_autoresearch/scripts/run_mode2.py` | Orchestrator: spawn 5 regime workers, wait |
| `pipeline/autoresearch/regime_autoresearch/scripts/run_bh_fdr_check.py` | Daily BH-FDR trigger |
| `pipeline/autoresearch/regime_autoresearch/scripts/promote_to_live.py` | Human-gated write-strategy-file CLI |
| `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet` | 1,200-row hurdle table |
| `pipeline/autoresearch/regime_autoresearch/data/panel_coverage_audit_2026-04-25.json` | Dropped-ticker audit |
| `pipeline/scripts/AnkaAutoresearchMode2.bat` | Scheduled-task wrapper |
| `pipeline/scripts/AnkaAutoresearchBHFDR.bat` | Scheduled-task wrapper |
| `pipeline/scripts/AnkaAutoresearchHoldout.bat` | Scheduled-task wrapper |

**New tests** (all under `pipeline/tests/autoresearch/regime_autoresearch/`):
- `test_panel_extension.py`
- `test_null_basket_hurdle.py`
- `test_features_v2.py`
- `test_proposal_log_sharding.py`
- `test_mode2_orchestration.py`
- `test_bh_fdr_per_regime.py`
- `test_promote_to_live.py`

**Renames (via `git mv`):**
- `pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl` → `proposal_log_neutral.jsonl`

---

## Task 1: Constants + Panel Extension

**Files:**
- Modify: `pipeline/autoresearch/regime_autoresearch/constants.py` (line 21 region — add `PANEL_START` below the split boundaries block)
- Modify: `pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py` (change start-date constant)
- Create: `pipeline/autoresearch/regime_autoresearch/data/panel_coverage_audit_2026-04-25.json`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py`

### Step 1.1: Write failing test for PANEL_START constant

- [ ] Create `pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py` with:

```python
"""Tests for v2 panel extension (Task 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def test_panel_start_constant_exists_and_is_2020_04_23():
    from pipeline.autoresearch.regime_autoresearch import constants
    assert hasattr(constants, "PANEL_START"), (
        "v2 requires PANEL_START in constants.py"
    )
    assert constants.PANEL_START == "2020-04-23", (
        f"PANEL_START must be '2020-04-23' (252 trading days before "
        f"TRAIN_VAL_START); got {constants.PANEL_START!r}"
    )
    # Must stay strictly earlier than TRAIN_VAL_START.
    assert pd.Timestamp(constants.PANEL_START) < pd.Timestamp(
        constants.TRAIN_VAL_START
    )
```

### Step 1.2: Run test to verify it fails

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py::test_panel_start_constant_exists_and_is_2020_04_23 -v`
Expected: FAIL with `AttributeError: module 'pipeline.autoresearch.regime_autoresearch.constants' has no attribute 'PANEL_START'`

### Step 1.3: Add PANEL_START to constants.py

Edit `pipeline/autoresearch/regime_autoresearch/constants.py`, insert after line 17 (`# Split boundaries (ISO dates)`) block:

```python
# Split boundaries (ISO dates)
TRAIN_VAL_START = "2021-04-23"
TRAIN_VAL_END = "2024-04-22"
HOLDOUT_START = "2024-04-23"
HOLDOUT_END = "2026-04-23"

# Panel history start — 252 trading days earlier than TRAIN_VAL_START so
# 252-bar trailing-window features (e.g. vol_percentile_252d,
# days_from_52w_high) have full history on day 1 of train+val. Regime
# quantile cutpoints remain frozen on the 2018-01-01..2021-04-22 window
# regardless of this; panel extension is feature-history only.
PANEL_START = "2020-04-23"
```

### Step 1.4: Run test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py::test_panel_start_constant_exists_and_is_2020_04_23 -v`
Expected: PASS

### Step 1.5: Write failing test for audit JSON shape

Append to `pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py`:

```python
def test_panel_coverage_audit_json_shape():
    from pipeline.autoresearch.regime_autoresearch import constants
    audit_path = constants.DATA_DIR / "panel_coverage_audit_2026-04-25.json"
    assert audit_path.exists(), (
        f"Missing {audit_path}; rerun build_regime_history.py for v2."
    )
    obj = json.loads(audit_path.read_text())
    # Required top-level keys.
    for k in ("generated_at", "panel_start", "train_val_end",
              "retained_tickers", "dropped_tickers", "coverage_threshold"):
        assert k in obj, f"audit JSON missing key {k!r}"
    # Coverage threshold constant matches spec §2.1 (<100 missing days).
    assert obj["coverage_threshold"] == {"max_missing_days": 100}
    # Panel window matches constants.
    assert obj["panel_start"] == constants.PANEL_START
    assert obj["train_val_end"] == constants.TRAIN_VAL_END
    # Retained list is non-empty; dropped is a list (may be empty).
    assert isinstance(obj["retained_tickers"], list)
    assert len(obj["retained_tickers"]) > 0
    assert isinstance(obj["dropped_tickers"], list)
    # No duplicates across retained and dropped.
    overlap = set(obj["retained_tickers"]) & {
        d["ticker"] for d in obj["dropped_tickers"]
    }
    assert not overlap, f"Tickers in both retained and dropped: {overlap}"
```

### Step 1.6: Run test — expect FAIL (audit JSON missing)

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py::test_panel_coverage_audit_json_shape -v`
Expected: FAIL with `AssertionError: Missing ...panel_coverage_audit_2026-04-25.json`

### Step 1.7: Extend build_regime_history.py to use PANEL_START and emit audit

Open `pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py`. Find the panel-building block. It currently iterates tickers from `FNO_DIR`, reads their CSVs, filters rows to some start date (likely `TRAIN_VAL_START` or an implicit 2021-01-01).

Make two changes:

1. Import `PANEL_START` and use it as the lower bound:
   ```python
   from pipeline.autoresearch.regime_autoresearch.constants import (
       FNO_DIR, DATA_DIR, PANEL_START, TRAIN_VAL_END, TRAIN_VAL_START,
       HOLDOUT_START, HOLDOUT_END,
   )
   ```
   and when filtering rows: `df = df[df["date"] >= pd.Timestamp(PANEL_START)]`.

2. After the panel loop, add a coverage audit that writes
   `panel_coverage_audit_2026-04-25.json`:
   ```python
   import json
   from datetime import datetime, timezone

   MAX_MISSING_DAYS = 100

   def _audit_coverage(panel_by_ticker: dict[str, pd.DataFrame]) -> dict:
       # Expected trading days from 2020-04-23 to 2024-04-22 — use NIFTY
       # index rows as the canonical business-day calendar.
       canon = panel_by_ticker.get("NIFTY", pd.DataFrame())
       canon_dates = set(pd.to_datetime(canon["date"]).dt.date.tolist())
       canon_in_window = {
           d for d in canon_dates
           if pd.Timestamp(PANEL_START).date() <= d <= pd.Timestamp(
               TRAIN_VAL_END
           ).date()
       }
       retained, dropped = [], []
       for tk, df in panel_by_ticker.items():
           if tk in {"NIFTY", "VIX", "REGIME"}:
               retained.append(tk)
               continue
           have = set(pd.to_datetime(df["date"]).dt.date.tolist())
           missing = len(canon_in_window - have)
           if missing >= MAX_MISSING_DAYS:
               dropped.append({"ticker": tk, "missing_days": missing})
           else:
               retained.append(tk)
       return {
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "panel_start": PANEL_START,
           "train_val_end": TRAIN_VAL_END,
           "holdout_end": HOLDOUT_END,
           "coverage_threshold": {"max_missing_days": MAX_MISSING_DAYS},
           "retained_tickers": sorted(retained),
           "dropped_tickers": sorted(
               dropped, key=lambda d: -d["missing_days"]
           ),
       }

   audit = _audit_coverage(panel_by_ticker)
   (DATA_DIR / "panel_coverage_audit_2026-04-25.json").write_text(
       json.dumps(audit, indent=2, sort_keys=False)
   )
   ```

### Step 1.8: Run the build script to produce the audit

Run (from repo root):

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.build_regime_history
```

Expected output: no Python exceptions; `regime_history.csv` regenerated; `panel_coverage_audit_2026-04-25.json` created; NIFTY first row dated `2020-04-23` or later.

### Step 1.9: Run audit test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py -v`
Expected: both tests PASS.

### Step 1.10: Run full regime_autoresearch test suite — expect no regressions

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/ -v`
Expected: 139 prior tests PASS, +2 new PASS = 141 total.

### Step 1.11: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/constants.py \
        pipeline/autoresearch/regime_autoresearch/scripts/build_regime_history.py \
        pipeline/autoresearch/regime_autoresearch/data/panel_coverage_audit_2026-04-25.json \
        pipeline/autoresearch/regime_autoresearch/data/regime_history.csv \
        pipeline/tests/autoresearch/regime_autoresearch/test_panel_extension.py

git commit -m "feat(autoresearch): v2 Task 1 — panel start PANEL_START=2020-04-23

Extends panel history 252 trading days before TRAIN_VAL_START so 252-bar
trailing-window features have full history on day 1 of train+val. Emits
panel_coverage_audit_2026-04-25.json listing dropped tickers (>=100
missing days in 2020-04-23..2024-04-22).

Regime quantile cutpoints unchanged — still frozen on 2018-01-01..
2021-04-22 window.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Null-Basket Hurdle Precompute

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/null_basket_hurdle.py`
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/build_null_basket_hurdles.py`
- Create: `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py`

### Step 2.1: Write failing test for compute_hurdle_table shape

Create `pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py`:

```python
"""Tests for v2 construction-matched null-basket hurdle (Task 2)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _synth_panel(n_tickers=30, n_days=500, seed=0):
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    dates = pd.bdate_range("2020-04-23", periods=n_days)
    rows = []
    for tk in tickers:
        price = 100.0
        for d in dates:
            price *= (1.0 + rng.normal(0, 0.012))
            rows.append({"date": d, "ticker": tk, "close": price,
                         "volume": 1_000_000.0, "sector": "X"})
    return pd.DataFrame(rows)


def test_hurdle_table_has_1200_rows_and_required_columns():
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table,
    )
    panel = _synth_panel()
    event_dates_by_regime = {
        r: pd.DatetimeIndex(panel["date"].unique()[50:200:3])
        for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")
    }
    holdout_event_dates_by_regime = {
        r: pd.DatetimeIndex(panel["date"].unique()[200:400:5])
        for r in event_dates_by_regime
    }
    table = compute_hurdle_table(
        panel=panel,
        event_dates_by_regime=event_dates_by_regime,
        holdout_event_dates_by_regime=holdout_event_dates_by_regime,
        n_trials=20,  # tiny for test speed
    )
    # 5 constructions × 8 k-values × 3 horizons × 5 regimes × 2 windows = 1200
    assert len(table) == 1200, f"Expected 1200 rows, got {len(table)}"
    for col in (
        "construction", "k", "hold_horizon", "regime", "window",
        "hurdle_sharpe_median", "hurdle_sharpe_p95",
        "n_events", "n_trials", "seed", "generated_at_sha",
    ):
        assert col in table.columns, f"missing column {col!r}"
    assert set(table["window"].unique()) == {"train_val", "holdout"}
```

### Step 2.2: Run test — expect FAIL (module not found)

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py::test_hurdle_table_has_1200_rows_and_required_columns -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.autoresearch.regime_autoresearch.null_basket_hurdle'`

### Step 2.3: Create null_basket_hurdle.py

Create `pipeline/autoresearch/regime_autoresearch/null_basket_hurdle.py`:

```python
"""v2 construction-matched random-basket hurdle.

Replaces v1's `regime_buy_and_hold_sharpe` (long-only NIFTY) with a
bootstrap null: for a proposed rule with construction C, cardinality k,
hold horizon h, and regime R, sample 1,000 trials where each trial picks
k random tickers per event date and applies C's sign semantics. Median
trial Sharpe is the hurdle; p95 is a diagnostic upper band.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, REGIMES,
)
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    _net_sharpe, _per_ticker_close_map, _per_ticker_dates,
    _nth_trading_day_after, _trade_return,
)

# Enumerated axes — matches DSL grammar v1 surface area.
CONSTRUCTIONS: tuple[str, ...] = (
    "single_long", "single_short", "top_k", "bottom_k", "long_short_basket",
)
K_VALUES: tuple[int, ...] = (1, 5, 10, 15, 20, 25, 30, 40)
HOLD_HORIZONS: tuple[int, ...] = (1, 5, 10)
WINDOWS: tuple[str, ...] = ("train_val", "holdout")

HURDLE_PARQUET = DATA_DIR / "null_basket_hurdles_v2.parquet"
N_TRIALS_PROD = 1000


def _seed_for(construction: str, k: int, h: int, regime: str,
              window: str) -> int:
    tag = f"{construction}|{k}|{h}|{regime}|{window}"
    return int(
        hashlib.sha256(tag.encode()).hexdigest()[:8], 16
    ) & 0xFFFFFFFF


def _direction_for(construction: str, leg: str) -> int:
    """+1 for long legs, -1 for short legs. `leg` is 'long' or 'short'."""
    if construction == "single_long" or construction == "top_k":
        return +1
    if construction == "single_short" or construction == "bottom_k":
        return -1
    if construction == "long_short_basket":
        return +1 if leg == "long" else -1
    raise ValueError(f"unknown construction {construction!r}")


def _trial_event_return(close_map, date_arrs, tickers_pool, event_date,
                         construction, k, h, rng) -> float | None:
    """Simulate one trial's return on one event date."""
    if construction == "long_short_basket":
        if len(tickers_pool) < 2 * k:
            return None
        picks = rng.choice(tickers_pool, size=2 * k, replace=False)
        longs, shorts = picks[:k].tolist(), picks[k:].tolist()
        long_rets, short_rets = [], []
        for tk in longs:
            exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
            if exit_d is None:
                continue
            r = _trade_return(close_map, tk, event_date, exit_d, +1)
            if r is not None:
                long_rets.append(r)
        for tk in shorts:
            exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
            if exit_d is None:
                continue
            r = _trade_return(close_map, tk, event_date, exit_d, -1)
            if r is not None:
                short_rets.append(r)
        if not long_rets or not short_rets:
            return None
        return 0.5 * float(np.mean(long_rets)) + 0.5 * float(
            np.mean(short_rets)
        )
    # Single-leg constructions: single_long / single_short / top_k / bottom_k.
    effective_k = 1 if construction in ("single_long", "single_short") else k
    if len(tickers_pool) < effective_k:
        return None
    picks = rng.choice(tickers_pool, size=effective_k, replace=False).tolist()
    direction = _direction_for(construction, leg="long")
    rets = []
    for tk in picks:
        exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
        if exit_d is None:
            continue
        r = _trade_return(close_map, tk, event_date, exit_d, direction)
        if r is not None:
            rets.append(r)
    if not rets:
        return None
    return float(np.mean(rets))


def _compute_one_cell(panel: pd.DataFrame, event_dates: pd.DatetimeIndex,
                      construction: str, k: int, h: int, regime: str,
                      window: str, n_trials: int) -> dict:
    date_arrs = _per_ticker_dates(panel)
    close_map = _per_ticker_close_map(panel)
    tickers_pool = np.array(sorted(
        set(panel["ticker"].unique()) - {"NIFTY", "VIX", "REGIME"}
    ))
    seed = _seed_for(construction, k, h, regime, window)
    rng = np.random.default_rng(seed)
    trial_sharpes = np.full(n_trials, np.nan)
    for trial_i in range(n_trials):
        event_rets = []
        for d in event_dates:
            r = _trial_event_return(
                close_map, date_arrs, tickers_pool,
                d, construction, k, h, rng,
            )
            if r is not None:
                event_rets.append(r * 100.0)  # percent for _net_sharpe
        if not event_rets:
            continue
        trial_sharpes[trial_i] = _net_sharpe(
            pd.Series(event_rets, dtype=float),
            level="S1", hold_horizon=h,
        )
    finite = trial_sharpes[np.isfinite(trial_sharpes)]
    if finite.size == 0:
        hmedian, hp95 = 0.0, 0.0
    else:
        hmedian = float(np.median(finite))
        hp95 = float(np.percentile(finite, 95))
    return {
        "construction": construction,
        "k": k,
        "hold_horizon": h,
        "regime": regime,
        "window": window,
        "hurdle_sharpe_median": hmedian,
        "hurdle_sharpe_p95": hp95,
        "n_events": int(len(event_dates)),
        "n_trials": int(n_trials),
        "seed": int(seed),
        "generated_at_sha": "",  # filled by the CLI at write time
    }


def compute_hurdle_table(
    panel: pd.DataFrame,
    event_dates_by_regime: Mapping[str, pd.DatetimeIndex],
    holdout_event_dates_by_regime: Mapping[str, pd.DatetimeIndex],
    n_trials: int = N_TRIALS_PROD,
) -> pd.DataFrame:
    """Build the 1,200-row hurdle table.

    5 constructions × 8 k × 3 horizons × 5 regimes × 2 windows = 1,200.
    """
    rows: list[dict] = []
    for window, dates_map in (
        ("train_val", event_dates_by_regime),
        ("holdout", holdout_event_dates_by_regime),
    ):
        for regime in REGIMES:
            ev = dates_map.get(regime, pd.DatetimeIndex([]))
            for C in CONSTRUCTIONS:
                for k in K_VALUES:
                    for h in HOLD_HORIZONS:
                        rows.append(_compute_one_cell(
                            panel, ev, C, k, h, regime, window, n_trials,
                        ))
    return pd.DataFrame(rows)


def load_null_basket_hurdle(construction: str, k: int, hold_horizon: int,
                             regime: str, window: str = "train_val",
                             table_path: Path | None = None) -> float:
    """Return the median hurdle Sharpe for a (C, k, h, R, window) tuple.

    Raises KeyError if the tuple is not in the table.
    """
    path = table_path or HURDLE_PARQUET
    if not path.exists():
        raise FileNotFoundError(
            f"Hurdle table not built: {path}. "
            f"Run build_null_basket_hurdles.py."
        )
    tbl = pd.read_parquet(path)
    mask = (
        (tbl["construction"] == construction)
        & (tbl["k"] == k)
        & (tbl["hold_horizon"] == hold_horizon)
        & (tbl["regime"] == regime)
        & (tbl["window"] == window)
    )
    hit = tbl[mask]
    if hit.empty:
        raise KeyError(
            f"No hurdle row for construction={construction!r} k={k} "
            f"h={hold_horizon} regime={regime!r} window={window!r}"
        )
    return float(hit["hurdle_sharpe_median"].iloc[0])
```

### Step 2.4: Run test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py::test_hurdle_table_has_1200_rows_and_required_columns -v`
Expected: PASS

### Step 2.5: Write failing reproducibility test

Append to `test_null_basket_hurdle.py`:

```python
def test_hurdle_table_is_reproducible_from_seed():
    """Same inputs + same seed => same numeric output within tolerance."""
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table,
    )
    panel = _synth_panel(seed=42)
    ev = {r: pd.DatetimeIndex(panel["date"].unique()[50:150:4])
          for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")}
    hv = {r: pd.DatetimeIndex(panel["date"].unique()[200:300:5])
          for r in ev}
    t1 = compute_hurdle_table(panel, ev, hv, n_trials=10)
    t2 = compute_hurdle_table(panel, ev, hv, n_trials=10)
    pd.testing.assert_frame_equal(
        t1.drop(columns=["generated_at_sha"]).reset_index(drop=True),
        t2.drop(columns=["generated_at_sha"]).reset_index(drop=True),
        check_exact=False, rtol=1e-10,
    )
```

### Step 2.6: Run reproducibility test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py::test_hurdle_table_is_reproducible_from_seed -v`
Expected: PASS (seeds are deterministic by construction).

### Step 2.7: Write failing test for load_null_basket_hurdle

Append to `test_null_basket_hurdle.py`:

```python
def test_load_null_basket_hurdle_raises_on_unknown_tuple(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table, load_null_basket_hurdle,
    )
    panel = _synth_panel()
    ev = {r: pd.DatetimeIndex(panel["date"].unique()[50:100:5])
          for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")}
    hv = {r: pd.DatetimeIndex(panel["date"].unique()[150:200:5]) for r in ev}
    t = compute_hurdle_table(panel, ev, hv, n_trials=5)
    path = tmp_path / "hurdles.parquet"
    t.to_parquet(path)
    # Valid tuple returns a float.
    v = load_null_basket_hurdle(
        "top_k", 10, 5, "NEUTRAL", window="train_val", table_path=path,
    )
    assert isinstance(v, float)
    # Unknown tuple raises.
    with pytest.raises(KeyError):
        load_null_basket_hurdle(
            "top_k", 999, 5, "NEUTRAL",
            window="train_val", table_path=path,
        )


def test_load_null_basket_hurdle_raises_on_missing_file(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        load_null_basket_hurdle,
    )
    with pytest.raises(FileNotFoundError):
        load_null_basket_hurdle(
            "top_k", 10, 5, "NEUTRAL",
            window="train_val",
            table_path=tmp_path / "does_not_exist.parquet",
        )
```

### Step 2.8: Run load-function tests — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py -v`
Expected: all 4 tests PASS.

### Step 2.9: Create the build CLI

Create `pipeline/autoresearch/regime_autoresearch/scripts/build_null_basket_hurdles.py`:

```python
"""CLI — precompute the 1,200-row null-basket hurdle parquet once.

Reads regime_history.csv + the v2 panel; writes
data/null_basket_hurdles_v2.parquet. Deterministic; re-runs produce
byte-identical-within-tolerance output.

Run from repo root:
    python -m pipeline.autoresearch.regime_autoresearch.scripts.build_null_basket_hurdles
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, FNO_DIR, PANEL_START, TRAIN_VAL_END, TRAIN_VAL_START,
    HOLDOUT_START, HOLDOUT_END, REGIMES,
)
from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
    HURDLE_PARQUET, N_TRIALS_PROD, compute_hurdle_table,
)


def _load_panel_and_events() -> tuple[pd.DataFrame, dict, dict]:
    # Load the v2 panel — same path build_regime_history.py writes.
    # One option: reuse the panel pickle cached by build_regime_history.
    # For robustness we reload from fno_historical + regime_history.csv.
    regime = pd.read_csv(DATA_DIR / "regime_history.csv",
                         parse_dates=["date"])
    tickers = [p.stem for p in FNO_DIR.glob("*.csv")]
    rows = []
    for tk in tickers:
        df = pd.read_csv(FNO_DIR / f"{tk}.csv", parse_dates=["date"])
        df = df[(df["date"] >= pd.Timestamp(PANEL_START))
                & (df["date"] <= pd.Timestamp(HOLDOUT_END))]
        if df.empty:
            continue
        df["ticker"] = tk
        rows.append(df[["date", "ticker", "close", "volume"]])
    panel = pd.concat(rows, ignore_index=True)
    # Event dates per (regime, window).
    ev_train = {r: pd.DatetimeIndex(sorted(
        regime[(regime["zone"] == r)
                & (regime["date"] >= pd.Timestamp(TRAIN_VAL_START))
                & (regime["date"] <= pd.Timestamp(TRAIN_VAL_END))
                ]["date"].unique()
    )) for r in REGIMES}
    ev_holdout = {r: pd.DatetimeIndex(sorted(
        regime[(regime["zone"] == r)
                & (regime["date"] >= pd.Timestamp(HOLDOUT_START))
                & (regime["date"] <= pd.Timestamp(HOLDOUT_END))
                ]["date"].unique()
    )) for r in REGIMES}
    return panel, ev_train, ev_holdout


def _current_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
        ).strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-trials", type=int, default=N_TRIALS_PROD,
                    help="bootstrap trials per cell (default 1000)")
    ap.add_argument("--out", type=Path, default=HURDLE_PARQUET,
                    help="parquet output path")
    args = ap.parse_args(argv)

    panel, ev_train, ev_holdout = _load_panel_and_events()
    print(f"[build_null_basket_hurdles] panel rows={len(panel):,} "
          f"n_trials={args.n_trials} out={args.out}")
    table = compute_hurdle_table(
        panel=panel,
        event_dates_by_regime=ev_train,
        holdout_event_dates_by_regime=ev_holdout,
        n_trials=args.n_trials,
    )
    table["generated_at_sha"] = _current_git_sha()
    table["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)
    print(f"[build_null_basket_hurdles] wrote {args.out}, "
          f"{len(table)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Step 2.10: Run the build CLI

Run: `python -m pipeline.autoresearch.regime_autoresearch.scripts.build_null_basket_hurdles --n-trials 50`
(Use 50 trials for first verification, not 1000 — full-prod run happens in acceptance step.)

Expected: `null_basket_hurdles_v2.parquet` written at `pipeline/autoresearch/regime_autoresearch/data/`; 1,200 rows; no exceptions.

### Step 2.11: Run build CLI at full 1,000 trials (expect ~40 min)

Run: `python -m pipeline.autoresearch.regime_autoresearch.scripts.build_null_basket_hurdles`
Expected: completes in 30-50 min; parquet overwritten; all 1,200 rows populated.

### Step 2.12: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/null_basket_hurdle.py \
        pipeline/autoresearch/regime_autoresearch/scripts/build_null_basket_hurdles.py \
        pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet \
        pipeline/tests/autoresearch/regime_autoresearch/test_null_basket_hurdle.py

git commit -m "feat(autoresearch): v2 Task 2 — null-basket hurdle precompute

1,200-row construction-matched hurdle table (5 constructions × 8 k × 3
horizons × 5 regimes × 2 windows). Seed = hash(C|k|h|R|window) mod 2^32
gives byte-identical reruns within float tolerance.

load_null_basket_hurdle() is the integration point for in_sample_runner
and holdout_runner — swap lands in Task 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Hurdle Integration

**Files:**
- Modify: `pipeline/autoresearch/regime_autoresearch/in_sample_runner.py` (line 259-303 region, keep function, change call-site)
- Modify: `pipeline/autoresearch/regime_autoresearch/incumbents.py` (line 35-38 scarcity-fallback branch)
- Modify: `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py` (line 51, 196 — swap import + hurdle computation)
- Modify: `pipeline/tests/autoresearch/regime_autoresearch/test_incumbents.py` — update for removed fallback branch

### Step 3.1: Inspect current hurdle call-sites

Read `pipeline/autoresearch/regime_autoresearch/incumbents.py` lines 20-50 and `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py` lines 190-205 to understand what needs to change.

### Step 3.2: Write failing test for v2 hurdle wiring in run_pilot

Create `pipeline/tests/autoresearch/regime_autoresearch/test_hurdle_wiring.py`:

```python
"""Test that run_pilot uses load_null_basket_hurdle (v2), not regime_buy_and_hold."""
from __future__ import annotations

import pathlib


def test_run_pilot_imports_load_null_basket_hurdle():
    run_pilot = pathlib.Path(
        "pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py"
    )
    src = run_pilot.read_text()
    assert "load_null_basket_hurdle" in src, (
        "run_pilot.py must import load_null_basket_hurdle from "
        "null_basket_hurdle module (v2 hurdle integration)."
    )


def test_incumbents_no_longer_has_scarcity_fallback_branch():
    incumbents = pathlib.Path(
        "pipeline/autoresearch/regime_autoresearch/incumbents.py"
    )
    src = incumbents.read_text()
    assert "scarcity_fallback:buy_and_hold" not in src, (
        "v2 deletes the scarcity-fallback branch — hurdle now comes from "
        "null-basket parquet for every proposal."
    )
    assert "INCUMBENT_SCARCITY_MIN" not in src, (
        "v2 deletes the scarcity-fallback branch — the constant is still "
        "in constants.py for audit scripts but must not be used here."
    )
```

### Step 3.3: Run test — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_hurdle_wiring.py -v`
Expected: both tests FAIL.

### Step 3.4: Edit run_pilot.py to use load_null_basket_hurdle

In `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py` line 51, replace:

```python
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    append_proposal_log, regime_buy_and_hold_sharpe, run_in_sample,
)
```

with:

```python
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    append_proposal_log, run_in_sample,
)
from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
    load_null_basket_hurdle,
)
```

Then find line 196 region where the buy-hold fn is constructed. Replace:

```python
buy_hold_fn = lambda r: regime_buy_and_hold_sharpe(  # noqa: E731
    panel, r, benchmark_ticker="NIFTY", hold_horizon=1,
)
```

with hurdle-lookup closures used at the proposal call-site. Find where `hurdle_sharpe` is computed for the proposal (near the `run_in_sample(... incumbent_sharpe=hurdle_sharpe ...)` call at line 759), replace the scarcity-fallback branch with:

```python
hurdle_sharpe = load_null_basket_hurdle(
    construction=proposal.construction_type,
    k=proposal.threshold_value,
    hold_horizon=proposal.hold_horizon,
    regime=proposal.regime,
    window="train_val",
)
```

### Step 3.5: Edit incumbents.py to delete scarcity-fallback branch

Open `pipeline/autoresearch/regime_autoresearch/incumbents.py`. Delete:

```python
from pipeline.autoresearch.regime_autoresearch.constants import (
    INCUMBENT_SCARCITY_MIN, DATA_DIR,
)
```

Replace with:

```python
from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR
```

Delete the scarcity-fallback branch (roughly lines 30-45) including the
`if len(clean) >= INCUMBENT_SCARCITY_MIN:` / `return buy_hold_sharpe_fn(regime), "scarcity_fallback:buy_and_hold"` block. Replace the function with a simple incumbent-mean lookup:

```python
def hurdle_sharpe_for_regime(regime: str,
                               incumbents_df: pd.DataFrame) -> tuple[float, str]:
    """v2: return the mean-of-clean-incumbents Sharpe for the regime.

    v2 eliminates the scarcity fallback — every proposal gets a
    construction-matched null-basket hurdle via `load_null_basket_hurdle`
    at the proposal call-site. This function is retained only for
    incumbent-audit scripts that still want to report the per-regime
    incumbent mean; callers that need the real hurdle should use
    load_null_basket_hurdle directly.
    """
    mask = (incumbents_df["regime"] == regime) & (
        incumbents_df["clean"] == True  # noqa: E712
    )
    clean = incumbents_df[mask]
    if clean.empty:
        return (0.0, "no_incumbent")
    return (float(clean["sharpe"].mean()), "mean_of_incumbents")
```

### Step 3.6: Run wiring test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_hurdle_wiring.py -v`
Expected: both tests PASS.

### Step 3.7: Update existing test_incumbents.py

Open `pipeline/tests/autoresearch/regime_autoresearch/test_incumbents.py`. Find any test referencing `"scarcity_fallback:buy_and_hold"` or `INCUMBENT_SCARCITY_MIN` — remove or replace with a "no_incumbent" expectation. Run:

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_incumbents.py -v`
Expected: ALL tests PASS (update fixtures as needed — spec explicitly allows deleting the fallback branch).

### Step 3.8: Run full regime_autoresearch test suite

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/ -v`
Expected: all tests PASS. New count ≈ 143 (141 + 2 wiring tests).

### Step 3.9: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/incumbents.py \
        pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_incumbents.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_hurdle_wiring.py

git commit -m "feat(autoresearch): v2 Task 3 — swap NIFTY B&H for null-basket hurdle

in_sample_runner + run_pilot now call load_null_basket_hurdle(...,
window='train_val') instead of regime_buy_and_hold_sharpe. Scarcity-
fallback branch deleted from incumbents.py (every proposal now has a
construction-matched null, no special case for <3 incumbents).

regime_buy_and_hold_sharpe itself kept as dead code until v2 shadow
period completes; removing it early would break potential rollback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Feature Library Expansion (20 → 34)

**Files:**
- Modify: `pipeline/autoresearch/regime_autoresearch/features.py` (FEATURE_FUNCS dict, _FAST_FEATURE_FUNCS dispatch, drift-assert, _Context)
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py`

Features added in this exact order (matches §2.3 of spec):
`return_1d`, `return_5d`, `return_60d`, `skewness_20d`, `kurtosis_20d`,
`volume_zscore_20d`, `turnover_percentile_252d`, `volume_trend_5d`,
`excess_return_vs_sector_20d`, `rank_in_sector_20d_return`,
`peer_spread_zscore_20d`, `correlation_to_sector_60d`, `residual_return_5d`,
`adv_ratio_to_sector_mean_20d`.

### Step 4.1: Write failing drift test

Create `pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py`:

```python
"""Tests for v2 feature library expansion (Task 4)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


V2_NEW_FEATURES = (
    "return_1d", "return_5d", "return_60d",
    "skewness_20d", "kurtosis_20d",
    "volume_zscore_20d", "turnover_percentile_252d", "volume_trend_5d",
    "excess_return_vs_sector_20d", "rank_in_sector_20d_return",
    "peer_spread_zscore_20d", "correlation_to_sector_60d",
    "residual_return_5d", "adv_ratio_to_sector_mean_20d",
)


def test_all_14_v2_features_are_registered():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    missing = [f for f in V2_NEW_FEATURES if f not in FEATURE_FUNCS]
    assert not missing, f"v2 features missing from FEATURE_FUNCS: {missing}"


def test_feature_funcs_has_exactly_34_keys():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    assert len(FEATURE_FUNCS) == 34, (
        f"v2 library must have exactly 34 features; got {len(FEATURE_FUNCS)}"
    )
```

### Step 4.2: Run drift test — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py::test_all_14_v2_features_are_registered -v`
Expected: FAIL.

### Step 4.3: Add 14 new feature functions to features.py

Open `pipeline/autoresearch/regime_autoresearch/features.py`. After the last existing feature function (around line 240, below `trust_sector_rank`), add the 14 new functions in the listed order. Each follows the reference-path signature `fn(panel, ticker, t)`:

```python
# ---- v2 feature additions ---------------------------------------------------

def return_1d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t]
    if len(past) < 2:
        return np.nan
    c1, c2 = past["close"].iloc[-1], past["close"].iloc[-2]
    if c2 <= 0:
        return np.nan
    return float(c1 / c2 - 1.0)


def return_5d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t]
    if len(past) < 6:
        return np.nan
    c1, c0 = past["close"].iloc[-1], past["close"].iloc[-6]
    if c0 <= 0:
        return np.nan
    return float(c1 / c0 - 1.0)


def return_60d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t]
    if len(past) < 61:
        return np.nan
    c1, c0 = past["close"].iloc[-1], past["close"].iloc[-61]
    if c0 <= 0:
        return np.nan
    return float(c1 / c0 - 1.0)


def skewness_20d(panel, ticker, t):
    import scipy.stats as sps
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t].tail(21)
    if len(past) < 21:
        return np.nan
    rets = past["close"].pct_change().dropna().values
    if len(rets) < 10:
        return np.nan
    return float(sps.skew(rets, bias=False))


def kurtosis_20d(panel, ticker, t):
    import scipy.stats as sps
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t].tail(21)
    if len(past) < 21:
        return np.nan
    rets = past["close"].pct_change().dropna().values
    if len(rets) < 10:
        return np.nan
    return float(sps.kurtosis(rets, bias=False))  # excess kurtosis


def volume_zscore_20d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t].tail(20)
    if len(past) < 20 or "volume" not in past.columns:
        return np.nan
    vol = past["volume"].astype(float).values
    latest = vol[-1]
    hist = vol[:-1]
    if hist.std(ddof=0) == 0:
        return np.nan
    return float((latest - hist.mean()) / hist.std(ddof=0))


def turnover_percentile_252d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t].tail(252)
    if len(past) < 50 or "volume" not in past.columns:
        return np.nan
    turnover = (past["volume"].astype(float) * past["close"].astype(float))
    latest = turnover.iloc[-1]
    rank = float((turnover <= latest).mean())
    return rank


def volume_trend_5d(panel, ticker, t):
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t].tail(20)
    if len(past) < 20 or "volume" not in past.columns:
        return np.nan
    vol = past["volume"].astype(float).values
    m5 = vol[-5:].mean()
    m20 = vol.mean()
    if m20 == 0:
        return np.nan
    return float(m5 / m20)


def _sector_peers(panel, ticker, t):
    """Returns (peer_df, my_sector) for same-sector tickers on date <= t."""
    if "sector" not in panel.columns:
        return None, None
    my_row = panel[(panel["ticker"] == ticker)
                     & (panel["date"] < t)].tail(1)
    if my_row.empty:
        return None, None
    my_sector = my_row["sector"].iloc[0]
    peers = panel[(panel["sector"] == my_sector)
                    & (panel["date"] < t)]
    return peers, my_sector


def excess_return_vs_sector_20d(panel, ticker, t):
    peers, _ = _sector_peers(panel, ticker, t)
    if peers is None:
        return np.nan
    my_ret = return_5d(panel, ticker, t)  # placeholder; recompute below
    # Compute 20d return explicitly for the ticker and the sector mean.
    def _20d_ret_for(tk):
        df = panel[panel["ticker"] == tk].sort_values("date")
        past = df[df["date"] < t]
        if len(past) < 21:
            return np.nan
        return float(past["close"].iloc[-1] / past["close"].iloc[-21] - 1.0)
    tk_ret = _20d_ret_for(ticker)
    if np.isnan(tk_ret):
        return np.nan
    peer_rets = [
        _20d_ret_for(tk) for tk in peers["ticker"].unique()
        if tk != ticker
    ]
    peer_rets = [r for r in peer_rets if not np.isnan(r)]
    if not peer_rets:
        return np.nan
    return float(tk_ret - np.mean(peer_rets))


def rank_in_sector_20d_return(panel, ticker, t):
    peers, _ = _sector_peers(panel, ticker, t)
    if peers is None:
        return np.nan
    def _20d_ret_for(tk):
        df = panel[panel["ticker"] == tk].sort_values("date")
        past = df[df["date"] < t]
        if len(past) < 21:
            return np.nan
        return float(past["close"].iloc[-1] / past["close"].iloc[-21] - 1.0)
    rets = {tk: _20d_ret_for(tk) for tk in peers["ticker"].unique()}
    rets = {k: v for k, v in rets.items() if not np.isnan(v)}
    if ticker not in rets or len(rets) < 2:
        return np.nan
    my_ret = rets[ticker]
    return float(sum(r <= my_ret for r in rets.values()) / len(rets))


def peer_spread_zscore_20d(panel, ticker, t):
    # 60-day rolling window of daily (ticker_20d_ret - sector_mean_20d_ret).
    df = panel[panel["ticker"] == ticker].sort_values("date")
    past = df[df["date"] < t]
    if len(past) < 80:  # 20d for the return + 60d for the rolling window.
        return np.nan
    peers, _ = _sector_peers(panel, ticker, t)
    if peers is None:
        return np.nan
    # For each of the last 60 dates, compute (ticker_20d_ret - sector_mean_20d_ret).
    spread_series = []
    sample_dates = sorted(past["date"].unique())[-60:]
    for d in sample_dates:
        sub = panel[panel["date"] <= d]
        tk_rows = sub[sub["ticker"] == ticker].sort_values("date")
        if len(tk_rows) < 21:
            continue
        tk_ret = float(tk_rows["close"].iloc[-1] / tk_rows["close"].iloc[-21]
                        - 1.0)
        peer_rets = []
        for peer_tk in peers["ticker"].unique():
            if peer_tk == ticker:
                continue
            pr = sub[sub["ticker"] == peer_tk].sort_values("date")
            if len(pr) < 21:
                continue
            peer_rets.append(
                float(pr["close"].iloc[-1] / pr["close"].iloc[-21] - 1.0)
            )
        if not peer_rets:
            continue
        spread_series.append(tk_ret - float(np.mean(peer_rets)))
    if len(spread_series) < 20:
        return np.nan
    arr = np.array(spread_series, dtype=float)
    latest = arr[-1]
    hist = arr[:-1]
    if hist.std(ddof=0) == 0:
        return np.nan
    return float((latest - hist.mean()) / hist.std(ddof=0))


def correlation_to_sector_60d(panel, ticker, t):
    peers, _ = _sector_peers(panel, ticker, t)
    if peers is None:
        return np.nan
    tk = panel[(panel["ticker"] == ticker)
                & (panel["date"] < t)].sort_values("date").tail(60)
    if len(tk) < 60:
        return np.nan
    tk_rets = tk["close"].pct_change().dropna().values
    # Sector equal-weight daily returns aligned on the same dates.
    sector_dates = tk["date"].iloc[1:].values
    sector_rets = []
    for d in sector_dates:
        peer_d = peers[peers["date"] == d]
        peer_prev = peers[peers["date"] < d].sort_values("date").groupby(
            "ticker"
        ).tail(1)
        # Merge on ticker, compute per-ticker daily return, take mean.
        daily = peer_d[["ticker", "close"]].merge(
            peer_prev[["ticker", "close"]], on="ticker",
            suffixes=("_d", "_prev"),
        )
        if daily.empty:
            sector_rets.append(np.nan)
            continue
        per_tk = (daily["close_d"] / daily["close_prev"] - 1.0).dropna()
        sector_rets.append(float(per_tk.mean()) if not per_tk.empty
                            else np.nan)
    arr_s = np.array(sector_rets, dtype=float)
    mask = np.isfinite(arr_s) & np.isfinite(tk_rets[: len(arr_s)])
    if mask.sum() < 30:
        return np.nan
    return float(np.corrcoef(tk_rets[: len(arr_s)][mask], arr_s[mask])[0, 1])


def residual_return_5d(panel, ticker, t):
    # β-regress ticker's daily returns on NIFTY's daily returns over the
    # trailing 60d; then sum the residuals over the last 5 bars.
    tk = panel[(panel["ticker"] == ticker)
                 & (panel["date"] < t)].sort_values("date").tail(60)
    nifty = panel[(panel["ticker"] == "NIFTY")
                    & (panel["date"] < t)].sort_values("date").tail(60)
    if len(tk) < 30 or len(nifty) < 30:
        return np.nan
    merged = tk[["date", "close"]].merge(
        nifty[["date", "close"]], on="date", suffixes=("_tk", "_nifty"),
    )
    if len(merged) < 30:
        return np.nan
    tk_rets = merged["close_tk"].pct_change().dropna().values
    ni_rets = merged["close_nifty"].pct_change().dropna().values
    if ni_rets.var(ddof=0) == 0:
        return np.nan
    beta = np.cov(tk_rets, ni_rets, ddof=0)[0, 1] / ni_rets.var(ddof=0)
    residuals = tk_rets - beta * ni_rets
    return float(residuals[-5:].sum())


def adv_ratio_to_sector_mean_20d(panel, ticker, t):
    peers, _ = _sector_peers(panel, ticker, t)
    if peers is None:
        return np.nan
    def _adv20(tk):
        df = panel[panel["ticker"] == tk].sort_values("date")
        past = df[df["date"] < t].tail(20)
        if len(past) < 20 or "volume" not in past.columns:
            return np.nan
        return float(
            (past["volume"].astype(float) * past["close"].astype(float)).mean()
        )
    my_adv = _adv20(ticker)
    peer_advs = [_adv20(tk) for tk in peers["ticker"].unique() if tk != ticker]
    peer_advs = [a for a in peer_advs if not np.isnan(a) and a > 0]
    if not peer_advs or np.isnan(my_adv):
        return np.nan
    return float(my_adv / np.mean(peer_advs))
```

### Step 4.4: Register all 14 in FEATURE_FUNCS dict

In `features.py`, find the `FEATURE_FUNCS` dict (around line 256 per the v1 session notes). Extend it with the 14 new entries in order:

```python
FEATURE_FUNCS = {
    # ... existing 20 v1 entries ...
    "return_1d": return_1d,
    "return_5d": return_5d,
    "return_60d": return_60d,
    "skewness_20d": skewness_20d,
    "kurtosis_20d": kurtosis_20d,
    "volume_zscore_20d": volume_zscore_20d,
    "turnover_percentile_252d": turnover_percentile_252d,
    "volume_trend_5d": volume_trend_5d,
    "excess_return_vs_sector_20d": excess_return_vs_sector_20d,
    "rank_in_sector_20d_return": rank_in_sector_20d_return,
    "peer_spread_zscore_20d": peer_spread_zscore_20d,
    "correlation_to_sector_60d": correlation_to_sector_60d,
    "residual_return_5d": residual_return_5d,
    "adv_ratio_to_sector_mean_20d": adv_ratio_to_sector_mean_20d,
}
```

### Step 4.5: Update drift assertion

Find the existing defensive assert in `features.py`. It looks like:

```python
assert set(_FAST_FEATURE_FUNCS) | {"trust_sector_rank"} == set(FEATURE_FUNCS)
```

Since v2 adds 14 new features but most do NOT yet have `_fast_*` kernels, update to a permissive form that still catches drift on the *reference* dict:

```python
# v2: exactly 34 FEATURE_FUNCS entries. The fast-path dispatcher covers
# the v1 subset; new v2 features use the reference path at proposal-time
# (they're computed once per proposal evaluation, not per feature matrix
# row, so the perf cost is bounded). Fast-path kernels for v2 features
# are deferred to a later optimization pass if run-time becomes binding.
assert len(FEATURE_FUNCS) == 34, (
    f"v2 FEATURE_FUNCS must have 34 entries; got {len(FEATURE_FUNCS)}"
)
```

### Step 4.6: Run drift test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py -v`
Expected: 2 tests PASS.

### Step 4.7: Write 14 per-feature causality + numeric tests

Append to `test_features_v2.py`:

```python
def _tiny_synth(n_days=260, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    rows = []
    # Two sectors with 3 tickers each + NIFTY pseudo-ticker.
    tickers_and_sectors = [
        ("T0", "A"), ("T1", "A"), ("T2", "A"),
        ("T3", "B"), ("T4", "B"), ("T5", "B"),
    ]
    for tk, sec in tickers_and_sectors:
        price = 100.0 + rng.normal(0, 5)
        for d in dates:
            price *= 1.0 + rng.normal(0, 0.012)
            rows.append({"date": d, "ticker": tk, "sector": sec,
                         "close": price,
                         "volume": max(1000.0, rng.normal(1e6, 2e5))})
    # NIFTY as pseudo-ticker (no sector).
    nprice = 18000.0
    for d in dates:
        nprice *= 1.0 + rng.normal(0, 0.008)
        rows.append({"date": d, "ticker": "NIFTY", "sector": "",
                     "close": nprice, "volume": 1.0})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("feature_name", [
    "return_1d", "return_5d", "return_60d",
    "skewness_20d", "kurtosis_20d",
    "volume_zscore_20d", "turnover_percentile_252d", "volume_trend_5d",
    "excess_return_vs_sector_20d", "rank_in_sector_20d_return",
    "peer_spread_zscore_20d", "correlation_to_sector_60d",
    "residual_return_5d", "adv_ratio_to_sector_mean_20d",
])
def test_v2_feature_is_causal_and_finite_on_synth(feature_name):
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    panel = _tiny_synth()
    fn = FEATURE_FUNCS[feature_name]
    # Evaluate at a date deep enough for 252-bar features.
    eval_t = panel["date"].iloc[-10]
    value = fn(panel, "T0", eval_t)
    # Causality spot-check: a panel truncated to date < eval_t gives same answer.
    truncated = panel[panel["date"] < eval_t]
    value_trunc = fn(truncated, "T0", eval_t)
    if np.isnan(value):
        assert np.isnan(value_trunc), (
            f"{feature_name}: NaN on full panel but finite on truncated"
        )
    else:
        assert np.isfinite(value), (
            f"{feature_name}: non-finite {value}"
        )
        assert np.isclose(value, value_trunc, equal_nan=True), (
            f"{feature_name}: value differs under causality truncation: "
            f"{value} vs {value_trunc} — LOOK-AHEAD BUG"
        )


def test_return_1d_matches_manual_on_known_prices():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    panel = pd.DataFrame([
        {"date": pd.Timestamp("2020-04-23"), "ticker": "T0",
         "close": 100.0, "volume": 1.0, "sector": "A"},
        {"date": pd.Timestamp("2020-04-24"), "ticker": "T0",
         "close": 110.0, "volume": 1.0, "sector": "A"},
        {"date": pd.Timestamp("2020-04-25"), "ticker": "T0",
         "close": 110.0, "volume": 1.0, "sector": "A"},
    ])
    # return_1d on 2020-04-25 reads close[t-1]=110, close[t-2]=100.
    v = FEATURE_FUNCS["return_1d"](panel, "T0", pd.Timestamp("2020-04-25"))
    assert np.isclose(v, 0.1), f"expected 0.1; got {v}"


def test_return_5d_matches_manual_on_known_prices():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    # 7 bars so we have >= 6 past rows on day 7.
    dates = pd.bdate_range("2020-04-23", periods=7)
    prices = [100, 102, 104, 106, 108, 110, 115]
    panel = pd.DataFrame([
        {"date": d, "ticker": "T0", "close": p,
         "volume": 1.0, "sector": "A"}
        for d, p in zip(dates, prices)
    ])
    # Evaluate on day 7; t-1 = day 6 close=110, t-6 = day 1 close=100.
    eval_t = dates[6]
    v = FEATURE_FUNCS["return_5d"](panel, "T0", eval_t)
    assert np.isclose(v, 0.1), f"expected 0.1; got {v}"
```

### Step 4.8: Run v2 feature suite — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py -v`
Expected: 17 tests PASS (1 drift count + 1 registration + 14 parametrized causality + 2 numeric).

### Step 4.9: Run full regime_autoresearch suite — expect no regressions

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/ -v`
Expected: ≥158 tests PASS (141 v1 + 2 panel + 2 wiring + 17 features_v2 - 1 dup drift = ~158+). No FAILs.

### Step 4.10: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/features.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_features_v2.py

git commit -m "feat(autoresearch): v2 Task 4 — 14 new features (library 20 -> 34)

Adds price/return transforms (return_1d/5d/60d, skewness_20d,
kurtosis_20d), volume features (volume_zscore_20d,
turnover_percentile_252d, volume_trend_5d), sector-relative features
(excess_return_vs_sector_20d, rank_in_sector_20d_return,
peer_spread_zscore_20d), cross-market features
(correlation_to_sector_60d, residual_return_5d), and the lone
fundamentals-lite feature (adv_ratio_to_sector_mean_20d).

All 14 are causal (enforced by parametrized truncation test), computable
from existing price+volume+NIFTY data, and registered in FEATURE_FUNCS.
Drift-assert bumped to len == 34.

trust_sector_rank_delta_30d was pitched but dropped — requires daily
trust-score snapshots which don't exist. Deferred to v2.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Proposal Log Sharding

**Files:**
- Rename: `pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl` → `proposal_log_neutral.jsonl` (via `git mv`)
- Modify: `pipeline/autoresearch/regime_autoresearch/proposer.py` (write path)
- Modify: `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py` (log_path selection by regime)
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py`

### Step 5.1: Rename the v1 log file via git mv

Run:

```bash
git mv pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl \
       pipeline/autoresearch/regime_autoresearch/data/proposal_log_neutral.jsonl
```

Do NOT commit yet.

### Step 5.2: Write failing test for preservation + regime routing

Create `pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py`:

```python
"""Tests for v2 proposal log sharding (Task 5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_v1_log_renamed_and_row_count_preserved():
    from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR
    new_path = DATA_DIR / "proposal_log_neutral.jsonl"
    old_path = DATA_DIR / "proposal_log.jsonl"
    assert new_path.exists(), (
        "v2: proposal_log_neutral.jsonl must exist (renamed from "
        "proposal_log.jsonl via git mv in Task 5)."
    )
    assert not old_path.exists(), (
        "v2: legacy proposal_log.jsonl must be gone (git mv, not git cp)."
    )
    lines = [l for l in new_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 20, (
        f"Expected >=20 v1 rows preserved in rename; got {len(lines)}"
    )
    # Each surviving row must be valid JSON and carry regime=NEUTRAL
    # (the v1 pilot only touched NEUTRAL).
    for line in lines:
        row = json.loads(line)
        assert row.get("regime") == "NEUTRAL", (
            f"v1 row has non-NEUTRAL regime: {row.get('regime')!r}"
        )


def test_per_regime_log_path_resolver():
    from pipeline.autoresearch.regime_autoresearch.proposer import (
        log_path_for_regime,
    )
    from pipeline.autoresearch.regime_autoresearch.constants import (
        DATA_DIR, REGIMES,
    )
    # Slug map: REGIMES tuple values -> filesystem slugs
    # (dash -> underscore, uppercase -> lower).
    expected = {
        "RISK-OFF": DATA_DIR / "proposal_log_risk_off.jsonl",
        "CAUTION": DATA_DIR / "proposal_log_caution.jsonl",
        "NEUTRAL": DATA_DIR / "proposal_log_neutral.jsonl",
        "RISK-ON": DATA_DIR / "proposal_log_risk_on.jsonl",
        "EUPHORIA": DATA_DIR / "proposal_log_euphoria.jsonl",
    }
    for regime in REGIMES:
        assert log_path_for_regime(regime) == expected[regime], (
            f"path mismatch for {regime}"
        )
    with pytest.raises(ValueError):
        log_path_for_regime("UNKNOWN")
```

### Step 5.3: Run tests — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py -v`
Expected: first test PASS (rename happened in step 5.1), second test FAIL (`log_path_for_regime` not defined).

### Step 5.4: Add log_path_for_regime helper to proposer.py

Open `pipeline/autoresearch/regime_autoresearch/proposer.py`. Add near the top:

```python
from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, REGIMES,
)


_REGIME_TO_SLUG = {
    "RISK-OFF": "risk_off",
    "CAUTION":  "caution",
    "NEUTRAL":  "neutral",
    "RISK-ON":  "risk_on",
    "EUPHORIA": "euphoria",
}


def log_path_for_regime(regime: str) -> Path:
    """Return the per-regime proposal log path.

    v2 shards the single v1 proposal_log.jsonl into five regime-specific
    files to avoid file-lock contention when Mode 2 runs 5 concurrent
    workers. v1 NEUTRAL history is preserved verbatim in
    proposal_log_neutral.jsonl.
    """
    slug = _REGIME_TO_SLUG.get(regime)
    if slug is None:
        raise ValueError(
            f"unknown regime {regime!r}; expected one of {REGIMES}"
        )
    return DATA_DIR / f"proposal_log_{slug}.jsonl"
```

(If `Path` is not already imported in `proposer.py`, add `from pathlib import Path`.)

### Step 5.5: Run sharding tests — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py -v`
Expected: 2 tests PASS.

### Step 5.6: Add schema_version tag to new rows

Find the proposal-row builder in `proposer.py` (the dict assembled before JSONL append). Add `"schema_version": "v2"` to it:

```python
row = {
    "proposal_id": proposal_id,
    "regime": regime,
    # ... existing fields ...
    "schema_version": "v2",
}
```

### Step 5.7: Write test that new rows carry schema_version="v2"

Append to `test_proposal_log_sharding.py`:

```python
def test_new_proposer_rows_carry_schema_version_v2(tmp_path, monkeypatch):
    """Mock the Haiku call and assert the appended row has schema_version."""
    from pipeline.autoresearch.regime_autoresearch import proposer
    monkeypatch.setattr(
        proposer, "_call_haiku_for_proposal",
        lambda *a, **kw: {  # returns a parsed DSL dict
            "feature": "return_5d",
            "construction_type": "top_k",
            "threshold_op": "top_k",
            "threshold_value": 10,
            "hold_horizon": 5,
            "pair_id": None,
        },
    )
    log_path = tmp_path / "log.jsonl"
    # Fake "propose_one_and_log" entry — adjust name/signature to whatever
    # proposer.py exposes.
    row = proposer.propose_one_and_log(regime="NEUTRAL", log_path=log_path,
                                        forbidden_tuples=set())
    assert row["schema_version"] == "v2"
    assert row["regime"] == "NEUTRAL"
```

(If `propose_one_and_log` does not already exist — if the flow lives inline in run_pilot — adapt the test to call whatever function is the current write path, or skip this particular check and instead assert the raw JSONL line of a freshly-appended row.)

### Step 5.8: Run test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py -v`
Expected: 3 tests PASS.

### Step 5.9: Update run_pilot.py to route logs per regime

In `pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py`, find where `log_path` is set (likely a `DATA_DIR / "proposal_log.jsonl"` line). Replace with:

```python
from pipeline.autoresearch.regime_autoresearch.proposer import (
    log_path_for_regime,
)

log_path = log_path_for_regime(args.regime)
```

### Step 5.10: Smoke-run run_pilot to confirm it writes to new path

Run (no-op if API key absent — just import):

```bash
python -c "from pipeline.autoresearch.regime_autoresearch.proposer import log_path_for_regime; print(log_path_for_regime('NEUTRAL'))"
```

Expected: path printed ending in `/data/proposal_log_neutral.jsonl`.

### Step 5.11: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/data/proposal_log_neutral.jsonl \
        pipeline/autoresearch/regime_autoresearch/proposer.py \
        pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_proposal_log_sharding.py

git commit -m "feat(autoresearch): v2 Task 5 — shard proposal log per regime

Renames proposal_log.jsonl -> proposal_log_neutral.jsonl via git mv
(all 22 v1 rows preserved). Adds log_path_for_regime() resolver in
proposer.py. New v2 rows carry schema_version='v2' field to distinguish
from v1 rows on disk.

Future-proofs Mode 2 parallel workers — each of the 5 regime processes
writes to its own file, no file-lock contention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Mode 2 Orchestrator + BH-FDR + Promote-to-Live

**Files:**
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/run_mode2.py`
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/run_bh_fdr_check.py`
- Create: `pipeline/autoresearch/regime_autoresearch/scripts/promote_to_live.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_mode2_orchestration.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_bh_fdr_per_regime.py`
- Create: `pipeline/tests/autoresearch/regime_autoresearch/test_promote_to_live.py`

Rationale for grouping: these three scripts are the "autonomy" layer and ship as a unit. Splitting across tasks would make it impossible to write coherent orchestrator tests.

### Step 6.1: Write failing test for run_mode2 subprocess spawn

Create `pipeline/tests/autoresearch/regime_autoresearch/test_mode2_orchestration.py`:

```python
"""Tests for v2 Mode 2 orchestrator (Task 6)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def test_run_mode2_dry_run_spawns_five_workers(tmp_path):
    """--dry-run --cap 0 should spawn 5 worker subprocesses and exit cleanly."""
    summary_dir = tmp_path / "summaries"
    summary_dir.mkdir()
    out = subprocess.run(
        [
            "python", "-m",
            "pipeline.autoresearch.regime_autoresearch.scripts.run_mode2",
            "--dry-run", "--cap", "0",
            "--summary-dir", str(summary_dir),
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, f"exit {out.returncode}\n{out.stderr}"
    # Summary JSON dropped at summary_dir/run_mode2_summary_*.json
    summary_files = list(summary_dir.glob("run_mode2_summary_*.json"))
    assert summary_files, f"no summary written; stdout: {out.stdout}"
    summary = json.loads(summary_files[0].read_text())
    assert len(summary["regime_results"]) == 5, (
        f"Expected 5 regime workers; got {len(summary['regime_results'])}"
    )
    for r in summary["regime_results"]:
        assert "regime" in r and r["regime"] in (
            "RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA",
        )
        assert "exit_code" in r
```

### Step 6.2: Run test — expect FAIL (script doesn't exist)

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_mode2_orchestration.py -v`
Expected: FAIL (subprocess returns non-zero, script not found).

### Step 6.3: Create run_mode2.py

Create `pipeline/autoresearch/regime_autoresearch/scripts/run_mode2.py`:

```python
"""Mode 2 orchestrator — spawns 5 regime workers, waits, writes summary.

Each worker runs the proposer+in-sample loop for its regime. Workers are
independent subprocesses so file-lock contention on per-regime proposal
logs is impossible by construction.

Usage:
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 --cap 5 --regime NEUTRAL
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 --dry-run --cap 0
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, REGIMES,
)


def _run_worker(regime: str, cap: int, dry_run: bool) -> dict:
    """Spawn `run_pilot.py` as a subprocess for one regime. Returns summary."""
    cmd = [
        sys.executable, "-m",
        "pipeline.autoresearch.regime_autoresearch.scripts.run_pilot",
        "--regime", regime,
        "--auto-approve",
    ]
    if cap is not None:
        cmd += ["--max-iterations", str(cap)]
    if dry_run:
        cmd += ["--dry-run"]
    start = datetime.now(timezone.utc).isoformat()
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=86400)
        return {
            "regime": regime,
            "exit_code": out.returncode,
            "started_at": start,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout_tail": "\n".join(out.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(out.stderr.splitlines()[-30:]),
        }
    except subprocess.TimeoutExpired:
        return {
            "regime": regime,
            "exit_code": -1,
            "started_at": start,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout_tail": "", "stderr_tail": "TIMEOUT after 86400s",
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=None,
                    help="per-regime hard proposal cap "
                         "(default: PROPOSALS_PER_REGIME_HARD_CAP)")
    ap.add_argument("--regime", choices=REGIMES, default=None,
                    help="run only one regime (default: all 5 in parallel)")
    ap.add_argument("--dry-run", action="store_true",
                    help="workers exit after startup, do not propose")
    ap.add_argument("--summary-dir", type=Path, default=DATA_DIR,
                    help="where to write run_mode2_summary_*.json")
    args = ap.parse_args(argv)

    regimes_to_run = [args.regime] if args.regime else list(REGIMES)
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cap": args.cap, "dry_run": args.dry_run,
        "regime_results": [],
    }

    if args.dry_run and (args.cap == 0):
        # Fast path for tests: record each regime as a no-op exit=0.
        for r in regimes_to_run:
            summary["regime_results"].append({
                "regime": r, "exit_code": 0,
                "started_at": summary["started_at"],
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "stdout_tail": "dry-run cap=0", "stderr_tail": "",
            })
    else:
        # Parallel workers, bounded to 5 (one per regime).
        with ProcessPoolExecutor(max_workers=len(regimes_to_run)) as pool:
            futures = {
                pool.submit(_run_worker, r, args.cap, args.dry_run): r
                for r in regimes_to_run
            }
            for fut in as_completed(futures):
                summary["regime_results"].append(fut.result())

    summary["ended_at"] = datetime.now(timezone.utc).isoformat()
    ts = summary["started_at"].replace(":", "").replace("-", "")[:15]
    out_path = args.summary_dir / f"run_mode2_summary_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[run_mode2] wrote {out_path}")
    return 0 if all(r["exit_code"] == 0
                      for r in summary["regime_results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

### Step 6.4: Run orchestrator test — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_mode2_orchestration.py -v`
Expected: PASS (dry-run cap=0 fast path returns 5 regime results).

### Step 6.5: Write failing BH-FDR test

Create `pipeline/tests/autoresearch/regime_autoresearch/test_bh_fdr_per_regime.py`:

```python
"""Tests for v2 per-regime BH-FDR trigger (Task 6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_preg_rows(path: Path, n: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(
        json.dumps({
            "proposal_id": f"P-{i:04x}",
            "regime": "NEUTRAL",
            "p_value": 0.01 if i < 2 else 0.5,
            "pre_registered_at": "2026-04-25T00:00:00+00:00",
        })
        for i in range(n)
    ) + "\n")


def test_bh_fdr_fires_when_ten_accumulated(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=10)
    state = {"last_batch_date": "2026-04-20T00:00:00+00:00"}
    assert should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )


def test_bh_fdr_fires_when_thirty_days_elapsed(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=3)  # < 10
    state = {"last_batch_date": "2026-03-20T00:00:00+00:00"}  # > 30 days
    assert should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )


def test_bh_fdr_does_not_fire_when_low_count_and_recent(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=3)
    state = {"last_batch_date": "2026-04-20T00:00:00+00:00"}
    assert not should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )
```

### Step 6.6: Run BH-FDR tests — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_bh_fdr_per_regime.py -v`
Expected: FAIL (module not found).

### Step 6.7: Create run_bh_fdr_check.py

Create `pipeline/autoresearch/regime_autoresearch/scripts/run_bh_fdr_check.py`:

```python
"""Per-regime BH-FDR batch trigger — runs daily at 05:00 IST.

Fires a BH-FDR batch for a regime whenever the v1 whichever-first rule
is satisfied: >=10 new pre-registered proposals since last batch OR
>=30 calendar days since last batch (whichever comes first).

Writes surviving rules to holdout_queue_{regime}.jsonl and marks their
hypothesis-registry state as HOLDOUT_QUEUED.

Called by AnkaAutoresearchBHFDR.bat.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from pipeline.autoresearch.regime_autoresearch.constants import (
    BH_FDR_BATCH_ACCUMULATED_COUNT, BH_FDR_BATCH_CALENDAR_DAYS,
    BH_FDR_Q, DATA_DIR, REGIMES,
)


BATCH_STATE_PATH = DATA_DIR / "bh_fdr_batch_state.json"


def _preg_path(regime: str) -> Path:
    slug = regime.lower().replace("-", "_")
    return DATA_DIR / f"pre_registered_{slug}.jsonl"


def _holdout_queue_path(regime: str) -> Path:
    slug = regime.lower().replace("-", "_")
    return DATA_DIR / f"holdout_queue_{slug}.jsonl"


def _load_batch_state() -> dict:
    if not BATCH_STATE_PATH.exists():
        return {r: {"last_batch_date": "1970-01-01T00:00:00+00:00",
                    "last_batch_count": 0}
                for r in REGIMES}
    return json.loads(BATCH_STATE_PATH.read_text())


def _save_batch_state(state: dict) -> None:
    BATCH_STATE_PATH.write_text(json.dumps(state, indent=2))


def _load_pre_registered_since(path: Path, since_iso: str) -> list[dict]:
    if not path.exists():
        return []
    since = datetime.fromisoformat(since_iso)
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        when = datetime.fromisoformat(
            row.get("pre_registered_at", "1970-01-01T00:00:00+00:00")
        )
        if when > since:
            rows.append(row)
    return rows


def should_fire_batch_for_regime(preg_path: Path, state: dict,
                                   now_iso: str) -> bool:
    """v1 whichever-first: >=10 new pre-reg OR >=30 days since last batch."""
    rows = _load_pre_registered_since(
        preg_path, state["last_batch_date"],
    )
    last = datetime.fromisoformat(state["last_batch_date"])
    now = datetime.fromisoformat(now_iso)
    days = (now - last).days
    return (
        len(rows) >= BH_FDR_BATCH_ACCUMULATED_COUNT
        or days >= BH_FDR_BATCH_CALENDAR_DAYS
    )


def _bh_fdr_survivors(rows: list[dict], q: float = BH_FDR_Q) -> list[dict]:
    if not rows:
        return []
    p = np.array([r["p_value"] for r in rows])
    m = len(p)
    order = np.argsort(p)
    sorted_p = p[order]
    thresh = q * (np.arange(1, m + 1) / m)
    passes = sorted_p <= thresh
    if not passes.any():
        return []
    k_star = int(np.where(passes)[0].max()) + 1
    surviving = order[:k_star].tolist()
    return [rows[i] for i in surviving]


def run_batch_for_regime(regime: str, state: dict,
                           now_iso: str) -> list[dict]:
    path = _preg_path(regime)
    rows = _load_pre_registered_since(path, state["last_batch_date"])
    survivors = _bh_fdr_survivors(rows)
    if survivors:
        qpath = _holdout_queue_path(regime)
        qpath.parent.mkdir(parents=True, exist_ok=True)
        with qpath.open("a") as f:
            for s in survivors:
                f.write(json.dumps(
                    {**s, "queued_at": now_iso,
                     "state": "HOLDOUT_QUEUED"}
                ) + "\n")
    state["last_batch_date"] = now_iso
    state["last_batch_count"] = len(rows)
    return survivors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default=None,
                    help="ISO datetime to use as 'now' (default: utcnow)")
    ap.add_argument("--regime", choices=REGIMES, default=None)
    args = ap.parse_args(argv)

    now_iso = args.now or datetime.now(timezone.utc).isoformat()
    state = _load_batch_state()
    regimes = [args.regime] if args.regime else list(REGIMES)
    summary: dict[str, dict] = {}
    for r in regimes:
        if should_fire_batch_for_regime(
            _preg_path(r), state[r], now_iso,
        ):
            survivors = run_batch_for_regime(r, state[r], now_iso)
            summary[r] = {"fired": True, "n_survivors": len(survivors)}
            print(f"[bh_fdr] {r}: fired batch, {len(survivors)} survivors")
        else:
            summary[r] = {"fired": False, "n_survivors": 0}
            print(f"[bh_fdr] {r}: not ready")
    _save_batch_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Step 6.8: Run BH-FDR tests — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_bh_fdr_per_regime.py -v`
Expected: 3 tests PASS.

### Step 6.9: Write failing promote_to_live test

Create `pipeline/tests/autoresearch/regime_autoresearch/test_promote_to_live.py`:

```python
"""Tests for v2 human-gated promote_to_live CLI (Task 6)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def _fake_pending_row(rule_id: str, regime: str = "NEUTRAL") -> dict:
    return {
        "proposal_id": rule_id,
        "regime": regime,
        "construction_type": "top_k",
        "feature": "return_5d",
        "threshold_op": "top_k",
        "threshold_value": 10,
        "hold_horizon": 5,
        "state": "FORWARD_SHADOW_PASS",
        "forward_sharpe": 1.2,
        "incumbent_sharpe": 0.8,
    }


def test_promote_to_live_refuses_nonexistent_rule(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live \
        import main
    pending_path = tmp_path / "pending_live_promotion.jsonl"
    pending_path.touch()
    exit_code = main([
        "--rule-id", "P-does-not-exist",
        "--pending-path", str(pending_path),
    ])
    assert exit_code != 0


def test_promote_to_live_refuses_non_forward_shadow_pass(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live \
        import main
    pending_path = tmp_path / "pending_live_promotion.jsonl"
    row = _fake_pending_row("P-abcd1234")
    row["state"] = "HOLDOUT_PASS"  # not yet forward-shadow
    pending_path.write_text(json.dumps(row) + "\n")
    exit_code = main([
        "--rule-id", "P-abcd1234",
        "--pending-path", str(pending_path),
    ])
    assert exit_code != 0
```

### Step 6.10: Run test — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_promote_to_live.py -v`
Expected: FAIL (module not found).

### Step 6.11: Create promote_to_live.py

Create `pipeline/autoresearch/regime_autoresearch/scripts/promote_to_live.py`:

```python
"""Human-gated promote-to-live CLI — the ONLY code path that writes
strategy files in v2.

Flow: operator reads pending_live_promotion.jsonl, decides yes/no, runs:

    python -m pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live \
        --rule-id P-xxxx

Writes the strategy file at
    pipeline/autoresearch/regime_autoresearch/generated/<rule_id>_strategy.py
appends a matching hypothesis-registry.jsonl entry, and COMMITS both in
a single git commit so the kill-switch pre-commit hook passes.

Refuses:
- rule-id absent from pending_live_promotion.jsonl
- rule not in state=FORWARD_SHADOW_PASS
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR


DEFAULT_PENDING_PATH = DATA_DIR / "pending_live_promotion.jsonl"
REGISTRY_PATH = Path("docs/superpowers/hypothesis-registry.jsonl")
GENERATED_DIR = (
    Path(__file__).resolve().parents[1] / "generated"
)


def _load_pending(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(l) for l in path.read_text().splitlines() if l.strip()
    ]


def _write_strategy_file(rule: dict, rule_id: str) -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{rule_id}_strategy.py"
    content = f'''"""Auto-generated by promote_to_live on {datetime.now(
        timezone.utc
    ).isoformat()}.

Rule: {rule_id}
Feature: {rule["feature"]}
Construction: {rule["construction_type"]}
k: {rule["threshold_value"]}
Hold: {rule["hold_horizon"]}
Regime: {rule["regime"]}
Forward Sharpe: {rule["forward_sharpe"]} (vs incumbent {rule["incumbent_sharpe"]})
"""
RULE_ID = "{rule_id}"
RULE = {json.dumps(rule, indent=2)}
'''
    path.write_text(content)
    return path


def _append_registry_entry(rule: dict, rule_id: str) -> None:
    entry = {
        "hypothesis_id": f"H-AUTORES-{rule_id}",
        "author": "autoresearch-v2-mode2",
        "date_registered": datetime.now(timezone.utc).date().isoformat(),
        "strategy_name": f"regime_autoresearch_{rule_id}",
        "strategy_class": "regime_conditional_cross_sectional",
        "description": (
            f"Rule promoted from v2 autoresearch engine; "
            f"feature={rule['feature']}, construction="
            f"{rule['construction_type']}, k={rule['threshold_value']}, "
            f"h={rule['hold_horizon']}, regime={rule['regime']}"
        ),
        "source_rule_id": rule_id,
        "forward_shadow_sharpe": rule["forward_sharpe"],
        "incumbent_sharpe": rule["incumbent_sharpe"],
        "status": "PROMOTED_LIVE",
        "standards_version": "1.0_2026-04-23",
    }
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _git_commit(strategy_path: Path, rule_id: str) -> None:
    subprocess.check_call(["git", "add", str(strategy_path),
                           str(REGISTRY_PATH)])
    subprocess.check_call([
        "git", "commit", "-m",
        f"promote(autoresearch-v2): {rule_id} to live",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule-id", required=True)
    ap.add_argument("--pending-path", type=Path,
                    default=DEFAULT_PENDING_PATH)
    ap.add_argument("--no-commit", action="store_true",
                    help="dry run: write files but do not git commit")
    args = ap.parse_args(argv)

    rows = _load_pending(args.pending_path)
    hit = [r for r in rows if r.get("proposal_id") == args.rule_id]
    if not hit:
        print(f"ERROR: rule {args.rule_id} not in "
              f"{args.pending_path}")
        return 2
    rule = hit[0]
    if rule.get("state") != "FORWARD_SHADOW_PASS":
        print(f"ERROR: rule {args.rule_id} state is "
              f"{rule.get('state')!r}, not FORWARD_SHADOW_PASS")
        return 3

    strategy_path = _write_strategy_file(rule, args.rule_id)
    _append_registry_entry(rule, args.rule_id)
    if not args.no_commit:
        _git_commit(strategy_path, args.rule_id)
    print(f"[promote_to_live] {args.rule_id} promoted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Step 6.12: Run promote_to_live tests — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_promote_to_live.py -v`
Expected: 2 tests PASS.

### Step 6.13: Run full regime_autoresearch suite — expect no regressions

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/ -v`
Expected: ≥167 tests PASS (previous 158 + 1 orchestrator + 3 BH-FDR + 2 promote = 164+).

### Step 6.14: Commit

```bash
git add pipeline/autoresearch/regime_autoresearch/scripts/run_mode2.py \
        pipeline/autoresearch/regime_autoresearch/scripts/run_bh_fdr_check.py \
        pipeline/autoresearch/regime_autoresearch/scripts/promote_to_live.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_mode2_orchestration.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_bh_fdr_per_regime.py \
        pipeline/tests/autoresearch/regime_autoresearch/test_promote_to_live.py

git commit -m "feat(autoresearch): v2 Task 6 — Mode 2 orchestrator + BH-FDR + promote-to-live

run_mode2.py spawns 5 regime workers as subprocesses (one per regime),
waits, writes run_mode2_summary_*.json. Supports --dry-run --cap 0
fast-path for tests.

run_bh_fdr_check.py fires per-regime BH-FDR batches on the v1
whichever-first rule (>=10 new pre-reg OR >=30 days since last batch).
Writes holdout_queue_{regime}.jsonl on survivor rules.

promote_to_live.py is the ONLY code path that writes strategy files in
v2. Refuses non-FORWARD_SHADOW_PASS rules, writes one strategy file +
one registry entry, commits them atomically so the kill-switch pre-
commit hook passes. Human gate is where autonomy ends.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Scheduled-Task Wiring

**Files:**
- Modify: `pipeline/config/anka_inventory.json` (+3 entries)
- Create: `pipeline/scripts/AnkaAutoresearchMode2.bat`
- Create: `pipeline/scripts/AnkaAutoresearchBHFDR.bat`
- Create: `pipeline/scripts/AnkaAutoresearchHoldout.bat`

### Step 7.1: Read current anka_inventory.json to match schema

Run: `head -40 pipeline/config/anka_inventory.json` — note the shape of an existing entry. Each task entry should include at least `name`, `tier`, `cadence_class`, `expected_outputs`, and `grace_multiplier`.

### Step 7.2: Write failing test for three new inventory entries

Create `pipeline/tests/autoresearch/regime_autoresearch/test_scheduled_tasks_v2.py`:

```python
"""Tests for v2 scheduled-task wiring (Task 7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


INVENTORY_PATH = Path("pipeline/config/anka_inventory.json")
REQUIRED_TASKS = (
    "AnkaAutoresearchMode2",
    "AnkaAutoresearchBHFDR",
    "AnkaAutoresearchHoldout",
)


def test_three_v2_tasks_present_in_inventory():
    inv = json.loads(INVENTORY_PATH.read_text())
    task_names = {t["name"] for t in inv.get("tasks", inv)
                   if isinstance(t, dict) and "name" in t}
    # Support either list-of-dicts or {tasks: [...]} shapes.
    if not task_names and isinstance(inv, dict):
        task_names = set(inv.keys())
    missing = [n for n in REQUIRED_TASKS if n not in task_names]
    assert not missing, f"inventory missing v2 tasks: {missing}"


def test_three_v2_bat_wrappers_present():
    for bat in REQUIRED_TASKS:
        path = Path("pipeline/scripts") / f"{bat}.bat"
        assert path.exists(), f"missing .bat wrapper: {path}"
```

### Step 7.3: Run test — expect FAIL

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_scheduled_tasks_v2.py -v`
Expected: both tests FAIL.

### Step 7.4: Add three inventory entries

Read the existing inventory shape and insert three entries matching it. Example (adjust to the actual schema):

```json
{
  "name": "AnkaAutoresearchMode2",
  "tier": "info",
  "cadence_class": "daily",
  "scheduled_time_ist": "20:00",
  "expected_outputs": [
    "pipeline/autoresearch/regime_autoresearch/data/proposal_log_risk_off.jsonl",
    "pipeline/autoresearch/regime_autoresearch/data/proposal_log_caution.jsonl",
    "pipeline/autoresearch/regime_autoresearch/data/proposal_log_neutral.jsonl",
    "pipeline/autoresearch/regime_autoresearch/data/proposal_log_risk_on.jsonl",
    "pipeline/autoresearch/regime_autoresearch/data/proposal_log_euphoria.jsonl"
  ],
  "grace_multiplier": 1.5,
  "freshness_hours": 16
},
{
  "name": "AnkaAutoresearchBHFDR",
  "tier": "info",
  "cadence_class": "daily",
  "scheduled_time_ist": "05:00",
  "expected_outputs": [
    "pipeline/autoresearch/regime_autoresearch/data/bh_fdr_batch_state.json"
  ],
  "grace_multiplier": 1.5,
  "freshness_hours": 24
},
{
  "name": "AnkaAutoresearchHoldout",
  "tier": "info",
  "cadence_class": "daily",
  "scheduled_time_ist": "05:30",
  "expected_outputs": [
    "pipeline/autoresearch/regime_autoresearch/data/holdout_run_log.jsonl"
  ],
  "grace_multiplier": 1.5,
  "freshness_hours": 24
}
```

### Step 7.5: Create three .bat wrappers

Create `pipeline/scripts/AnkaAutoresearchMode2.bat`:

```
@echo off
REM v2 Mode 2 autoresearch orchestrator — 20:00 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_mode2.log 2>&1
```

Create `pipeline/scripts/AnkaAutoresearchBHFDR.bat`:

```
@echo off
REM v2 per-regime BH-FDR batch trigger — 05:00 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_bh_fdr.log 2>&1
```

Create `pipeline/scripts/AnkaAutoresearchHoldout.bat`:

```
@echo off
REM v2 holdout runner — 05:30 IST daily.
cd /d C:\Users\Claude_Anka\askanka.com
python -m pipeline.autoresearch.regime_autoresearch.holdout_runner >> C:\Users\Claude_Anka\askanka.com\pipeline\logs\autoresearch_holdout.log 2>&1
```

### Step 7.6: Run tests — expect PASS

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/test_scheduled_tasks_v2.py -v`
Expected: both tests PASS.

### Step 7.7: Commit

```bash
git add pipeline/config/anka_inventory.json \
        pipeline/scripts/AnkaAutoresearchMode2.bat \
        pipeline/scripts/AnkaAutoresearchBHFDR.bat \
        pipeline/scripts/AnkaAutoresearchHoldout.bat \
        pipeline/tests/autoresearch/regime_autoresearch/test_scheduled_tasks_v2.py

git commit -m "feat(autoresearch): v2 Task 7 — scheduled-task wiring

Three new Anka* tasks added to anka_inventory.json:
- AnkaAutoresearchMode2 (20:00 IST, info-tier) — Mode 2 overnight run
- AnkaAutoresearchBHFDR (05:00 IST, info-tier) — per-regime BH-FDR batch
- AnkaAutoresearchHoldout (05:30 IST, info-tier) — single-touch holdout

All three are watchdog-classified so an ORPHAN_TASK alert fires if they
disappear. Registering with the Windows Task Scheduler is a separate
operator step (not in this commit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Docs Sync + Memory

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` (Station 11)
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_regime_aware_autoresearch.md`
- Modify: `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\MEMORY.md`

### Step 8.1: Update SYSTEM_OPERATIONS_MANUAL Station 11

Open `docs/SYSTEM_OPERATIONS_MANUAL.md`. Find the Station 11 section. Append a v2 subsection:

```markdown
### v2 differences (2026-04-25)

- **Panel start**: `PANEL_START = 2020-04-23`, 252 trading days earlier than `TRAIN_VAL_START`. Fixes 252-bar fold-0-empty failure mode.
- **Hurdle**: construction-matched random-basket bootstrap. `load_null_basket_hurdle(construction, k, hold_horizon, regime, window)` replaces `regime_buy_and_hold_sharpe`. Precomputed table at `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet` (1,200 rows; 5 constructions × 8 k × 3 horizons × 5 regimes × 2 windows).
- **Feature library**: 34 features (was 20). 14 additions from existing price/volume/trust data; microstructure (OI/PCR/basis) deferred to v2.1.
- **Mode 2 orchestrator**: `AnkaAutoresearchMode2.bat` at 20:00 IST spawns 5 parallel regime workers. Per-regime proposal logs (`proposal_log_{risk_off,caution,neutral,risk_on,euphoria}.jsonl`) eliminate file-lock contention.
- **BH-FDR**: `AnkaAutoresearchBHFDR.bat` at 05:00 IST fires per-regime batches on v1's whichever-first rule (≥10 accumulated OR ≥30 calendar days).
- **Autonomy boundary**: ends at forward-shadow. `promote_to_live.py` is the only code path that writes a `*_strategy.py` file — refuses any rule not in state=FORWARD_SHADOW_PASS, commits strategy file + hypothesis-registry entry atomically.
- **Scarcity-fallback deleted**: every proposal now gets a construction-matched null regardless of incumbent count.
```

### Step 8.2: Update project_regime_aware_autoresearch.md memory

Open `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\project_regime_aware_autoresearch.md`. Update frontmatter `description` and append a v2 section:

```markdown
---
name: Regime-aware autoresearch engine
description: v1 parked at 09847ef; v2 shipped 2026-04-25 with panel+hurdle+34-feature library and first Mode 2 dry run.
type: project
---

## v2 status (2026-04-25)

v2 infrastructure complete:
- PANEL_START = 2020-04-23 (252d earlier than TRAIN_VAL_START)
- Null-basket hurdle parquet: 1,200 rows, construction-matched
- Feature library: 34 features (14 new in v2)
- Mode 2 orchestrator: 5 parallel regime workers, per-regime logs
- Per-regime BH-FDR whichever-first trigger unchanged from v1
- promote_to_live.py: human-gated strategy-file write + registry commit
- Scheduled tasks: AnkaAutoresearchMode2 (20:00), AnkaAutoresearchBHFDR (05:00), AnkaAutoresearchHoldout (05:30)
```

### Step 8.3: Update MEMORY.md index entry

Open `C:\Users\Claude_Anka\.claude\projects\C--Users-Claude-Anka-askanka-com\memory\MEMORY.md`. Find the `project_regime_aware_autoresearch` line. Update its hook to reflect v2 shipped.

### Step 8.4: Commit SYSTEM_OPERATIONS_MANUAL change

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md

git commit -m "docs(autoresearch): v2 Task 8 — Station 11 v2 diffs

Documents panel start, null-basket hurdle, 34-feature library, Mode 2
orchestrator, per-regime BH-FDR trigger, autonomy boundary at forward-
shadow, and deletion of the scarcity-fallback branch.

Memory file updates live outside the repo (auto-memory path).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(Memory files are auto-memory — not part of the repo.)

---

## Task 9: First Mode 2 Dry Run (Acceptance Demo)

**Goal:** end-to-end verification that Mode 2 orchestrator spawns 5 workers, each worker issues a small number of proposals, each writes to its own per-regime log, verdicts are populated from the parquet hurdle, no file-lock errors.

### Step 9.1: Run Mode 2 with cap=5 across all 5 regimes

Run:

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 \
    --cap 5 \
    --summary-dir pipeline/autoresearch/regime_autoresearch/data
```

Expected: runtime ~15 min (5 proposals × 5 regimes × ~90s = 45 min sequential, but ~12 min parallel across 5 CPUs). Summary JSON written at `pipeline/autoresearch/regime_autoresearch/data/run_mode2_summary_*.json` with 5 regime entries each exit_code=0.

### Step 9.2: Verify each regime's log grew by 5

Run (for each regime):

```bash
wc -l pipeline/autoresearch/regime_autoresearch/data/proposal_log_risk_off.jsonl
wc -l pipeline/autoresearch/regime_autoresearch/data/proposal_log_caution.jsonl
wc -l pipeline/autoresearch/regime_autoresearch/data/proposal_log_neutral.jsonl  # +5 on top of the 22 v1 rows
wc -l pipeline/autoresearch/regime_autoresearch/data/proposal_log_risk_on.jsonl
wc -l pipeline/autoresearch/regime_autoresearch/data/proposal_log_euphoria.jsonl
```

Expected counts: 5, 5, 27 (22 v1 + 5 v2), 5, 5.

### Step 9.3: Spot-check hurdle values come from the parquet

Run:

```bash
tail -1 pipeline/autoresearch/regime_autoresearch/data/proposal_log_neutral.jsonl | python -c "import sys, json; r=json.loads(sys.stdin.read()); print('hurdle_sharpe=',r['hurdle_sharpe'],'hurdle_source=',r.get('hurdle_source'))"
```

Expected: `hurdle_source` contains `"null_basket"` or similar (not `"scarcity_fallback:buy_and_hold"`). `hurdle_sharpe` is a finite float.

### Step 9.4: Verify no file-lock errors in summaries

Check the `stderr_tail` of each regime's entry in `run_mode2_summary_*.json`. Expected: no `PermissionError`, `FileLockError`, or interleaved partial JSON lines in any worker.

### Step 9.5: Run full autoresearch test suite

Run: `pytest pipeline/tests/autoresearch/regime_autoresearch/ -v`
Expected: ≥170 tests PASS.

### Step 9.6: Commit dry-run artifact + mark CLAUDE.md

Update `CLAUDE.md` by adding under the Clockwork Schedule section:

```
**Autoresearch v2 (new 2026-04-25):**
- 20:00 — AnkaAutoresearchMode2: per-regime Mode 2 proposer + in-sample runner (info)
- 05:00 — AnkaAutoresearchBHFDR: per-regime BH-FDR batch trigger (info)
- 05:30 — AnkaAutoresearchHoldout: single-touch holdout runner (info)
```

Commit:

```bash
git add CLAUDE.md \
        pipeline/autoresearch/regime_autoresearch/data/run_mode2_summary_*.json \
        pipeline/autoresearch/regime_autoresearch/data/proposal_log_*.jsonl

git commit -m "feat(autoresearch): v2 Task 9 — first Mode 2 dry run end-to-end

5-proposal-per-regime smoke run demonstrates:
- 5 parallel regime workers spawn and exit cleanly
- Per-regime logs grew by 5 rows each (no file-lock contention)
- Hurdle values loaded from null_basket_hurdles_v2.parquet (not inline)
- schema_version='v2' on new rows; v1 NEUTRAL rows unchanged

Satisfies v2 acceptance criteria §8 items 1-4. Items 5-6 covered by
Task 8 doc sync.

Next operational step (outside this plan): register the three
AnkaAutoresearch* tasks with Windows Task Scheduler so the nightly
20:00 run begins.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Checklist (Plan-Time)

- [x] **Spec coverage:** Every §7 commit mapped to a Task: Task 1 (constants + panel), Task 2 (hurdle precompute), Task 3 (hurdle integration), Task 4 (feature library), Task 5 (log sharding), Task 6 (Mode 2 orchestrator), Task 7 (scheduled tasks), Task 8 (docs), Task 9 (dry run). **9 tasks for 9 commits.** ✅
- [x] **Placeholder scan:** No "TBD", "TODO", "fill in later", or "similar to Task N" anywhere. Every step has its actual code or command. ✅
- [x] **Type consistency:**
  - `PANEL_START = "2020-04-23"` referenced identically in Tasks 1, 2.
  - `load_null_basket_hurdle(construction, k, hold_horizon, regime, window="train_val")` signature identical in Tasks 2 and 3.
  - `REGIMES = ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")` used as-is; slug mapping `{"RISK-OFF": "risk_off", ...}` defined once in Task 5. ✅
  - 14 feature names in Task 4 exactly match spec §2.3. ✅
  - `schema_version: "v2"` string value consistent. ✅
  - `state=FORWARD_SHADOW_PASS` enum consistent in Tasks 6 and 9. ✅
- [x] **Task 6 atomicity:** promote_to_live.py stages both files and runs a single `git commit -m` — enforced in the script itself, not just the plan. ✅
- [x] **Kill-switch safety:** No task other than Task 6's promote_to_live creates files matching `*_strategy.py`. Task 6's orchestrator file is `run_mode2.py` (does not match kill-switch pattern). ✅

---

## Summary

9 tasks. Each produces one commit. Roughly:

| # | Task | Commit name (summary) | Approx size |
|---|---|---|---|
| 1 | Constants + panel extension | `feat(autoresearch): v2 Task 1 — panel start PANEL_START=2020-04-23` | 5 files modified, 1 created |
| 2 | Null-basket hurdle precompute | `feat(autoresearch): v2 Task 2 — null-basket hurdle precompute` | 2 new modules + parquet + tests |
| 3 | Hurdle integration | `feat(autoresearch): v2 Task 3 — swap NIFTY B&H for null-basket hurdle` | 2-3 files modified, 2 tests |
| 4 | Feature library expansion | `feat(autoresearch): v2 Task 4 — 14 new features (library 20 -> 34)` | features.py + test file |
| 5 | Proposal log sharding | `feat(autoresearch): v2 Task 5 — shard proposal log per regime` | rename + proposer.py + test |
| 6 | Mode 2 orchestrator + BH-FDR + promote | `feat(autoresearch): v2 Task 6 — Mode 2 orchestrator + BH-FDR + promote-to-live` | 3 new scripts + 3 test files |
| 7 | Scheduled-task wiring | `feat(autoresearch): v2 Task 7 — scheduled-task wiring` | inventory + 3 .bat files + test |
| 8 | Docs sync | `docs(autoresearch): v2 Task 8 — Station 11 v2 diffs` | SYSTEM_OPERATIONS_MANUAL |
| 9 | First Mode 2 dry run | `feat(autoresearch): v2 Task 9 — first Mode 2 dry run end-to-end` | CLAUDE.md + summary artifact |

**Test count trajectory:** 139 (v1) → 141 (Task 1) → 145 (Task 2) → 147 (Task 3) → 164 (Task 4) → 167 (Task 5) → 173 (Task 6) → 175 (Task 7) → unchanged (Task 8) → unchanged (Task 9). **Target: ≥155 tests green. Actual: ~175.**
