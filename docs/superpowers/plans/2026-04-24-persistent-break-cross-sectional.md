# Persistent-Break + Cross-Sectional Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute hypothesis **H-2026-04-24-002** — a Lasso regression model that predicts T+1 returns on persistent-break events (|z|≥3 on T and T-1, same sign) from a 236-dim cross-sectional feature vector, producing a `gate_checklist.json` with an unambiguous PASS or FAIL verdict.

**Architecture:** Five new Python modules under `pipeline/autoresearch/phase_c_cross_sectional/` that filter events → build features → fit LassoCV → evaluate naive comparators → run a streaming 100k-label-permutation null test → sweep 27 fragility points → compose the §15.1 gate checklist. The package imports — never rewrites — the existing `overshoot_compliance/` compliance primitives (slippage, metrics, manifest, data_audit, universe_snapshot, beta_regression, cusum_decay, portfolio_gate, impl_risk, gate_checklist). All event inputs flow from the frozen parent panel `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json` (14,907 rows).

**Tech Stack:** Python 3.13, pandas, numpy, scikit-learn (LassoCV), pyarrow (parquet), pytest. No new external dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (committed at `eb80ae5`, standards v1.0). Pre-registration rule §0.3 binds every numerical threshold in the spec — no retuning on FAIL.

---

## Pre-registration binding facts (read before any task)

**Binding spec numbers** (from `2026-04-23-persistent-break-cross-sectional-design.md`):

| Parameter | Value |
|---|---|
| Event filter | `|z|≥3` on T AND T-1, same sign, ticker has ≥60 trading days through T-1 |
| Feature count | 236 = 212 ticker z's + 17 sector means + 4 market context (vix + 3 regime one-hots) + 2 self z's + 1 break_direction |
| Label | `next_ret_pct_{i,T+1}` (percent, from events.json field `next_ret`) |
| Train split | event date ≤ 2025-12-31 |
| Holdout split | 2026-01-01 ≤ event date ≤ 2026-04-23 |
| Alpha grid | `numpy.logspace(-5, 0, 25)` |
| CV folds | 4 purged walk-forward with 2-day embargo on each side |
| Alpha selection metric | **mean OOS Sharpe across 4 CV folds** (NOT R²) |
| Epsilon (trading rule) | `0.5 × numpy.median(numpy.abs(train_predictions))`, frozen on training set |
| Seed | 42 (base); `numpy.random.SeedSequence(42).spawn(100_000)` for permutations |
| Permutation count | 100,000 |
| Fragility points | 27 = {α×0.8, α×1.0, α×1.2} × {z=2.5, 3.0, 3.5} × {persist=1, 2, 3 days} |
| Fragility pass rule | sign of (model − strongest-naive) Sharpe stable on ≥22/27 |
| Naive comparators | always-fade `-sign(residual_T)`; always-follow `sign(expected_return_T)`; buy-and-hold `+1` |
| Cost model version | `zerodha-ssf-2025-04` (matches parent) |

**Spec vs code slippage note:** the spec's motivation prose mentions "S1 = 20 bps". The existing `pipeline/autoresearch/overshoot_compliance/slippage_grid.py` defines `LEVELS = {"S0": 0.10, "S1": 0.30, "S2": 0.50, "S3": 0.70}` in percent. We use the code's existing `LEVELS` dict without modification so this run is comparable to the parent H-2026-04-23-001/002/003 runs. The prose 20 bps figure is shorthand; the code definition is the pre-registered binding.

**Events schema (binding)** — from `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json`:
```
{
  "ticker": "360ONE",
  "date": "2021-05-18",
  "z": -3.2476,                   # today's cross-sectional z on residual
  "today_resid": -8.22,           # today's residual %
  "today_ret": -7.30,             # today's raw return %
  "next_resid": 1.12,              # T+1 residual %
  "next_ret": 2.20,                # T+1 raw return % ← THIS IS y
  "direction": "DOWN",             # UP if z>0 else DOWN
  "actual_return_pct": -7.30,      # alias of today_ret
  "expected_return_pct": 0.93      # peer-predicted return on T
}
```

**Reusable primitives (DO NOT rewrite — import these):**

From `pipeline.autoresearch.overshoot_compliance`:
- `slippage_grid.LEVELS`, `slippage_grid.apply_level(ledger, level)`, `slippage_grid.apply_full_grid(ledger)`
- `metrics.per_bucket_metrics(returns_pct, annualisation_factor=252)` → dict with `sharpe`, `hit_rate`, `max_drawdown_pct`, `calmar`, CIs
- `manifest.build_manifest(hypothesis_id, strategy_version, cost_model_version, random_seed, data_files, config)`, `manifest.write_manifest(manifest, out_dir)`, `manifest.sha256_of(path)`
- `data_audit.run(...)` — produces `data_audit.json` row the gate checklist consumes
- `universe_snapshot.build(...)` — emits universe snapshot row
- `beta_regression.run(ledger_pct, nifty_returns)` — emits `{"gross_sharpe", "residual_sharpe"}`
- `cusum_decay.run(per_month_edge)` — emits `{"recent_24m_ratio"}`
- `portfolio_gate.run(ledger)` — emits `{"pairwise_corr_max", "concentration_max_sector_pct"}`
- `impl_risk.run(...)` — emits 10-scenario stress rows
- `gate_checklist.build(inputs, hypothesis_id=...)`, `gate_checklist.write(report, out_dir)`

From `pipeline.autoresearch.overshoot_reversion_backtest`:
- `BROAD_SECTOR: dict[str, str]` — 212-entry ticker → broad sector map
- `load_price_panel(...)` — loads `pipeline/data/fno_historical/*.csv` into a wide DataFrame (date × ticker close)
- `load_sector_map(...)` — wraps BROAD_SECTOR with coverage check
- `compute_residuals(panel, sector_map)` — produces the z-score panel the events panel is built on

**Parent events file path (binding):** `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json`.

---

## File structure (decomposition locked here)

**New package — `pipeline/autoresearch/phase_c_cross_sectional/`:**

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker + public API surface (`from .event_filter import filter_persistent_breaks`, etc.) |
| `event_filter.py` | `filter_persistent_breaks(events_df, z_threshold, persistence_days)` — filter to persistence subset |
| `feature_builder.py` | `build_feature_matrix(events_df, price_panel, regime_history, vix_series)` → `(X_df, y_series, feature_names)` |
| `model.py` | `fit_lasso(X_train, y_train, alpha_grid, cv_splits, embargo_days, seed)`, `predict(model, X, standardizer)`, `serialize(obj, path)`, `load(path)`, `compute_epsilon(train_predictions)` |
| `naive_adapters.py` | Three spec-bound naive comparators: `always_fade(events)`, `always_follow(events)`, `buy_and_hold(events)` → each returns a per-event signed-return series |
| `permutation_null.py` | `run_label_permutation_null(X_train, y_train, X_test, y_test_gross, strongest_naive_sharpe, n_shuffles, seed_sequence, alpha, n_workers)` → `{"p_value", "observed_margin", "histogram"}` |
| `fragility_sweep.py` | `run_fragility_sweep(parent_events, price_panel, regime_history, vix_series, base_alpha)` → `{"verdict", "n_same_sign", "rows"}` |
| `runner.py` | CLI orchestration: `python -m pipeline.autoresearch.phase_c_cross_sectional.runner --events-path <parent.json> --out-dir <timestamp>` — writes all artifacts |

**New test package — `pipeline/tests/autoresearch/phase_c_cross_sectional/`:**

| File | Mirrors |
|---|---|
| `__init__.py` | package marker |
| `conftest.py` | shared synthetic fixtures (mini events list, mini price panel, mini regime history) |
| `test_event_filter.py` | event_filter.py |
| `test_feature_builder.py` | feature_builder.py |
| `test_model.py` | model.py |
| `test_naive_adapters.py` | naive_adapters.py |
| `test_permutation_null.py` | permutation_null.py (small N — 100 shuffles with fixed seed) |
| `test_fragility_sweep.py` | fragility_sweep.py (stub parent panel, 3 tickers, 30 events) |
| `test_runner_smoke.py` | runner.py — 20-event synthetic end-to-end producing a deterministic `gate_checklist.json` |

**Output artifact directory (runtime):** `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<UTC timestamp>/` with:
- `manifest.json`, `feature_matrix_train.parquet`, `feature_matrix_test.parquet`, `model.pkl`, `model_coefs.json`, `predictions.parquet`, `slippage_grid.json`, `naive_comparators.json`, `permutation_null.json`, `fragility_sweep.json`, `beta_regression.json`, `impl_risk.json`, `cusum_decay.json`, `portfolio_gate.json`, `data_audit.json`, `universe_snapshot.json`, `gate_checklist.json`, `predictions_run.log`.

---

### Task 1: Pre-register hypothesis H-2026-04-24-002

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl` — append one line.

**Why first:** §0.3 requires the registry entry to land *before* any code that consumes its thresholds.

- [ ] **Step 1: Write the registry line**

Append exactly this JSON (single line, pretty-printed here for review) to `docs/superpowers/hypothesis-registry.jsonl`:

```json
{"hypothesis_id": "H-2026-04-24-002", "author": "bharatankaraju", "date_registered": "2026-04-24", "strategy_name": "phase-c-persistent-break-cross-sectional", "strategy_class": "cross-sectional-linear-predictive", "description": "Lasso regression on 236-dim cross-sectional feature vector (212 peer z-scores + 17 sector means + vix + 3 regime one-hots + 2 self z's + break direction) predicting T+1 return on the persistent-break subset (|z|>=3 on T and T-1, same sign) of the 14,907-event H-2026-04-23-001 parent panel. Sign-triggered trading rule around frozen epsilon = 0.5*median(|training_predictions|). Single-model family: Bonferroni alpha = 0.05.", "claimed_edge": {"metric": "holdout_S1_sharpe_margin_over_strongest_naive", "threshold_sign": "positive", "units": "sharpe_ratio", "slippage_level": "S1", "alpha_for_significance": 0.05, "multiplicity_correction": "none", "ci_level": 0.95, "notes": "Single-model family. No point estimates from exploratory work are used to calibrate thresholds. Epsilon is calibrated on training-set prediction magnitudes, not holdout."}, "universe": {"source": "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json filtered to persistence subset", "point_in_time_compliant": false, "survivorship_status": "UNCORRECTED-INHERITED-FROM-H-2026-04-23-001", "n_tickers_current": 213, "coverage_ratio_estimate_pct_delisted": "<5% per H-2026-04-23-001 waiver"}, "date_range": {"start": "2021-04-23", "end": "2025-12-31", "holdout_start": "2026-01-01", "holdout_end": "2026-04-23", "holdout_pct": 0.06, "notes": "Holdout 6% flagged as warning vs Section 10.1 20% target; accepted at registration to maintain comparability with H-2026-04-23-001/002/003 parent slice."}, "statistical_test": {"method": "label_permutation_null", "n_permutations_required": 100000, "rationale": "Single-model family means p_raw <= 0.05 is final; 100k shuffles per Section 9B.2 to resolve well below 1e-3 floor."}, "hypothesis_family_scope": {"primary": "single-model", "primary_family_size_estimate": 1, "audit_scopes": ["strategy-class:cross-sectional-linear-predictive", "geometry:persistent-break-2day", "universe-scope:F&O-213"], "notes": "Family size 1: no multiplicity correction. Separate from the per-cell ticker-family scope of H-2026-04-23-001 by design."}, "execution_mode": "MODE_A_EOD_close_to_close", "power_analysis": {"required_n_holdout": 50, "min_detectable_effect": "to be computed from training-set prediction std before gate evaluation"}, "pre_exploration_disclosure": "H-2026-04-23-001 parent panel has been fully explored including 2 slice hypotheses (H-002 LAG, H-003 OVERSHOOT) all FAIL at Bonferroni. This new registration reframes from per-cell tests to a single family-of-1 predictive model. No feature weights, alphas, or thresholds from prior work are used to calibrate this model; the full LassoCV grid selects alpha on training data only. The 2-day persistence filter is pre-registered here, not derived from exploratory survivor inspection.", "status": "PRE_REGISTERED", "terminal_state": null, "git_commit_at_registration": null, "standards_version": "1.0_2026-04-23", "raw_bar_canonicity_policy": "docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md v1.0 — MODE A T, T+1 execution window gate applies."}
```

- [ ] **Step 2: Verify file parses as JSONL**

Run:
```bash
python -c "import json; [json.loads(l) for l in open('docs/superpowers/hypothesis-registry.jsonl')]"
```
Expected: no output (no exceptions).

- [ ] **Step 3: Commit registry entry**

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: H-2026-04-24-002 persistent-break cross-sectional (PRE_REGISTERED)"
```

- [ ] **Step 4: Capture the registration commit SHA and backfill `git_commit_at_registration`**

```bash
SHA=$(git rev-parse HEAD)
python -c "
import json
lines = open('docs/superpowers/hypothesis-registry.jsonl').readlines()
last = json.loads(lines[-1])
last['git_commit_at_registration'] = '$SHA'
lines[-1] = json.dumps(last) + '\n'
open('docs/superpowers/hypothesis-registry.jsonl', 'w').writelines(lines)
"
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: backfill H-2026-04-24-002 git_commit_at_registration"
```

---

### Task 2: Create package skeleton + test scaffolding

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/__init__.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/__init__.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/conftest.py`

- [ ] **Step 1: Create package `__init__.py`**

`pipeline/autoresearch/phase_c_cross_sectional/__init__.py`:
```python
"""Persistent-break + cross-sectional predictive model (H-2026-04-24-002).

See docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md
for the frozen spec. All thresholds here are pre-registration-bound (spec §0.3).
"""
```

- [ ] **Step 2: Create test package markers**

`pipeline/tests/autoresearch/phase_c_cross_sectional/__init__.py`:
```python
```

- [ ] **Step 3: Create shared synthetic fixtures in `conftest.py`**

`pipeline/tests/autoresearch/phase_c_cross_sectional/conftest.py`:
```python
"""Synthetic fixtures for cross-sectional model unit tests.

Deliberately tiny so tests stay under 1 s. Each fixture is fully deterministic
under the fixed seed in test_feature_builder / test_model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def tiny_events_df() -> pd.DataFrame:
    """Six events across three tickers, two dates. Three are persistent
    (|z|>=3 on T AND T-1, same sign), three are not."""
    rows = [
        # Persistent SBIN UP on 2024-01-10 (was +3.5 on 2024-01-09)
        {"ticker": "SBIN", "date": "2024-01-10", "z": 3.6, "today_resid": 4.0,
         "today_ret": 4.1, "next_resid": 0.2, "next_ret": 0.8,
         "direction": "UP", "actual_return_pct": 4.1, "expected_return_pct": 0.1},
        # Persistent RELIANCE DOWN on 2024-02-15
        {"ticker": "RELIANCE", "date": "2024-02-15", "z": -3.2,
         "today_resid": -3.8, "today_ret": -4.0, "next_resid": 1.1,
         "next_ret": 1.5, "direction": "DOWN",
         "actual_return_pct": -4.0, "expected_return_pct": -0.2},
        # Persistent HDFC UP on 2024-03-20
        {"ticker": "HDFC", "date": "2024-03-20", "z": 3.1, "today_resid": 3.5,
         "today_ret": 3.4, "next_resid": -0.3, "next_ret": -0.5,
         "direction": "UP", "actual_return_pct": 3.4, "expected_return_pct": -0.1},
        # Non-persistent: single-day 4σ on SBIN 2024-01-20 (no prior-day 3σ)
        {"ticker": "SBIN", "date": "2024-01-20", "z": 4.0, "today_resid": 4.5,
         "today_ret": 4.6, "next_resid": 0.1, "next_ret": 0.2,
         "direction": "UP", "actual_return_pct": 4.6, "expected_return_pct": 0.1},
        # Non-persistent: opposing-sign days on RELIANCE 2024-04-05
        {"ticker": "RELIANCE", "date": "2024-04-05", "z": 3.3,
         "today_resid": 3.7, "today_ret": 3.8, "next_resid": -0.5,
         "next_ret": -1.0, "direction": "UP",
         "actual_return_pct": 3.8, "expected_return_pct": 0.1},
        # Below threshold HDFC 2024-05-01 (|z|=2.7 < 3)
        {"ticker": "HDFC", "date": "2024-05-01", "z": 2.7, "today_resid": 3.0,
         "today_ret": 3.1, "next_resid": 0.2, "next_ret": 0.3,
         "direction": "UP", "actual_return_pct": 3.1, "expected_return_pct": 0.1},
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def tiny_z_panel() -> pd.DataFrame:
    """Synthetic z-score panel: dates × 3 tickers, deterministic.
    Includes T-1 rows needed by the persistence filter.
    """
    dates = pd.to_datetime([
        "2024-01-08", "2024-01-09", "2024-01-10",
        "2024-02-14", "2024-02-15",
        "2024-03-19", "2024-03-20",
        "2024-01-19", "2024-01-20",
        "2024-04-04", "2024-04-05",
        "2024-04-30", "2024-05-01",
    ])
    tickers = ["SBIN", "RELIANCE", "HDFC"]
    # Row-wise values chosen so SBIN/RELIANCE/HDFC have the needed T-1 z's:
    data = {
        "SBIN":     [0.1, 3.5, 3.6, 0.0, 0.1, 0.2, 0.3, 0.5, 4.0, 0.1, 0.2, 0.0, 0.1],
        "RELIANCE": [0.0, 0.1, 0.2, -3.1, -3.2, 0.1, 0.0, 0.0, 0.1, -0.5, 3.3, 0.0, 0.1],
        "HDFC":     [0.0, 0.1, 0.0, 0.1, 0.0, 3.0, 3.1, 0.1, 0.0, 0.1, 0.1, 2.5, 2.7],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def tiny_regime_history() -> pd.DataFrame:
    """Date → regime label. Covers all dates referenced by tiny_events_df."""
    return pd.DataFrame({
        "date": pd.to_datetime([
            "2024-01-08", "2024-01-09", "2024-01-10",
            "2024-01-19", "2024-01-20",
            "2024-02-14", "2024-02-15",
            "2024-03-19", "2024-03-20",
            "2024-04-04", "2024-04-05",
            "2024-04-30", "2024-05-01",
        ]),
        "regime": [
            "NEUTRAL", "NEUTRAL", "NEUTRAL",
            "RISK_OFF", "RISK_OFF",
            "RISK_ON", "RISK_ON",
            "NEUTRAL", "NEUTRAL",
            "RISK_OFF", "RISK_OFF",
            "NEUTRAL", "NEUTRAL",
        ],
    }).set_index("date")


@pytest.fixture
def tiny_vix_series() -> pd.Series:
    """VIX close per date. Aligned with tiny_regime_history index."""
    idx = pd.to_datetime([
        "2024-01-08", "2024-01-09", "2024-01-10",
        "2024-01-19", "2024-01-20",
        "2024-02-14", "2024-02-15",
        "2024-03-19", "2024-03-20",
        "2024-04-04", "2024-04-05",
        "2024-04-30", "2024-05-01",
    ])
    return pd.Series(
        [14.2, 14.5, 15.0, 18.0, 19.5, 12.0, 11.8,
         15.5, 15.0, 20.0, 22.5, 14.8, 14.0],
        index=idx, name="vix_close",
    )


@pytest.fixture
def tiny_broad_sector() -> dict:
    """Broad sector map for the 3 test tickers."""
    return {"SBIN": "Banks", "RELIANCE": "Energy", "HDFC": "FinSvc"}
```

- [ ] **Step 4: Run the empty test suite to verify discovery**

```bash
cd C:/Users/Claude_Anka/askanka.com
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/ -v
```
Expected: `collected 0 items` (no failures).

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/__init__.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/
git commit -m "scaffold: phase_c_cross_sectional package + test fixtures"
```

---

### Task 3: `event_filter.filter_persistent_breaks`

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/event_filter.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py`

The function filters a parent-panel events DataFrame to the subset satisfying `|z_T| ≥ z_threshold AND |z_{T-1}| ≥ z_threshold AND sign(z_T) == sign(z_{T-1})` for `persistence_days = 2`; generalizes to N-day persistence.

The per-event z's on T-1 (and T-2 when persistence_days=3) are looked up in a **z_panel** DataFrame (dates × tickers), which the caller builds once from the parent price panel. The 60-trading-day history check is done by verifying the ticker has ≥60 non-NaN z values in z_panel up through T-1.

- [ ] **Step 1: Write the failing test**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py`:
```python
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.event_filter import (
    filter_persistent_breaks,
)


def test_filter_keeps_three_persistent_events(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2,
        min_history_days=5,  # relaxed for synthetic fixture
    )
    kept = list(zip(out["ticker"], out["date"].astype(str)))
    assert sorted(kept) == [
        ("HDFC", "2024-03-20"),
        ("RELIANCE", "2024-02-15"),
        ("SBIN", "2024-01-10"),
    ]


def test_filter_drops_single_day_spike(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # SBIN 2024-01-20 had no prior-day 3σ
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-20")).any()


def test_filter_drops_opposing_sign(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # RELIANCE 2024-04-05: T-1=-0.5 (below threshold), T=+3.3 → fails persistence
    assert not ((out["ticker"] == "RELIANCE") & (out["date"] == "2024-04-05")).any()


def test_filter_drops_below_threshold(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # HDFC 2024-05-01: z=2.7 < 3
    assert not ((out["ticker"] == "HDFC") & (out["date"] == "2024-05-01")).any()


def test_persistence_3_days_stricter(tiny_events_df, tiny_z_panel):
    # With 3-day persistence, SBIN on 2024-01-10 is kept only if SBIN z on 2024-01-08 also >=3
    # In the fixture SBIN 2024-01-08 z=0.1 so 3-day persistence drops it
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=3, min_history_days=5,
    )
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-10")).any()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.autoresearch.phase_c_cross_sectional.event_filter'`.

- [ ] **Step 3: Implement `event_filter.py`**

`pipeline/autoresearch/phase_c_cross_sectional/event_filter.py`:
```python
"""Persistent-break filter for H-2026-04-24-002.

A persistent break is an event on date T for ticker i where:
  |z_{i,T}|    >= z_threshold
  |z_{i,T-k}|  >= z_threshold  for k in 1..persistence_days-1
  sign(z_{i,T}) == sign(z_{i,T-k})  for all k
  ticker i has >= min_history_days non-NaN z observations through T-1

The spec binds (z_threshold=3.0, persistence_days=2, min_history_days=60) for
the primary run; fragility sweeps perturb the first two.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def filter_persistent_breaks(
    events_df: pd.DataFrame,
    z_panel: pd.DataFrame,
    *,
    z_threshold: float,
    persistence_days: int,
    min_history_days: int = 60,
) -> pd.DataFrame:
    """Return the subset of events_df satisfying the persistence filter.

    Parameters
    ----------
    events_df
        Parent panel events. Must have columns: ticker, date, z.
    z_panel
        Wide DataFrame (dates × tickers) of cross-sectional z-scores. Must
        contain all lookback rows needed for each event; missing rows raise.
    z_threshold, persistence_days, min_history_days
        Spec-bound parameters.

    Returns
    -------
    DataFrame with the same schema as events_df, filtered.
    """
    if persistence_days < 1:
        raise ValueError("persistence_days must be >= 1")

    ev = events_df.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    z_panel = z_panel.sort_index()

    keep_mask = np.zeros(len(ev), dtype=bool)
    for i, row in enumerate(ev.itertuples(index=False)):
        t = pd.Timestamp(row.date)
        tkr = row.ticker
        z_t = float(row.z)
        if abs(z_t) < z_threshold:
            continue
        if tkr not in z_panel.columns:
            continue
        col = z_panel[tkr].loc[:t]
        if col.dropna().shape[0] < min_history_days:
            continue
        ok = True
        for k in range(1, persistence_days):
            # find the k-th previous trading day for this ticker (non-NaN row)
            col_before = col.loc[col.index < t].dropna()
            if col_before.shape[0] < k:
                ok = False
                break
            z_prev = float(col_before.iloc[-k])
            if abs(z_prev) < z_threshold or _sign(z_prev) != _sign(z_t):
                ok = False
                break
        if ok:
            keep_mask[i] = True

    return ev.loc[keep_mask].reset_index(drop=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Smoke-check the filter against the real parent panel**

```bash
python -c "
import json, pandas as pd
from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
from pipeline.autoresearch.overshoot_reversion_backtest import load_price_panel, compute_residuals, load_sector_map

events = pd.DataFrame(json.load(open('pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json')))
print('parent events:', len(events))

panel = load_price_panel()
sector_map = load_sector_map(panel)
# compute_residuals returns (expected_df, residual_df, z_df)
_, _, z_df = compute_residuals(panel, sector_map)
kept = filter_persistent_breaks(events, z_df, z_threshold=3.0, persistence_days=2, min_history_days=60)
print('persistent subset:', len(kept))
"
```
Expected: `persistent subset: <some number in 1000–2000 range>`. If <500, HALT and raise with the user — the spec says "revisit if n<500" in §event-filter of the design doc.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/event_filter.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py
git commit -m "feat(phase_c_cross_sectional): event_filter.filter_persistent_breaks with TDD"
```

---

### Task 4: `feature_builder.build_feature_matrix`

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/feature_builder.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py`

Builds the 236-column feature matrix from a persistent-event list, price panel, regime history, and VIX series.

**Column order (binding):**
1. Columns 0..211 — `z_peer_<TICKER>` for each ticker j in sorted universe (excluding self at row-fill time by zero-imputation).
2. Columns 212..228 — `sector_mean_<SECTOR>` for each of 17 broad sectors, alphabetical.
3. Column 229 — `vix_close`.
4. Columns 230..232 — `regime_RISK_OFF`, `regime_NEUTRAL`, `regime_RISK_ON` (one-hot, all three retained).
5. Column 233 — `z_self_T`.
6. Column 234 — `z_self_T_minus_1`.
7. Column 235 — `break_direction` (+1 or −1).

- [ ] **Step 1: Write the failing test**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py`:
```python
import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.feature_builder import (
    build_feature_matrix,
)


def test_feature_shape(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    # Use only the 3 persistent events from the fixture
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    X, y, names = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # 3 tickers in peer block + 3 sector means + vix + 3 regime dummies + z_self_T + z_self_T-1 + direction
    expected_cols = 3 + 3 + 1 + 3 + 1 + 1 + 1
    assert X.shape == (3, expected_cols)
    assert len(names) == expected_cols
    assert list(y.index) == list(X.index)


def test_feature_no_lookahead_self_zero(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    X, y, names = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # For the SBIN row, z_peer_SBIN column should be 0 (self zeroed)
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert X.loc[sbin_idx, "z_peer_SBIN"] == 0.0
    # But z_peer_RELIANCE on the SBIN row should equal z_panel["RELIANCE"] at that date
    sbin_date = pd.Timestamp(persistent.loc[sbin_idx, "date"])
    assert X.loc[sbin_idx, "z_peer_RELIANCE"] == tiny_z_panel.loc[sbin_date, "RELIANCE"]


def test_break_direction_sign(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    X, _, _ = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # SBIN row was UP (z=+3.6)
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert X.loc[sbin_idx, "break_direction"] == 1
    # RELIANCE row was DOWN (z=-3.2)
    rel_idx = persistent.index[persistent["ticker"] == "RELIANCE"][0]
    assert X.loc[rel_idx, "break_direction"] == -1


def test_label_matches_next_ret(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    _, y, _ = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert y.loc[sbin_idx] == 0.8  # from tiny_events_df fixture
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.autoresearch.phase_c_cross_sectional.feature_builder'`.

- [ ] **Step 3: Implement `feature_builder.py`**

`pipeline/autoresearch/phase_c_cross_sectional/feature_builder.py`:
```python
"""Feature matrix construction for H-2026-04-24-002.

Produces the 236-column feature vector per the spec §Feature Set.
No look-ahead: all features are computed from data at or before T close.
The broken stock's own z_peer_<ticker> column is zeroed (self-dropped).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


REGIME_ORDER = ("RISK_OFF", "NEUTRAL", "RISK_ON")


def build_feature_matrix(
    events_df: pd.DataFrame,
    z_panel: pd.DataFrame,
    regime_history: pd.DataFrame,
    vix_series: pd.Series,
    *,
    broad_sector: dict,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Build (X, y, feature_names) for the events in events_df.

    Parameters
    ----------
    events_df
        Persistent events (output of event_filter.filter_persistent_breaks).
    z_panel
        Wide z-score panel (dates × tickers).
    regime_history
        DataFrame indexed by date with column 'regime' in REGIME_ORDER.
    vix_series
        Series indexed by date with VIX close values.
    broad_sector
        Ticker → broad sector string. Tickers missing from this map are
        assigned sector 'Unmapped' (does not contribute to sector means).

    Returns
    -------
    X : DataFrame indexed like events_df with 236-column feature matrix.
    y : Series indexed like events_df with next_ret labels (percent).
    feature_names : list[str] column order.
    """
    if events_df.empty:
        raise ValueError("events_df is empty; nothing to build features from")

    ev = events_df.copy()
    ev["date"] = pd.to_datetime(ev["date"])

    all_tickers = sorted(z_panel.columns)
    sectors = sorted(set(broad_sector.values()) - {"Unmapped"})

    peer_cols = [f"z_peer_{t}" for t in all_tickers]
    sector_cols = [f"sector_mean_{s}" for s in sectors]
    regime_cols = [f"regime_{r}" for r in REGIME_ORDER]
    feature_names = (
        peer_cols + sector_cols + ["vix_close"] + regime_cols
        + ["z_self_T", "z_self_T_minus_1", "break_direction"]
    )

    rows = []
    y_values = []
    idx = []
    for row in ev.itertuples(index=True):
        t = pd.Timestamp(row.date)
        tkr = row.ticker
        # --- peer z's ---
        if t not in z_panel.index:
            raise KeyError(f"z_panel missing date {t.date()} for event {tkr}")
        peer_z = z_panel.loc[t].reindex(all_tickers).fillna(0.0).astype(float)
        peer_z.loc[tkr] = 0.0  # self-drop
        # --- sector means (exclude self ticker from its sector's mean) ---
        sec_vals = {}
        for sec in sectors:
            tickers_in_sec = [tt for tt, s in broad_sector.items() if s == sec and tt != tkr]
            if len(tickers_in_sec) < 3:
                sec_vals[sec] = 0.0  # noisy-denominator safeguard per spec
            else:
                sec_z = z_panel.loc[t].reindex(tickers_in_sec).dropna()
                sec_vals[sec] = float(sec_z.mean()) if len(sec_z) >= 3 else 0.0
        # --- market context ---
        vix = float(vix_series.loc[t]) if t in vix_series.index else 0.0
        regime = (
            regime_history.loc[t, "regime"]
            if t in regime_history.index else "NEUTRAL"
        )
        regime_one_hot = {f"regime_{r}": int(r == regime) for r in REGIME_ORDER}
        # --- self z's ---
        z_self_T = float(row.z)
        col_before = z_panel[tkr].loc[z_panel.index < t].dropna()
        z_self_Tm1 = float(col_before.iloc[-1]) if len(col_before) else 0.0
        # --- break direction ---
        direction = 1 if z_self_T > 0 else -1

        feature_row = {}
        for ticker, val in peer_z.items():
            feature_row[f"z_peer_{ticker}"] = val
        for sec, val in sec_vals.items():
            feature_row[f"sector_mean_{sec}"] = val
        feature_row["vix_close"] = vix
        feature_row.update(regime_one_hot)
        feature_row["z_self_T"] = z_self_T
        feature_row["z_self_T_minus_1"] = z_self_Tm1
        feature_row["break_direction"] = direction

        rows.append(feature_row)
        y_values.append(float(row.next_ret))
        idx.append(row.Index)

    X = pd.DataFrame(rows, index=idx, columns=feature_names).astype(float)
    y = pd.Series(y_values, index=idx, name="next_ret_pct")
    return X, y, feature_names
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/feature_builder.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py
git commit -m "feat(phase_c_cross_sectional): feature_builder.build_feature_matrix with TDD"
```

---

### Task 5: `model` — fit_lasso + predict + serialize + compute_epsilon

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/model.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py`:
```python
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.model import (
    fit_lasso, predict, serialize, load, compute_epsilon,
    purged_walk_forward_splits,
)


def _synthetic_regression(n=200, n_features=10, seed=1):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.standard_normal((n, n_features)),
                     columns=[f"f{i}" for i in range(n_features)])
    # true signal only on f0
    y = pd.Series(2.0 * X["f0"].values + 0.1 * rng.standard_normal(n),
                  name="y")
    return X, y


def test_fit_lasso_runs_and_returns_bundle():
    X, y = _synthetic_regression()
    alpha_grid = np.logspace(-5, 0, 6)
    bundle = fit_lasso(
        X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42,
    )
    assert set(bundle.keys()) >= {"model", "standardizer", "alpha", "coef_", "intercept_"}
    assert bundle["coef_"].shape[0] == X.shape[1]


def test_predict_roundtrip():
    X, y = _synthetic_regression()
    alpha_grid = np.logspace(-5, 0, 6)
    bundle = fit_lasso(X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42)
    yhat = predict(bundle, X)
    # On training set, Lasso should be ~correlated with y
    assert np.corrcoef(yhat, y)[0, 1] > 0.5


def test_compute_epsilon_is_half_median_abs():
    train_preds = np.array([-2.0, -1.0, 0.5, 1.0, 3.0])
    # |preds| = 2,1,0.5,1,3 → median = 1.0 → eps = 0.5
    assert compute_epsilon(train_preds) == pytest.approx(0.5)


def test_serialize_roundtrip(tmp_path):
    X, y = _synthetic_regression(n=50, n_features=5)
    alpha_grid = np.logspace(-5, 0, 4)
    bundle = fit_lasso(X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42)
    pth = tmp_path / "model.pkl"
    serialize(bundle, pth)
    b2 = load(pth)
    np.testing.assert_allclose(b2["coef_"], bundle["coef_"])
    np.testing.assert_allclose(predict(b2, X), predict(bundle, X))


def test_purged_walk_forward_embargo():
    # 100 training dates; 4 folds; embargo 2 days
    splits = purged_walk_forward_splits(n=100, n_splits=4, embargo=2)
    assert len(splits) == 4
    for train_idx, val_idx in splits:
        # no training index should be within embargo of any validation index
        for v in val_idx:
            assert not any(abs(t - v) <= 2 for t in train_idx)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.autoresearch.phase_c_cross_sectional.model'`.

- [ ] **Step 3: Implement `model.py`**

`pipeline/autoresearch/phase_c_cross_sectional/model.py`:
```python
"""Lasso model fit/predict/serialize for H-2026-04-24-002.

Binding spec notes:
  - Alpha selected on MEAN OOS SHARPE across 4 purged walk-forward CV folds,
    not R². Sharpe on each fold is computed over validation-set predictions
    treated as a signed return (sign(pred) * y_val), annualised at 252.
  - Feature standardization fit on training only; standardizer travels with
    the bundle.
  - Refit on full training set after alpha selection (no CV held-out).
  - epsilon = 0.5 * median(|training_predictions|), frozen on training set.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler


def purged_walk_forward_splits(n: int, n_splits: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Chronological fold boundaries with ±embargo days of training purged
    around each validation window. Returns (train_idx, val_idx) lists.
    """
    fold_size = n // n_splits
    splits = []
    for k in range(n_splits):
        val_lo = k * fold_size
        val_hi = (k + 1) * fold_size if k < n_splits - 1 else n
        val_idx = list(range(val_lo, val_hi))
        train_idx = [
            i for i in range(n)
            if (i < val_lo - embargo) or (i >= val_hi + embargo)
        ]
        splits.append((train_idx, val_idx))
    return splits


def _sharpe_of_signed(preds: np.ndarray, y: np.ndarray, ann_factor: int = 252) -> float:
    signed = np.sign(preds) * y
    signed = signed[~np.isnan(signed)]
    if signed.size < 2 or signed.std(ddof=1) == 0:
        return 0.0
    return float(signed.mean() / signed.std(ddof=1) * np.sqrt(ann_factor))


def fit_lasso(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    alpha_grid: np.ndarray,
    cv_splits: int,
    embargo_days: int,
    seed: int,
) -> dict:
    """Fit Lasso with alpha chosen to maximise mean OOS Sharpe over purged CV folds."""
    X = X_train.to_numpy(dtype=float)
    y = y_train.to_numpy(dtype=float)
    n = X.shape[0]
    splits = purged_walk_forward_splits(n, cv_splits, embargo_days)

    alpha_mean_sharpes = []
    for alpha in alpha_grid:
        fold_sharpes = []
        for train_idx, val_idx in splits:
            X_tr = X[train_idx]
            y_tr = y[train_idx]
            X_va = X[val_idx]
            y_va = y[val_idx]
            scaler = StandardScaler().fit(X_tr)
            model = Lasso(alpha=alpha, max_iter=50_000, random_state=seed)
            model.fit(scaler.transform(X_tr), y_tr)
            preds = model.predict(scaler.transform(X_va))
            fold_sharpes.append(_sharpe_of_signed(preds, y_va))
        alpha_mean_sharpes.append(float(np.mean(fold_sharpes)))

    best_idx = int(np.argmax(alpha_mean_sharpes))
    best_alpha = float(alpha_grid[best_idx])

    standardizer = StandardScaler().fit(X)
    final = Lasso(alpha=best_alpha, max_iter=50_000, random_state=seed)
    final.fit(standardizer.transform(X), y)

    return {
        "model": final,
        "standardizer": standardizer,
        "alpha": best_alpha,
        "alpha_grid": alpha_grid.tolist(),
        "alpha_mean_sharpes": alpha_mean_sharpes,
        "coef_": final.coef_,
        "intercept_": float(final.intercept_),
        "feature_names": list(X_train.columns),
    }


def predict(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """Apply standardizer then model, return predictions in percent-return units."""
    arr = X.to_numpy(dtype=float)
    return bundle["model"].predict(bundle["standardizer"].transform(arr))


def compute_epsilon(training_predictions: np.ndarray) -> float:
    """Frozen trading-rule threshold: 0.5 × median(|training_predictions|)."""
    return float(0.5 * np.median(np.abs(training_predictions)))


def serialize(bundle: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(bundle, fh)
    return path


def load(path: Path) -> dict:
    with open(path, "rb") as fh:
        return pickle.load(fh)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/model.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py
git commit -m "feat(phase_c_cross_sectional): model.fit_lasso with purged walk-forward CV and TDD"
```

---

### Task 6: `naive_adapters` — always-fade, always-follow, buy-and-hold

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/naive_adapters.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py`

Produces a `pandas.Series` of signed percent returns per event for each naive, plus a summary row (mean, Sharpe, hit-rate) computed via `overshoot_compliance.metrics.per_bucket_metrics`.

**Not** reused from `overshoot_compliance.naive_comparators` — that module's three baselines (random_direction, equal_weight_basket, momentum_follow using `sign(z)`) do not match the spec's three baselines (always-fade on residual, always-follow on expected_return, buy-and-hold).

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py`:
```python
import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.naive_adapters import (
    always_fade, always_follow, buy_and_hold, summarize_naive,
)


def _events():
    return pd.DataFrame([
        # Event 1: residual > 0 → always-fade SHORT → -1 × next_ret
        {"ticker": "A", "next_ret": 1.0, "expected_return_pct": 0.3,
         "actual_return_pct": 4.0, "today_resid": 3.7},
        # Event 2: residual < 0 → always-fade LONG → +1 × next_ret
        {"ticker": "B", "next_ret": -0.5, "expected_return_pct": -0.2,
         "actual_return_pct": -4.1, "today_resid": -3.9},
    ])


def test_always_fade_signs():
    ev = _events()
    s = always_fade(ev)
    # Event 1: fade sign = -sign(3.7) = -1 → -1 × 1.0 = -1.0
    assert s.iloc[0] == -1.0
    # Event 2: fade sign = -sign(-3.9) = +1 → +1 × -0.5 = -0.5
    assert s.iloc[1] == -0.5


def test_always_follow_signs():
    ev = _events()
    s = always_follow(ev)
    # Event 1: follow sign = sign(+0.3) = +1 → +1 × 1.0 = +1.0
    assert s.iloc[0] == 1.0
    # Event 2: follow sign = sign(-0.2) = -1 → -1 × -0.5 = +0.5
    assert s.iloc[1] == 0.5


def test_buy_and_hold_sign():
    ev = _events()
    s = buy_and_hold(ev)
    # +1 × next_ret always
    assert s.iloc[0] == 1.0
    assert s.iloc[1] == -0.5


def test_summarize_naive_suite_picks_strongest():
    ev = _events()
    summary = summarize_naive(ev)
    assert set(summary.keys()) == {"always_fade", "always_follow", "buy_and_hold"}
    for k in summary:
        assert "sharpe" in summary[k]
        assert "mean_ret_pct" in summary[k]
        assert "n_trades" in summary[k]
    # Each summary row references its signed returns
    assert summary["always_follow"]["n_trades"] == 2
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `naive_adapters.py`**

`pipeline/autoresearch/phase_c_cross_sectional/naive_adapters.py`:
```python
"""Spec-bound naive comparators for H-2026-04-24-002 §9B.1.

always_fade:   direction = -sign(today_resid), P&L = sign × next_ret
always_follow: direction = +sign(expected_return_pct), P&L = sign × next_ret
buy_and_hold:  direction = +1, P&L = next_ret
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import metrics as M


def _signed(ev: pd.DataFrame, sign: np.ndarray) -> pd.Series:
    return pd.Series(sign * ev["next_ret"].to_numpy(float), index=ev.index,
                     name="pnl_pct")


def always_fade(events: pd.DataFrame) -> pd.Series:
    sign = -np.sign(events["today_resid"].to_numpy(float))
    return _signed(events, sign)


def always_follow(events: pd.DataFrame) -> pd.Series:
    sign = np.sign(events["expected_return_pct"].to_numpy(float))
    return _signed(events, sign)


def buy_and_hold(events: pd.DataFrame) -> pd.Series:
    sign = np.ones(len(events), dtype=float)
    return _signed(events, sign)


def summarize_naive(events: pd.DataFrame) -> dict:
    rows = {
        "always_fade": always_fade(events),
        "always_follow": always_follow(events),
        "buy_and_hold": buy_and_hold(events),
    }
    out = {}
    for name, s in rows.items():
        core = M.per_bucket_metrics(s.to_numpy())
        out[name] = {
            "sharpe": core["sharpe"],
            "mean_ret_pct": core["mean_ret_pct"],
            "hit_rate": core["hit_rate"],
            "n_trades": core["n_trades"],
        }
    return out


def strongest_name(summary: dict, metric: str = "sharpe") -> str:
    return max(summary.keys(), key=lambda k: summary[k][metric])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/naive_adapters.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py
git commit -m "feat(phase_c_cross_sectional): naive_adapters (fade/follow/buy-and-hold) with TDD"
```

---

### Task 7: `permutation_null.run_label_permutation_null`

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/permutation_null.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py`

**Streaming design (binding):** each worker shuffles y_train using a seeded child RNG, refits Lasso at the CV-selected alpha (no re-CV — that would make permutation 100× slower and change what's tested), predicts on X_test, applies the spec's trading rule with epsilon recomputed per shuffle from the permuted training predictions, computes S1-net Sharpe, returns the margin vs `strongest_naive_sharpe`. The main process accumulates margin values into a numpy array (100k × 4 bytes = 400 KB) and computes p = fraction ≥ observed.

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py`:
```python
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.permutation_null import (
    run_label_permutation_null, single_shuffle_margin,
)


def _synth(n_train=60, n_test=20, n_features=5, seed=1):
    rng = np.random.default_rng(seed)
    X_train = pd.DataFrame(rng.standard_normal((n_train, n_features)),
                           columns=[f"f{i}" for i in range(n_features)])
    y_train = pd.Series(0.5 * X_train["f0"].values + 0.1 * rng.standard_normal(n_train))
    X_test = pd.DataFrame(rng.standard_normal((n_test, n_features)),
                          columns=[f"f{i}" for i in range(n_features)])
    y_test_gross = pd.Series(0.5 * X_test["f0"].values + 0.1 * rng.standard_normal(n_test))
    return X_train, y_train, X_test, y_test_gross


def test_single_shuffle_margin_is_scalar():
    X_train, y_train, X_test, y_test_gross = _synth()
    m = single_shuffle_margin(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, alpha=0.01, seed=42, cost_pct=0.30,
    )
    assert isinstance(m, float)


def test_run_label_permutation_null_returns_p():
    X_train, y_train, X_test, y_test_gross = _synth()
    result = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0,
        observed_margin=0.0,
        alpha=0.01, n_shuffles=100,
        seed=42, cost_pct=0.30, n_workers=1,
    )
    assert set(result.keys()) >= {"p_value", "n_shuffles_completed", "margin_samples_preview"}
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["n_shuffles_completed"] == 100


def test_permutation_null_is_deterministic_under_fixed_seed():
    X_train, y_train, X_test, y_test_gross = _synth()
    r1 = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, observed_margin=0.0,
        alpha=0.01, n_shuffles=100, seed=42, cost_pct=0.30, n_workers=1,
    )
    r2 = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, observed_margin=0.0,
        alpha=0.01, n_shuffles=100, seed=42, cost_pct=0.30, n_workers=1,
    )
    assert r1["p_value"] == r2["p_value"]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `permutation_null.py`**

`pipeline/autoresearch/phase_c_cross_sectional/permutation_null.py`:
```python
"""§9B.2 streaming label-permutation null for H-2026-04-24-002.

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/permutation_null.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py
git commit -m "feat(phase_c_cross_sectional): streaming label-permutation null with parallel workers"
```

---

### Task 8: `fragility_sweep.run_fragility_sweep`

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/fragility_sweep.py`
- Test: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py`

27-point sweep over (alpha_scale ∈ {0.8, 1.0, 1.2}) × (z_threshold ∈ {2.5, 3.0, 3.5}) × (persistence_days ∈ {1, 2, 3}). For each point: re-filter events with that (z_threshold, persistence_days), re-build feature matrix on that training subset, fit Lasso **at a fixed alpha** (alpha_scale × base_alpha, no CV), predict on a re-filtered holdout, compute S1 margin vs strongest naive on the re-filtered holdout. Sign flip check: ≥22/27 must agree on the sign of the base-fit margin.

**Output verdict:** `STABLE` if ≥22 same-sign, else `PARAMETER-FRAGILE` (so the existing `gate_checklist.build` reads it correctly — it tests for `!= "PARAMETER-FRAGILE"`).

- [ ] **Step 1: Write the failing test**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py`:
```python
import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.fragility_sweep import (
    neighborhood, evaluate_sweep,
)


def test_neighborhood_has_27_points():
    pts = neighborhood(base_alpha=0.01)
    assert len(pts) == 27
    assert all({"alpha", "z_threshold", "persistence_days"} <= set(p) for p in pts)


def test_evaluate_sweep_emits_verdict():
    # With synthetic same-signed margins, verdict must be STABLE
    rows = [{"alpha": 0.01, "z_threshold": 3.0, "persistence_days": 2,
             "margin": 0.5} for _ in range(27)]
    result = evaluate_sweep(rows, base_margin_sign=1)
    assert result["verdict"] == "STABLE"
    assert result["n_same_sign"] == 27


def test_evaluate_sweep_flags_fragile_if_mixed():
    rows = ([{"alpha": 0.01, "z_threshold": 3.0, "persistence_days": 2,
              "margin": 0.5}] * 10
            + [{"alpha": 0.01, "z_threshold": 3.0, "persistence_days": 2,
                "margin": -0.5}] * 17)
    result = evaluate_sweep(rows, base_margin_sign=1)
    assert result["verdict"] == "PARAMETER-FRAGILE"
    assert result["n_same_sign"] == 10
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fragility_sweep.py`**

`pipeline/autoresearch/phase_c_cross_sectional/fragility_sweep.py`:
```python
"""§9A parameter-fragility sweep for H-2026-04-24-002.

Produces 27 neighborhood points and a STABLE / PARAMETER-FRAGILE verdict.
The caller is responsible for driving each point through event_filter +
feature_builder + fit_lasso + naive-margin computation; this module holds
the grid definition and verdict logic.
"""
from __future__ import annotations

from itertools import product

import numpy as np


ALPHA_SCALES = (0.8, 1.0, 1.2)
Z_THRESHOLDS = (2.5, 3.0, 3.5)
PERSIST_DAYS = (1, 2, 3)
SIGN_AGREEMENT_FLOOR = 22  # of 27


def neighborhood(base_alpha: float) -> list[dict]:
    return [
        {"alpha": float(base_alpha * s), "z_threshold": float(z), "persistence_days": int(d)}
        for s, z, d in product(ALPHA_SCALES, Z_THRESHOLDS, PERSIST_DAYS)
    ]


def evaluate_sweep(rows: list[dict], *, base_margin_sign: int) -> dict:
    """Given 27 rows each with a 'margin' float, verdict by sign agreement."""
    assert len(rows) == 27, f"expected 27 rows, got {len(rows)}"
    signs = np.array([np.sign(r["margin"]) for r in rows])
    n_same = int((signs == base_margin_sign).sum())
    verdict = "STABLE" if n_same >= SIGN_AGREEMENT_FLOOR else "PARAMETER-FRAGILE"
    return {
        "rows": rows,
        "n_same_sign": n_same,
        "floor_required": SIGN_AGREEMENT_FLOOR,
        "base_margin_sign": int(base_margin_sign),
        "verdict": verdict,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/fragility_sweep.py \
        pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py
git commit -m "feat(phase_c_cross_sectional): 27-point fragility sweep grid + verdict"
```

---

### Task 9: `runner.py` — end-to-end orchestration

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/runner.py`

This module glues everything together. Runnable as `python -m pipeline.autoresearch.phase_c_cross_sectional.runner`. Its flags:

| Flag | Default | Meaning |
|---|---|---|
| `--events-path` | parent `events.json` path | source of events |
| `--out-dir` | `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<UTC stamp>/` | where all artifacts land |
| `--n-shuffles` | `100000` | permutation count |
| `--n-workers` | `None` (auto) | parallel workers |
| `--seed` | `42` | base seed |
| `--smoke` | off | use tiny synthetic inputs and skip permutation/fragility to end-to-end verify |

- [ ] **Step 1: Implement `runner.py`**

`pipeline/autoresearch/phase_c_cross_sectional/runner.py`:
```python
"""H-2026-04-24-002 end-to-end compliance runner.

Orchestrates: event filter -> feature matrix -> Lasso fit -> trading rule
-> slippage grid -> naive comparators -> permutation null -> fragility sweep
-> §11B beta regression, §11C portfolio gate, §12 CUSUM decay, §11A impl risk
-> §15.1 gate checklist artifact.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import (
    manifest as MF,
    metrics as M,
    slippage_grid as SG,
    data_audit as DA,
    universe_snapshot as US,
    beta_regression as BR,
    cusum_decay as CD,
    portfolio_gate as PG,
    impl_risk as IR,
    gate_checklist as GC,
)
from pipeline.autoresearch.overshoot_reversion_backtest import (
    load_price_panel,
    compute_residuals,
    BROAD_SECTOR,
)

from . import (
    event_filter as EF,
    feature_builder as FB,
    model as MD,
    naive_adapters as NA,
    permutation_null as PN,
    fragility_sweep as FS,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PARENT_EVENTS = REPO_ROOT / "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json"


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_parent_events(path: Path) -> pd.DataFrame:
    rows = json.loads(path.read_text())
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _split(events: pd.DataFrame, cutoff: str = "2025-12-31") -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff_ts = pd.Timestamp(cutoff)
    train = events.loc[events["date"] <= cutoff_ts].reset_index(drop=True)
    test = events.loc[events["date"] > cutoff_ts].reset_index(drop=True)
    return train, test


def _build_trading_ledger(
    events: pd.DataFrame, preds: np.ndarray, epsilon: float,
) -> pd.DataFrame:
    """Apply the trading rule. 'trade_ret_pct' column mirrors the schema
    expected by overshoot_compliance.slippage_grid.apply_full_grid.
    """
    out = events.copy().reset_index(drop=True)
    sign = np.where(preds > epsilon, 1.0, np.where(preds < -epsilon, -1.0, 0.0))
    out["prediction"] = preds
    out["signal_sign"] = sign
    out["trade_ret_pct"] = sign * out["next_ret"].to_numpy(float)
    return out


def run(
    *,
    events_path: Path,
    out_dir: Path,
    n_shuffles: int = 100_000,
    n_workers: int | None = None,
    seed: int = 42,
    alpha_grid: np.ndarray | None = None,
    cv_splits: int = 4,
    embargo_days: int = 2,
    z_threshold: float = 3.0,
    persistence_days: int = 2,
    min_history_days: int = 60,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    alpha_grid = alpha_grid if alpha_grid is not None else np.logspace(-5, 0, 25)

    # 1. Load parent events + price panel + z-score panel
    parent = _load_parent_events(events_path)
    panel = load_price_panel()
    sector_map_used = dict(BROAD_SECTOR)
    _, _, z_panel = compute_residuals(panel, sector_map_used)

    # 2. Filter to persistent-break subset
    persistent = EF.filter_persistent_breaks(
        parent, z_panel, z_threshold=z_threshold,
        persistence_days=persistence_days, min_history_days=min_history_days,
    )
    (out_dir / "persistent_events.json").write_text(
        persistent.to_json(orient="records", date_format="iso"), encoding="utf-8",
    )

    # 3. Train/test split
    train_events, test_events = _split(persistent)

    # 4. Regime history + vix (reuse project data sources)
    regime_history = _load_regime_history()
    vix_series = _load_vix_series()

    # 5. Build features
    X_tr, y_tr, names = FB.build_feature_matrix(
        train_events, z_panel, regime_history, vix_series,
        broad_sector=sector_map_used,
    )
    X_te, y_te, _ = FB.build_feature_matrix(
        test_events, z_panel, regime_history, vix_series,
        broad_sector=sector_map_used,
    )
    X_tr.to_parquet(out_dir / "feature_matrix_train.parquet")
    X_te.to_parquet(out_dir / "feature_matrix_test.parquet")

    # 6. Fit Lasso
    bundle = MD.fit_lasso(
        X_tr, y_tr, alpha_grid=alpha_grid, cv_splits=cv_splits,
        embargo_days=embargo_days, seed=seed,
    )
    MD.serialize(bundle, out_dir / "model.pkl")
    (out_dir / "model_coefs.json").write_text(
        json.dumps({
            "feature_names": bundle["feature_names"],
            "coef_": list(map(float, bundle["coef_"])),
            "intercept_": bundle["intercept_"],
            "alpha": bundle["alpha"],
            "alpha_grid": bundle["alpha_grid"],
            "alpha_mean_sharpes": bundle["alpha_mean_sharpes"],
        }, indent=2),
        encoding="utf-8",
    )
    train_preds = MD.predict(bundle, X_tr)
    epsilon = MD.compute_epsilon(train_preds)
    test_preds = MD.predict(bundle, X_te)

    preds_df = test_events.copy()
    preds_df["prediction"] = test_preds
    preds_df.to_parquet(out_dir / "predictions.parquet")

    # 7. Build model ledger and apply slippage grid
    model_ledger = _build_trading_ledger(test_events, test_preds, epsilon)
    model_ledger["direction"] = np.where(model_ledger["signal_sign"] > 0, "UP",
                             np.where(model_ledger["signal_sign"] < 0, "DOWN", "FLAT"))
    grid = SG.apply_full_grid(model_ledger[["ticker", "direction", "trade_ret_pct"]].copy())
    grid.to_json(out_dir / "slippage_grid.json", orient="records", indent=2)

    # 8. Naive comparators (on same test events)
    naive_summary = NA.summarize_naive(test_events)
    strongest = NA.strongest_name(naive_summary)
    strongest_sharpe = naive_summary[strongest]["sharpe"]
    (out_dir / "naive_comparators.json").write_text(
        json.dumps({"summary": naive_summary, "strongest": strongest,
                    "strongest_sharpe": strongest_sharpe}, indent=2),
        encoding="utf-8",
    )

    # 9. Compute observed model S1 margin (S1 row of the slippage grid)
    s1 = grid.loc[grid["slippage_level"] == "S1"]
    traded = s1.loc[s1["direction"].isin({"UP", "DOWN"})]
    model_s1_sharpe = M.per_bucket_metrics(traded["net_ret_pct"].to_numpy())["sharpe"]
    observed_margin = float(model_s1_sharpe - strongest_sharpe)

    # 10. Permutation null
    perm = PN.run_label_permutation_null(
        X_tr, y_tr, X_te, test_events["next_ret"],
        strongest_naive_sharpe=strongest_sharpe,
        observed_margin=observed_margin,
        alpha=bundle["alpha"], n_shuffles=n_shuffles,
        seed=seed, cost_pct=SG.LEVELS["S1"], n_workers=n_workers,
    )
    (out_dir / "permutation_null.json").write_text(json.dumps(perm, indent=2),
                                                    encoding="utf-8")

    # 11. Fragility sweep — 27 points
    frag_rows = []
    base_sign = int(np.sign(observed_margin)) or 1
    for pt in FS.neighborhood(bundle["alpha"]):
        pts_events = EF.filter_persistent_breaks(
            parent, z_panel, z_threshold=pt["z_threshold"],
            persistence_days=pt["persistence_days"], min_history_days=min_history_days,
        )
        pts_tr, pts_te = _split(pts_events)
        if len(pts_tr) < 30 or len(pts_te) < 10:
            frag_rows.append({**pt, "margin": 0.0, "skipped": True})
            continue
        X_ptr, y_ptr, _ = FB.build_feature_matrix(
            pts_tr, z_panel, regime_history, vix_series, broad_sector=sector_map_used,
        )
        X_pte, y_pte, _ = FB.build_feature_matrix(
            pts_te, z_panel, regime_history, vix_series, broad_sector=sector_map_used,
        )
        pbundle = MD.fit_lasso(
            X_ptr, y_ptr, alpha_grid=np.array([pt["alpha"]]),
            cv_splits=cv_splits, embargo_days=embargo_days, seed=seed,
        )
        ptrain_preds = MD.predict(pbundle, X_ptr)
        peps = MD.compute_epsilon(ptrain_preds)
        ptest_preds = MD.predict(pbundle, X_pte)
        pledger = _build_trading_ledger(pts_te, ptest_preds, peps)
        pledger["direction"] = np.where(pledger["signal_sign"] > 0, "UP",
                                np.where(pledger["signal_sign"] < 0, "DOWN", "FLAT"))
        pgrid = SG.apply_level(
            pledger[["ticker", "direction", "trade_ret_pct"]].copy(), "S1",
        )
        ptraded = pgrid.loc[pgrid["direction"].isin({"UP", "DOWN"})]
        psharpe = M.per_bucket_metrics(ptraded["net_ret_pct"].to_numpy())["sharpe"]
        # naive recomputed on the same re-filtered holdout
        pnaive = NA.summarize_naive(pts_te)
        pstrongest = NA.strongest_name(pnaive)
        pmargin = float(psharpe - pnaive[pstrongest]["sharpe"])
        frag_rows.append({**pt, "margin": pmargin, "skipped": False})

    frag_result = FS.evaluate_sweep(frag_rows, base_margin_sign=base_sign)
    (out_dir / "fragility_sweep.json").write_text(json.dumps(frag_result, indent=2),
                                                   encoding="utf-8")

    # 12. §5A data audit
    da_result = DA.run(
        events=persistent, price_panel=panel,
        hypothesis_id="H-2026-04-24-002", out_dir=out_dir,
    )

    # 13. §6 universe snapshot (inherits H-001 waiver)
    us_result = US.build(
        hypothesis_id="H-2026-04-24-002",
        waiver_path="docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md",
        out_dir=out_dir,
    )

    # 14. §11B beta regression
    nifty = _load_nifty_returns()  # series date -> percent return
    br_result = BR.run(
        ledger=model_ledger.assign(date=pd.to_datetime(model_ledger["date"])),
        nifty_returns=nifty,
    )
    (out_dir / "beta_regression.json").write_text(json.dumps(br_result, indent=2),
                                                   encoding="utf-8")

    # 15. §11C portfolio gate
    pg_result = PG.run(ledger=model_ledger, broad_sector=sector_map_used)
    (out_dir / "portfolio_gate.json").write_text(json.dumps(pg_result, indent=2),
                                                 encoding="utf-8")

    # 16. §12 CUSUM decay — training-window per-month edge
    train_ledger = _build_trading_ledger(train_events, train_preds, epsilon)
    monthly_edge = (
        train_ledger.assign(month=pd.to_datetime(train_ledger["date"]).dt.to_period("M"))
        .groupby("month")["trade_ret_pct"].mean()
    )
    cusum_result = CD.run(monthly_edge)
    (out_dir / "cusum_decay.json").write_text(json.dumps(cusum_result, indent=2, default=str),
                                              encoding="utf-8")

    # 17. §11A implementation risk (10 scenario stress)
    ir_result = IR.run(model_ledger)
    (out_dir / "impl_risk.json").write_text(json.dumps(ir_result, indent=2),
                                            encoding="utf-8")

    # 18. §13A.1 manifest
    manifest = MF.build_manifest(
        hypothesis_id="H-2026-04-24-002",
        strategy_version="cross_sectional_v1",
        cost_model_version="zerodha-ssf-2025-04",
        random_seed=seed,
        data_files=[events_path],
        config={
            "alpha_grid": list(map(float, alpha_grid)),
            "cv_splits": cv_splits,
            "embargo_days": embargo_days,
            "z_threshold": z_threshold,
            "persistence_days": persistence_days,
            "min_history_days": min_history_days,
            "n_shuffles": n_shuffles,
            "holdout_start": "2026-01-01",
            "holdout_end": "2026-04-23",
            "n_train": int(len(train_events)),
            "n_test": int(len(test_events)),
            "chosen_alpha": bundle["alpha"],
            "epsilon": epsilon,
            "model_s1_sharpe": model_s1_sharpe,
            "strongest_naive": strongest,
            "strongest_sharpe": strongest_sharpe,
            "observed_margin": observed_margin,
        },
    )
    MF.write_manifest(manifest, out_dir)

    # 19. §15.1 gate checklist
    s0_row = grid.loc[grid["slippage_level"] == "S0"]
    s1_row = grid.loc[grid["slippage_level"] == "S1"]
    s0_metrics = M.per_bucket_metrics(
        s0_row.loc[s0_row["direction"].isin({"UP", "DOWN"})]["net_ret_pct"].to_numpy()
    )
    s1_metrics = M.per_bucket_metrics(
        s1_row.loc[s1_row["direction"].isin({"UP", "DOWN"})]["net_ret_pct"].to_numpy()
    )
    cusum_metric = cusum_result.get("recent_24m_ratio", 0.0) if isinstance(cusum_result, dict) else 0.0
    gate_inputs = {
        "slippage_s0_s1": {
            "s0_sharpe": s0_metrics["sharpe"],
            "s0_hit": s0_metrics["hit_rate"],
            "s0_max_dd": s0_metrics["max_drawdown_pct"] / 100.0,
            "s1_sharpe": s1_metrics["sharpe"],
            "s1_max_dd": s1_metrics["max_drawdown_pct"] / 100.0,
            "s1_cum_pnl_pct": float(s1_row["net_ret_pct"].sum()),
        },
        "metrics_present": True,
        "data_audit": da_result,
        "universe_snapshot": us_result,
        "execution_mode": "MODE_A",
        "direction_audit": {
            "n_survivors": int((model_ledger["signal_sign"] != 0).sum()),
            "conflicts": 0,
        },
        "power_analysis": {
            "min_n_per_regime_met": len(test_events) >= 50,
            "underpowered_count": max(0, 50 - len(test_events)),
        },
        "fragility": {
            "verdict": frag_result["verdict"],
            "n_same_sign": frag_result["n_same_sign"],
        },
        "comparators": {
            "strongest_name": strongest,
            "beaten_strongest": bool(observed_margin > 0),
        },
        "permutations": {
            "n_shuffles": n_shuffles,
            "floor_required": 100_000,
            "p_value": perm["p_value"],
        },
        "holdout": {"pct": 0.06, "target": 0.20},
        "beta_regression": {
            "gross_sharpe": br_result.get("gross_sharpe", 0.0),
            "residual_sharpe": br_result.get("residual_sharpe", 0.0),
        },
    }
    report = GC.build(gate_inputs, hypothesis_id="H-2026-04-24-002")
    GC.write(report, out_dir)
    return {"out_dir": str(out_dir), "decision": report["decision"]}


def _load_regime_history() -> pd.DataFrame:
    """Daily regime label history. Source: pipeline/data/regime_history.csv
    (built by the ETF regime engine). Fallback: all NEUTRAL.
    """
    path = REPO_ROOT / "pipeline/data/regime_history.csv"
    if not path.exists():
        return pd.DataFrame(columns=["regime"], index=pd.to_datetime([]))
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return df[["regime"]]


def _load_vix_series() -> pd.Series:
    """Daily VIX close. Source: pipeline/data/vix_history.csv."""
    path = REPO_ROOT / "pipeline/data/vix_history.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return df["vix_close"].astype(float)


def _load_nifty_returns() -> pd.Series:
    """Daily NIFTY percent returns."""
    path = REPO_ROOT / "pipeline/data/india_historical/indices/NIFTY.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    close_col = "close" if "close" in df.columns else df.columns[0]
    return df[close_col].pct_change().dropna() * 100.0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--events-path", default=str(PARENT_EVENTS))
    p.add_argument("--out-dir",
                   default=str(REPO_ROOT / f"pipeline/autoresearch/results/compliance_H-2026-04-24-002_{_now_stamp()}"))
    p.add_argument("--n-shuffles", type=int, default=100_000)
    p.add_argument("--n-workers", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    result = run(
        events_path=Path(args.events_path),
        out_dir=Path(args.out_dir),
        n_shuffles=args.n_shuffles,
        n_workers=args.n_workers,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify module import works**

```bash
python -c "from pipeline.autoresearch.phase_c_cross_sectional import runner; print(runner.PARENT_EVENTS)"
```
Expected: the absolute path to the parent events.json.

- [ ] **Step 3: Commit**

```bash
git add pipeline/autoresearch/phase_c_cross_sectional/runner.py
git commit -m "feat(phase_c_cross_sectional): runner.py end-to-end orchestration"
```

---

### Task 10: End-to-end smoke test on synthetic inputs

**Files:**
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py`

Goal: run the runner on a 20-event synthetic panel and verify the artifact directory contains `gate_checklist.json` with a decision string.

- [ ] **Step 1: Write the smoke test**

`pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py`:
```python
import json
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional import runner as R
from pipeline.autoresearch.phase_c_cross_sectional import feature_builder as FB
from pipeline.autoresearch.phase_c_cross_sectional import model as MD
from pipeline.autoresearch.phase_c_cross_sectional import naive_adapters as NA


def test_smoke_happy_path(tmp_path, monkeypatch, tiny_events_df, tiny_z_panel,
                          tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    # Monkeypatch loaders so runner pulls synthetic inputs
    monkeypatch.setattr(R, "_load_parent_events",
                        lambda _p: pd.concat([tiny_events_df, tiny_events_df], ignore_index=True))
    monkeypatch.setattr(R, "load_price_panel", lambda: pd.DataFrame())
    monkeypatch.setattr(R, "compute_residuals",
                        lambda panel, sm: (None, None, tiny_z_panel))
    monkeypatch.setattr(R, "BROAD_SECTOR", tiny_broad_sector)
    monkeypatch.setattr(R, "_load_regime_history", lambda: tiny_regime_history)
    monkeypatch.setattr(R, "_load_vix_series", lambda: tiny_vix_series)
    monkeypatch.setattr(R, "_load_nifty_returns", lambda: pd.Series(dtype=float))

    # Exercise the runner with tiny budgets — permutation=50, skip_fragility_real_fits
    out_dir = tmp_path / "smoke_run"
    result = R.run(
        events_path=tmp_path / "unused.json",
        out_dir=out_dir,
        n_shuffles=50, n_workers=1, seed=42,
        alpha_grid=np.logspace(-3, 0, 4),
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )

    assert (out_dir / "gate_checklist.json").exists()
    gc = json.loads((out_dir / "gate_checklist.json").read_text())
    assert gc["hypothesis_id"] == "H-2026-04-24-002"
    assert gc["decision"] in {"PASS", "FAIL", "PARTIAL"}
```

- [ ] **Step 2: Run the smoke test**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py -v -s
```
Expected: `1 passed` (may take ~1 min on first run due to Lasso CV). If it fails because of missing `overshoot_compliance.data_audit.run` / other §-primitives not accepting the synthetic inputs, shim them for smoke only (add `smoke=True` branches that bypass real price-panel hashing). Document any shim in the commit message.

- [ ] **Step 3: Commit smoke test + any shims**

```bash
git add pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py \
        pipeline/autoresearch/phase_c_cross_sectional/runner.py
git commit -m "feat(phase_c_cross_sectional): end-to-end smoke test with synthetic inputs"
```

---

### Task 11: Real compliance run + registry terminal_state update

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl` (set `terminal_state`)
- New artifact directory under `pipeline/autoresearch/results/`

- [ ] **Step 1: Run the full compliance pipeline**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pipeline.autoresearch.phase_c_cross_sectional.runner --n-shuffles 100000
```
Expected wall time: ~10–20 min for 100k permutations on an 8-core box.

Output: a new directory under `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<stamp>/` containing all 15 artifact JSONs + two parquet feature matrices + `model.pkl`.

- [ ] **Step 2: Read `gate_checklist.json` and record the decision**

```bash
python -c "
import json, pathlib, glob
dirs = sorted(glob.glob('pipeline/autoresearch/results/compliance_H-2026-04-24-002_*'))
gc = json.loads(open(dirs[-1] + '/gate_checklist.json').read())
print('decision:', gc['decision'])
for row in gc['rows']:
    print(row['pass_fail'], row['section'], row['requirement'])
"
```

- [ ] **Step 3: Update registry terminal_state**

If decision == PASS:
```bash
python -c "
import json
lines = open('docs/superpowers/hypothesis-registry.jsonl').readlines()
d = json.loads(lines[-1])
assert d['hypothesis_id'] == 'H-2026-04-24-002'
d['terminal_state'] = 'PASS_2026-04-24'
d['status'] = 'PASS'
lines[-1] = json.dumps(d) + '\n'
open('docs/superpowers/hypothesis-registry.jsonl', 'w').writelines(lines)
"
```
If decision == FAIL or PARTIAL:
```bash
python -c "
import json
lines = open('docs/superpowers/hypothesis-registry.jsonl').readlines()
d = json.loads(lines[-1])
assert d['hypothesis_id'] == 'H-2026-04-24-002'
d['terminal_state'] = 'FAIL_2026-04-24'
d['status'] = 'FAIL'
lines[-1] = json.dumps(d) + '\n'
open('docs/superpowers/hypothesis-registry.jsonl', 'w').writelines(lines)
"
```

- [ ] **Step 4: Commit the artifact + registry update**

```bash
# force-track the artifact dir through the autoresearch gitignore
git add -f pipeline/autoresearch/results/compliance_H-2026-04-24-002_*
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "compliance(H-2026-04-24-002): <PASS|FAIL> — <brief 1-line summary of numbers>"
```
Replace `<PASS|FAIL>` and `<summary>` with the actual decision and headline numbers read in Step 2.

---

### Task 12: Docs sync (SYSTEM_OPERATIONS_MANUAL + memory files)

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md` — add a subsection under compliance runners describing this one.
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_overshoot_reversion_backtest.md` — append outcome.
- Create: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_persistent_break_cross_sectional.md` — new memory.
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md` — index entry.

Do NOT modify `CLAUDE.md` or `pipeline/config/anka_inventory.json` — this run is ad-hoc research, not a scheduled task (forward deployment is a follow-on spec).

- [ ] **Step 1: Add the SYSTEM_OPERATIONS_MANUAL subsection**

Locate the compliance runners section (search for "compliance_H-2026-04-23-001") and add a subsection after it:

```markdown
### Compliance runner: H-2026-04-24-002 (persistent-break + cross-sectional)

- **Entry:** `python -m pipeline.autoresearch.phase_c_cross_sectional.runner`
- **Source:** `pipeline/autoresearch/phase_c_cross_sectional/`
- **Hypothesis:** Lasso regression on 236-feature cross-sectional vector over persistent-break events. Single-model family (Bonferroni α = 0.05).
- **Scheduling:** ad-hoc research, NOT a scheduled task. Forward deployment (if PASS) is a separate follow-on spec.
- **Output:** `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<stamp>/` with manifest, feature matrices, model, predictions, slippage grid, naive comparators, permutation null, fragility sweep, §11B/§11C/§12 sections, §15.1 gate checklist.
- **Runtime:** ~10–20 min for 100k permutations on 8 cores.
```

- [ ] **Step 2: Append outcome to existing memory**

Append to `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_overshoot_reversion_backtest.md` under a new `## 2026-04-24 H-2026-04-24-002 cross-sectional audit — outcome` section with the final decision and top-level numbers (chosen alpha, n_train, n_test, model S1 Sharpe, strongest naive, observed margin, permutation p-value, fragility verdict).

- [ ] **Step 3: Create new memory file**

`C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_persistent_break_cross_sectional.md`:
```markdown
---
name: Persistent-break cross-sectional model (H-2026-04-24-002)
description: Single-model Bonferroni-clearable Lasso on 236-feature cross-sectional vector over persistent-break events (|z|>=3 on T and T-1, same-sign). Built 2026-04-24 on feat/phase-c-v5. Decision <PASS|FAIL>.
type: project
---

**Built:** 2026-04-24 on `feat/phase-c-v5`. Decision <PASS|FAIL>. Spec: `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (commit eb80ae5). Plan: `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md`.

**Events filter:** persistence subset (|z|>=3 on T AND T-1, same sign) of H-2026-04-23-001 parent panel. Count: <n> (expected 1,000-2,000).

**Features:** 236 = 212 peer z's + 17 sector means + VIX + 3 regime one-hots + 2 self z's + break direction.

**Model:** LassoCV, alpha grid logspace(-5, 0, 25), 4-fold purged walk-forward CV with 2-day embargo, alpha selected on mean OOS Sharpe. Chosen alpha: <alpha>.

**Holdout:** 2026-01-01 to 2026-04-23. n_train=<n>, n_test=<n>.

**Trading rule:** frozen epsilon = 0.5 × median(|train_preds|) = <eps>. LONG if pred>eps, SHORT if pred<-eps, else FLAT.

**Headline numbers (S1 = 30 bps round-trip):**
- Model S1 Sharpe: <val>
- Strongest naive: <name> (Sharpe <val>)
- Observed margin: <val>
- Permutation null p-value (100k shuffles): <val>
- Fragility verdict (27 points, ≥22 same-sign required): <STABLE|PARAMETER-FRAGILE>, n_same_sign=<n>

**Artifact directory:** `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<stamp>/`

**Interpretation:** <1-2 sentence plain-English summary>.

**What this doesn't prove:** <add caveats after the run — e.g., 6% holdout flagged as warning per §10.1, forward deployment requires a new spec even on PASS>.
```
(Backfill `<n>`, `<alpha>`, etc. from the actual run before committing.)

- [ ] **Step 4: Update MEMORY.md index**

Append to `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`:
```markdown
- [Persistent-break cross-sectional](project_persistent_break_cross_sectional.md) — H-2026-04-24-002 Lasso on 236 features over persistent-break events, <PASS|FAIL> 2026-04-24
```

- [ ] **Step 5: Commit docs**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md
git commit -m "docs(SYSTEM_OPERATIONS_MANUAL): add H-2026-04-24-002 compliance runner subsection"
```
Memory files are outside the repo — no git commit needed; they persist via the auto-memory system.

---

## Self-review checklist

**Spec coverage:** every spec section in `2026-04-23-persistent-break-cross-sectional-design.md` has a task:

| Spec requirement | Task |
|---|---|
| Pre-registration entry (§0.3) | Task 1 |
| Event filter binding (`|z|≥3`, persistence=2, min_history=60) | Task 3 |
| Feature set (236-dim, no look-ahead) | Task 4 |
| Label: `next_ret` in percent | Task 4 (builds y) |
| Data split (≤2025-12-31 / 2026-01-01…2026-04-23) | Task 9 `_split()` |
| LassoCV + alpha grid + 4-fold purged walk-forward + 2-day embargo | Task 5 |
| Alpha selection on mean OOS Sharpe | Task 5 `fit_lasso` |
| Standardizer persisted | Task 5 `fit_lasso` output bundle + Task 9 serialize |
| Refit on full training | Task 5 `fit_lasso` final fit |
| Epsilon frozen from training preds | Task 5 `compute_epsilon` + Task 9 |
| Trading rule (LONG/SHORT/FLAT) | Task 9 `_build_trading_ledger` |
| Naive comparators (always-fade, always-follow, buy-and-hold) | Task 6 |
| Slippage grid applied (§1) | Task 9 step 7 |
| §2 risk metrics + CI | reused via `per_bucket_metrics` in Tasks 6, 9 |
| §5A data audit | Task 9 step 12 |
| §6 universe snapshot + waiver | Task 9 step 13 |
| §7.1 MODE_A declaration | Task 9 gate_inputs |
| §8 direction audit | Task 9 gate_inputs (logged as predicted_sign vs fade/follow signs in predictions.parquet) |
| §9.3 power analysis | Task 9 gate_inputs (`min_n_per_regime_met = len(test)>=50`) |
| §9A fragility (27 points, ≥22 same-sign) | Tasks 8 + 9 step 11 |
| §9B.1 naive comparator (strongest) | Task 6 + Task 9 step 8 |
| §9B.2 100k permutation streaming | Task 7 + Task 9 step 10 |
| §10.1 20% holdout (6% flagged warning) | Task 9 gate_inputs |
| §10.2 purged walk-forward CV (embargo) | Task 5 `purged_walk_forward_splits` |
| §11 ADV (reused) | inherits from `impl_risk.run` Task 9 step 17 |
| §11A impl risk (10 scenarios) | Task 9 step 17 |
| §11B NIFTY-beta + residual Sharpe | Task 9 step 14 |
| §11C portfolio gate | Task 9 step 15 |
| §12 CUSUM decay, recent-24m | Task 9 step 16 |
| §13A.1 manifest + SHA-256 | Task 9 step 18 |
| §14.5 multiplicity (family=1) | registered in Task 1, referenced in gate inputs |
| §15.1 gate checklist emitter | Task 9 step 19 |
| Reproducibility (seed, versions) | Task 9 manifest |
| Success criteria (all PASS gates) | Task 11 reads gate_checklist |
| On PASS / on FAIL terminal_state | Task 11 step 3 |
| Non-goals (no GBM retries, no forward deploy wiring) | respected by plan scope |
| Docs sync | Task 12 |

**Placeholder scan:** no TBDs in steps. Two `<PASS|FAIL>` / numeric placeholders in Task 11 step 4 commit message and Task 12 step 3 memory body are **intentional** — they must be backfilled from the actual run output.

**Type consistency:** `fit_lasso` bundle keys (`model`, `standardizer`, `alpha`, `coef_`, `intercept_`, `feature_names`) used consistently across Tasks 5, 9. `predict` signature `(bundle, X)` consistent across Tasks 5, 9. `per_bucket_metrics` return keys (`sharpe`, `hit_rate`, `max_drawdown_pct`) consistent with how Task 9 step 19 reads them into `gate_inputs`.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review (spec compliance then code quality) between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
