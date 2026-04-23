# Persistent-Break v2 Cross-Sectional Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute hypothesis **H-2026-04-24-003** — re-parameterized persistent-break cross-sectional Lasso model after H-002 was abandoned at n=116 events, emitting a `gate_checklist.json` with an unambiguous PASS or FAIL verdict.

**Architecture:** Five new Python modules under `pipeline/autoresearch/phase_c_cross_sectional/` (three of them already scaffolded) that filter events → build features → fit LassoCV → evaluate naive comparators → run a streaming 100k-label-permutation null test → sweep 27 fragility points → compose the §15.1 gate checklist. The package imports — never rewrites — the existing `overshoot_compliance/` compliance primitives. All event inputs flow from the frozen parent panel `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json` (14,907 rows).

**Tech Stack:** Python 3.13, pandas, numpy, scikit-learn (LassoCV), pyarrow (parquet), pytest. No new external dependencies.

**Specs & prior artifacts:**
- **This plan's spec (frozen):** `docs/superpowers/specs/2026-04-24-persistent-break-v2-design.md` (commit `97054a7`).
- **Parent spec (inherited verbatim):** `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (commit `eb80ae5`).
- **Superseded v1 plan (code blocks reused by reference):** `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md` (commit `df63fe2`).
- **Already-shipped code (on `feat/phase-c-v5`):**
  - `82abbfc` — package skeleton + test fixtures (Task 2 of v1, **reuse as-is**).
  - `d786381` — `event_filter.py` + `test_event_filter.py` (Task 3 of v1, **signature change required** — see Task 3 below).
- **H-002 abandonment commit (audit trail):** `b50773f`.

---

## Pre-registration binding facts (read before any task)

| Parameter | Value |
|---|---|
| Event filter | `|z|≥3 on T` AND `|z|≥2 on T-1` AND same sign AND ≥60 non-NaN z through T-1 |
| Feature count | 236 = 212 peer z's + 17 sector means + 4 market context + 2 self z's + 1 break_direction |
| Label | `next_ret_pct_{i,T+1}` (percent, from events.json field `next_ret`) |
| Train split | 2021-04-23 → **2025-05-31** |
| Holdout split | **2025-06-01** → 2026-04-23 (~18%, expected ~57 events of 318 total) |
| Alpha grid | `numpy.logspace(-5, 0, 25)` |
| CV folds | 4 purged walk-forward with 2-day embargo |
| Alpha selection metric | mean OOS Sharpe across 4 CV folds |
| Epsilon | `0.5 × numpy.median(numpy.abs(train_predictions))`, frozen |
| Seed | 42 (base); `numpy.random.SeedSequence(42).spawn(100_000)` for permutations |
| Permutation count | 100,000 |
| Fragility grid | 27 = {α×0.8, α×1.0, α×1.2} × {z_current 2.5, 3.0, 3.5} × **{z_prior 1.5, 2.0, 2.5}** |
| Fragility pass rule | sign of (model − strongest-naive) Sharpe stable on ≥22/27 |
| Naive comparators | always-fade `-sign(today_resid)`; always-follow `sign(expected_return_pct)`; buy-and-hold `+1` |
| Cost model version | `zerodha-ssf-2025-04` |

**Events schema (from parent panel, unchanged):** `ticker`, `date`, `z`, `today_resid`, `today_ret`, `next_resid`, `next_ret`, `direction`, `actual_return_pct`, `expected_return_pct`.

**Slippage levels (from `overshoot_compliance/slippage_grid.py`, unchanged):** S0=0.10%, S1=0.30%, S2=0.50%, S3=0.70%.

---

## File structure

**Package `pipeline/autoresearch/phase_c_cross_sectional/`:**

| File | Status | Task |
|---|---|---|
| `__init__.py` | shipped at `82abbfc` | — |
| `event_filter.py` | shipped at `d786381`, **signature changes** | Task 3 |
| `feature_builder.py` | NEW | Task 4 |
| `model.py` | NEW | Task 5 |
| `naive_adapters.py` | NEW | Task 6 |
| `permutation_null.py` | NEW | Task 7 |
| `fragility_sweep.py` | NEW, **grid different from v1 plan** | Task 8 |
| `runner.py` | NEW, **holdout + fragility orchestration different** | Task 9 |

**Tests `pipeline/tests/autoresearch/phase_c_cross_sectional/`:**

| File | Status | Task |
|---|---|---|
| `__init__.py`, `conftest.py` | shipped at `82abbfc` | — |
| `test_event_filter.py` | shipped at `d786381`, **kwargs change + 2 new tests** | Task 3 |
| `test_feature_builder.py` | NEW | Task 4 |
| `test_model.py` | NEW | Task 5 |
| `test_naive_adapters.py` | NEW | Task 6 |
| `test_permutation_null.py` | NEW | Task 7 |
| `test_fragility_sweep.py` | NEW | Task 8 |
| `test_runner_smoke.py` | NEW | Task 10 |

**Runtime artifact directory:** `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<UTC stamp>/` with the 15 JSON artifacts + 2 parquet feature matrices + `model.pkl` listed in the v1 plan.

---

### Task 1: Pre-register hypothesis H-2026-04-24-003

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl` — append one line.

§0.3 requires registry entry before any new code consumes the v2 bindings. (Task 3 is the first code change that consumes them.)

- [ ] **Step 1: Append the registry line**

Write this script to `C:/tmp/register_h_2026_04_24_003.py`:

```python
"""Append H-2026-04-24-003 registration entry."""
import json
from pathlib import Path

REGISTRY = Path("C:/Users/Claude_Anka/askanka.com/docs/superpowers/hypothesis-registry.jsonl")

entry = {
    "hypothesis_id": "H-2026-04-24-003",
    "author": "bharatankaraju",
    "date_registered": "2026-04-24",
    "strategy_name": "phase-c-persistent-break-v2-cross-sectional",
    "strategy_class": "cross-sectional-linear-predictive",
    "description": (
        "v2 of H-2026-04-24-002 (abandoned at n=116). Lasso regression on "
        "236-dim cross-sectional feature vector over the asymmetric persistent-"
        "break subset (|z|>=3 on T AND |z|>=2 on T-1, same sign) of the "
        "14,907-event H-2026-04-23-001 parent panel. Single-model family: "
        "Bonferroni alpha = 0.05."
    ),
    "claimed_edge": {
        "metric": "holdout_S1_sharpe_margin_over_strongest_naive",
        "threshold_sign": "positive",
        "units": "sharpe_ratio",
        "slippage_level": "S1",
        "alpha_for_significance": 0.05,
        "multiplicity_correction": "none",
        "ci_level": 0.95,
        "notes": "Single-model family. Epsilon frozen on training-set prediction magnitudes.",
    },
    "universe": {
        "source": (
            "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/"
            "events.json filtered to v2 persistence subset"
        ),
        "point_in_time_compliant": False,
        "survivorship_status": "UNCORRECTED-INHERITED-FROM-H-2026-04-23-001",
        "n_tickers_current": 213,
        "coverage_ratio_estimate_pct_delisted": "<5% per H-2026-04-23-001 waiver",
    },
    "date_range": {
        "start": "2021-04-23",
        "end": "2025-05-31",
        "holdout_start": "2025-06-01",
        "holdout_end": "2026-04-23",
        "holdout_pct": 0.18,
        "notes": (
            "18% holdout clears Section 9.3 >=50-event gate; still PARTIAL vs "
            "Section 10.1 20% target but substantially reduced warning vs H-002's 6%."
        ),
    },
    "statistical_test": {
        "method": "label_permutation_null",
        "n_permutations_required": 100000,
        "rationale": "Single-model family means p_raw <= 0.05 is final; 100k shuffles per Section 9B.2.",
    },
    "hypothesis_family_scope": {
        "primary": "single-model",
        "primary_family_size_estimate": 1,
        "audit_scopes": [
            "strategy-class:cross-sectional-linear-predictive",
            "geometry:asymmetric-persistent-break-2day",
            "universe-scope:F&O-213",
        ],
        "notes": "Family size 1; no multiplicity correction.",
    },
    "execution_mode": "MODE_A_EOD_close_to_close",
    "power_analysis": {
        "required_n_holdout": 50,
        "expected_n_holdout": 57,
        "min_detectable_effect": (
            "to be computed from training-set prediction std before gate evaluation"
        ),
    },
    "pre_exploration_disclosure": (
        "H-2026-04-24-002 was abandoned at n=116. Before registering this successor, "
        "a count-only diagnostic measured 5 candidate persistence rules: "
        "ORIG=116, A=318, B=507, C=316, D=675. Rule A was chosen for matching the "
        "T-1-specific persistence intuition of the parent thesis, NOT for maximizing "
        "count. 18% holdout window was chosen to give rule A's 318 events a ~57-event "
        "holdout, clearing the Section 9.3 >=50 gate. NO model fits, predictions, or "
        "p-values were computed from any rule before this registration; only raw event "
        "counts observed."
    ),
    "status": "PRE_REGISTERED",
    "terminal_state": None,
    "git_commit_at_registration": None,
    "standards_version": "1.0_2026-04-23",
    "raw_bar_canonicity_policy": (
        "docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md v1.0 "
        "\u2014 MODE A T, T+1 execution window gate applies."
    ),
}

line = json.dumps(entry, ensure_ascii=False) + "\n"
with REGISTRY.open("a", encoding="utf-8") as fh:
    fh.write(line)

parsed = [json.loads(l) for l in REGISTRY.read_text(encoding="utf-8").splitlines()]
print(f"total lines: {len(parsed)}")
print(f"last hypothesis_id: {parsed[-1]['hypothesis_id']}")
print(f"last status: {parsed[-1]['status']}")
```

Run:
```bash
python C:/tmp/register_h_2026_04_24_003.py
```
Expected:
```
total lines: 6
last hypothesis_id: H-2026-04-24-003
last status: PRE_REGISTERED
```

- [ ] **Step 2: Commit registry entry**

```bash
git -C C:/Users/Claude_Anka/askanka.com add docs/superpowers/hypothesis-registry.jsonl
git -C C:/Users/Claude_Anka/askanka.com commit -m "register: H-2026-04-24-003 persistent-break v2 (PRE_REGISTERED)

v2 re-parameterization of H-002 (abandoned at n=116, b50773f). Asymmetric
persistence filter (|z|>=3 T AND |z|>=2 T-1, same-sign), 18% holdout window
(2025-06-01 -> 2026-04-23). All other bindings inherited from eb80ae5.
Spec: 97054a7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Backfill `git_commit_at_registration`**

Write this script to `C:/tmp/backfill_sha_003.py`:

```python
"""Backfill git_commit_at_registration for the H-003 registry entry."""
import json
import subprocess
from pathlib import Path

REGISTRY = Path("C:/Users/Claude_Anka/askanka.com/docs/superpowers/hypothesis-registry.jsonl")
sha = subprocess.check_output(
    ["git", "-C", "C:/Users/Claude_Anka/askanka.com", "rev-parse", "HEAD"],
    text=True,
).strip()
lines = REGISTRY.read_text(encoding="utf-8").splitlines(keepends=True)
last = json.loads(lines[-1])
assert last["hypothesis_id"] == "H-2026-04-24-003", f"got {last['hypothesis_id']}"
last["git_commit_at_registration"] = sha
lines[-1] = json.dumps(last, ensure_ascii=False) + "\n"
REGISTRY.write_text("".join(lines), encoding="utf-8")
print(f"backfilled: {sha}")
```

Run + commit:
```bash
python C:/tmp/backfill_sha_003.py
git -C C:/Users/Claude_Anka/askanka.com add docs/superpowers/hypothesis-registry.jsonl
git -C C:/Users/Claude_Anka/askanka.com commit -m "register: backfill H-2026-04-24-003 git_commit_at_registration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: SKIPPED — scaffold already shipped

Package `__init__.py`, test `__init__.py`, and `conftest.py` with 5 fixtures (`tiny_events_df`, `tiny_z_panel`, `tiny_regime_history`, `tiny_vix_series`, `tiny_broad_sector`) were shipped at commit `82abbfc` as part of the superseded v1 plan. No work required.

**Verification (optional):**
```bash
cd C:/Users/Claude_Anka/askanka.com
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/ --collect-only -q
```
Should list the five fixtures and the existing `test_event_filter.py::test_*` nodes. If not, stop and re-verify `82abbfc` is in the tree.

---

### Task 3: Extend `event_filter.filter_persistent_breaks` signature

**Files:**
- Modify: `pipeline/autoresearch/phase_c_cross_sectional/event_filter.py` (currently at `d786381`)
- Modify: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py` (currently at `d786381`)

The shipped v1 code takes a single `z_threshold` applied to both T and T-1. v2 splits this into `z_threshold_current` and `z_threshold_prior`.

- [ ] **Step 1: Update the 5 existing tests to use new kwargs**

Replace every occurrence of `z_threshold=3.0` with `z_threshold_current=3.0, z_threshold_prior=3.0` in `pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py`. Five call sites in total — use `Edit` with `replace_all=True`:

```
old: z_threshold=3.0, persistence_days=2, min_history_days=5
new: z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=2, min_history_days=5
```

And for the 3-day test:
```
old: z_threshold=3.0, persistence_days=3, min_history_days=5
new: z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=3, min_history_days=5
```

- [ ] **Step 2: Add two new tests for the asymmetric-threshold case**

Append to `test_event_filter.py`:

```python
def test_asymmetric_threshold_accepts_2sigma_prior(tiny_events_df, tiny_z_panel):
    """|z|>=3 on T with |z|>=2 on T-1 same-sign should now pass.

    HDFC 2024-03-20: T=+3.1, T-1=+3.0. Already passed under symmetric rule.
    Kept here as a regression baseline that the asymmetric rule is no stricter.
    """
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=2.0,
        persistence_days=2, min_history_days=5,
    )
    assert ((out["ticker"] == "HDFC") & (out["date"] == "2024-03-20")).any()


def test_asymmetric_threshold_expands_matches(tiny_events_df, tiny_z_panel):
    """Under symmetric |z|>=3 on both days only 3 events pass (see
    test_filter_keeps_three_persistent_events). Asymmetric |z|>=3 T with
    |z|>=2 T-1 should still include those 3 at minimum; the synthetic fixture
    is too small to add new matches but the output count must be >=3.
    """
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=2.0,
        persistence_days=2, min_history_days=5,
    )
    assert len(out) >= 3
```

- [ ] **Step 3: Run tests to verify failure on the new kwargs**

```bash
cd C:/Users/Claude_Anka/askanka.com
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py -v
```
Expected: all tests fail with `TypeError: filter_persistent_breaks() got an unexpected keyword argument 'z_threshold_current'` (or similar).

- [ ] **Step 4: Update `event_filter.py` signature**

In `pipeline/autoresearch/phase_c_cross_sectional/event_filter.py`, replace the function signature and body. The full replacement function:

```python
def filter_persistent_breaks(
    events_df: pd.DataFrame,
    z_panel: pd.DataFrame,
    *,
    z_threshold_current: float,
    z_threshold_prior: float,
    persistence_days: int,
    min_history_days: int = 60,
) -> pd.DataFrame:
    """Return the subset of events_df satisfying the v2 persistence filter.

    Parameters
    ----------
    events_df
        Parent panel events. Must have columns: ticker, date, z.
    z_panel
        Wide DataFrame (dates × tickers) of cross-sectional z-scores.
    z_threshold_current
        Minimum |z| on day T.
    z_threshold_prior
        Minimum |z| on days T-1 through T-(persistence_days-1).
    persistence_days
        Number of consecutive same-sign days required (including T).
    min_history_days
        Minimum non-NaN z observations through T-1 required for the ticker.

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
        if abs(z_t) < z_threshold_current:
            continue
        if tkr not in z_panel.columns:
            continue
        col = z_panel[tkr]
        col_through_t_minus_1 = col.loc[col.index < t].dropna()
        if col_through_t_minus_1.shape[0] < min_history_days:
            continue
        ok = True
        for k in range(1, persistence_days):
            if col_through_t_minus_1.shape[0] < k:
                ok = False
                break
            z_prev = float(col_through_t_minus_1.iloc[-k])
            if abs(z_prev) < z_threshold_prior or _sign(z_prev) != _sign(z_t):
                ok = False
                break
        if ok:
            keep_mask[i] = True

    return ev.loc[keep_mask].reset_index(drop=True)
```

Also update the module docstring:
```python
"""Persistent-break filter for H-2026-04-24-003 (asymmetric-threshold v2).

A v2-persistent break is an event on date T for ticker i where:
  |z_{i,T}|    >= z_threshold_current
  |z_{i,T-k}|  >= z_threshold_prior   for k in 1..persistence_days-1
  sign(z_{i,T}) == sign(z_{i,T-k})    for all k
  ticker i has >= min_history_days non-NaN z observations through T-1

The spec binds (z_threshold_current=3.0, z_threshold_prior=2.0, persistence_days=2,
min_history_days=60) for the primary run; fragility sweeps perturb the first two.
"""
```

**Note on history-bound fix:** this replacement also corrects the v1 deviation noted in the spec — `col_through_t_minus_1.shape[0]` uses rows *strictly before T* (matching the spec wording "through T-1"). On real data this doesn't change the count; on the synthetic fixture with `min_history_days=5` the `tiny_z_panel` has too few prior rows for most events — the existing tests already set `min_history_days=5` which is looser than the prior rows available. Verify in Step 5 that existing tests still pass under the stricter bound.

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py -v
```
Expected: `7 passed` (5 updated + 2 new).

If any test fails because the synthetic fixture's prior-row count drops below `min_history_days=5`, lower the test's `min_history_days` to `min_history_days=1` (still ensures the code path is exercised) — document the change in the commit message. Do NOT change `event_filter.py` to work around the fixture — the fixture is what should bend, not the spec-bound logic.

- [ ] **Step 6: Smoke-check against real parent panel**

Write this script to `C:/tmp/smoke_v2_event_count.py`:

```python
"""Smoke-check v2 persistence filter event count on the real parent panel."""
import json
import sys
from pathlib import Path

REPO = Path("C:/Users/Claude_Anka/askanka.com")
sys.path.insert(0, str(REPO))

import pandas as pd
from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
from pipeline.autoresearch.overshoot_reversion_backtest import (
    load_price_panel, load_sector_map, compute_residuals, _FNO_DIR,
)

events = pd.DataFrame(json.load(open(
    REPO / "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json"
)))
print(f"parent events: {len(events)}")

tickers = sorted(p.stem for p in _FNO_DIR.glob("*.csv"))
panel = load_price_panel(tickers)
sector_map = load_sector_map()
_, _, z_panel = compute_residuals(panel, sector_map)

kept = filter_persistent_breaks(
    events, z_panel,
    z_threshold_current=3.0, z_threshold_prior=2.0,
    persistence_days=2, min_history_days=60,
)
print(f"v2 persistent subset: {len(kept)}")
```

Run:
```bash
cd C:/Users/Claude_Anka/askanka.com
python C:/tmp/smoke_v2_event_count.py
```
Expected: `v2 persistent subset: 318` (±a few if z_panel re-computation has FP wobble; the brainstorming diagnostic measured 318 exactly). If result < 280 or > 360, stop and report as DONE_WITH_CONCERNS — something in the z-panel construction has drifted from the diagnostic.

- [ ] **Step 7: Commit**

```bash
git -C C:/Users/Claude_Anka/askanka.com add \
  pipeline/autoresearch/phase_c_cross_sectional/event_filter.py \
  pipeline/tests/autoresearch/phase_c_cross_sectional/test_event_filter.py
git -C C:/Users/Claude_Anka/askanka.com commit -m "feat(event_filter): asymmetric-threshold v2 signature for H-003

Replaces single z_threshold kwarg with z_threshold_current + z_threshold_prior.
Existing 5 tests updated (pass identical values for both kwargs, behavioral
equivalence preserved). 2 new tests cover asymmetric case (|z|>=3 T AND
|z|>=2 T-1). History-bound check corrected to rows strictly before T.

Smoke: real parent panel yields ~318 v2-persistent events (vs 116 under v1).

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 4: `feature_builder.build_feature_matrix` with TDD

**Inherited from v1 plan Task 4 (see `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md` at commit `df63fe2`, lines titled "Task 4: feature_builder.build_feature_matrix with TDD").**

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/feature_builder.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py`

**No deltas from v1.** 236-dim column schema (peer z's + sector means + vix + 3 regime one-hots + 2 self z's + break_direction), self-zeroing, sector <3 tickers → 0.0 imputation, label from `next_ret`.

**Steps (reuse v1 code blocks verbatim from `df63fe2`):**
- [ ] **Step 1:** Write 4 failing tests (`test_feature_shape`, `test_feature_no_lookahead_self_zero`, `test_break_direction_sign`, `test_label_matches_next_ret`) — code blocks in v1 plan Task 4 Step 1.
- [ ] **Step 2:** `pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py -v` expects `ModuleNotFoundError`.
- [ ] **Step 3:** Implement `feature_builder.py` with `build_feature_matrix(events_df, z_panel, regime_history, vix_series, *, broad_sector)` → `(X, y, feature_names)` — full code in v1 plan Task 4 Step 3.
- [ ] **Step 4:** `pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_feature_builder.py -v` expects `4 passed`.
- [ ] **Step 5:** Commit with message `feat(phase_c_cross_sectional): feature_builder.build_feature_matrix with TDD (v2, inherited from v1 plan)`.

The fixture calls in tests need updating — the v1 test code calls `filter_persistent_breaks(..., z_threshold=3.0, ...)` which is now invalid. Change those inline calls to `z_threshold_current=3.0, z_threshold_prior=3.0` for behavioral equivalence.

---

### Task 5: `model.fit_lasso` + predict + serialize + compute_epsilon with TDD

**Inherited from v1 plan Task 5 (at commit `df63fe2`, titled "Task 5: model (fit_lasso + predict + serialize + compute_epsilon) with TDD").**

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/model.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py`

**No deltas from v1.** LassoCV with purged walk-forward CV, alpha selected on mean OOS Sharpe (not R²), StandardScaler persisted, refit on full training, epsilon = 0.5 × median(|train_preds|) frozen.

**Steps (reuse v1 code blocks verbatim):**
- [ ] **Step 1:** Write 5 failing tests (`test_fit_lasso_runs_and_returns_bundle`, `test_predict_roundtrip`, `test_compute_epsilon_is_half_median_abs`, `test_serialize_roundtrip`, `test_purged_walk_forward_embargo`).
- [ ] **Step 2:** `pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py -v` expects `ModuleNotFoundError`.
- [ ] **Step 3:** Implement `model.py` with `fit_lasso`, `predict`, `compute_epsilon`, `serialize`, `load`, `purged_walk_forward_splits`.
- [ ] **Step 4:** `pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_model.py -v` expects `5 passed`.
- [ ] **Step 5:** Commit with message `feat(phase_c_cross_sectional): model.fit_lasso with purged walk-forward CV (v2, inherited)`.

---

### Task 6: `naive_adapters` (fade/follow/buy-and-hold) with TDD

**Inherited from v1 plan Task 6 (at commit `df63fe2`, titled "Task 6: naive_adapters (fade/follow/buy-and-hold) with TDD").**

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/naive_adapters.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_naive_adapters.py`

**No deltas from v1.** Three signed-return series: `always_fade` uses `-sign(today_resid)`, `always_follow` uses `sign(expected_return_pct)`, `buy_and_hold` is `+1`. `summarize_naive()` + `strongest_name()` helpers.

**Steps (reuse v1 code blocks verbatim):**
- [ ] **Step 1:** Write 4 failing tests (`test_always_fade_signs`, `test_always_follow_signs`, `test_buy_and_hold_sign`, `test_summarize_naive_suite_picks_strongest`).
- [ ] **Step 2:** `pytest ... test_naive_adapters.py -v` expects `ModuleNotFoundError`.
- [ ] **Step 3:** Implement `naive_adapters.py` with `always_fade`, `always_follow`, `buy_and_hold`, `summarize_naive`, `strongest_name`.
- [ ] **Step 4:** `pytest ... test_naive_adapters.py -v` expects `4 passed`.
- [ ] **Step 5:** Commit with message `feat(phase_c_cross_sectional): naive_adapters (v2, inherited)`.

---

### Task 7: `permutation_null.run_label_permutation_null` with TDD

**Inherited from v1 plan Task 7 (at commit `df63fe2`, titled "Task 7: permutation_null streaming 100k test with TDD").**

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/permutation_null.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_permutation_null.py`

**No deltas from v1.** Streaming label-permutation; each shuffle refits Lasso at fixed alpha, predicts on test, applies trading rule with per-shuffle epsilon, computes S1 margin vs strongest naive. ProcessPoolExecutor for parallelism. Deterministic under `SeedSequence(42).spawn(n_shuffles)`.

**Steps (reuse v1 code blocks verbatim):**
- [ ] **Step 1:** Write 3 failing tests (`test_single_shuffle_margin_is_scalar`, `test_run_label_permutation_null_returns_p`, `test_permutation_null_is_deterministic_under_fixed_seed`).
- [ ] **Step 2:** `pytest ... test_permutation_null.py -v` expects `ModuleNotFoundError`.
- [ ] **Step 3:** Implement `permutation_null.py` with `single_shuffle_margin` + `run_label_permutation_null` + `_worker`.
- [ ] **Step 4:** `pytest ... test_permutation_null.py -v` expects `3 passed`.
- [ ] **Step 5:** Commit with message `feat(phase_c_cross_sectional): permutation_null (v2, inherited)`.

---

### Task 8: `fragility_sweep` — 27-point grid with new prior-z dimension

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/fragility_sweep.py`
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py`

**Changed from v1:** the v1 plan used `PERSIST_DAYS = (1, 2, 3)` as the third grid axis. v2 replaces this with `Z_THRESHOLD_PRIOR_GRID = (1.5, 2.0, 2.5)`. `persistence_days` stays pinned at 2 for all 27 points.

- [ ] **Step 1: Write failing tests**

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
    for p in pts:
        assert {"alpha", "z_threshold_current", "z_threshold_prior"} <= set(p)


def test_neighborhood_uses_correct_prior_z_grid():
    pts = neighborhood(base_alpha=0.01)
    prior_zs = sorted({p["z_threshold_prior"] for p in pts})
    assert prior_zs == [1.5, 2.0, 2.5]


def test_neighborhood_uses_correct_current_z_grid():
    pts = neighborhood(base_alpha=0.01)
    current_zs = sorted({p["z_threshold_current"] for p in pts})
    assert current_zs == [2.5, 3.0, 3.5]


def test_neighborhood_alpha_scaling():
    pts = neighborhood(base_alpha=0.01)
    alphas = sorted({p["alpha"] for p in pts})
    # 0.8 * 0.01, 1.0 * 0.01, 1.2 * 0.01
    np.testing.assert_allclose(alphas, [0.008, 0.010, 0.012])


def test_evaluate_sweep_emits_verdict():
    rows = [{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
             "margin": 0.5} for _ in range(27)]
    result = evaluate_sweep(rows, base_margin_sign=1)
    assert result["verdict"] == "STABLE"
    assert result["n_same_sign"] == 27


def test_evaluate_sweep_flags_fragile_if_mixed():
    rows = ([{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
              "margin": 0.5}] * 10
            + [{"alpha": 0.01, "z_threshold_current": 3.0, "z_threshold_prior": 2.0,
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
"""§9A parameter-fragility sweep for H-2026-04-24-003 (v2 axis).

27 neighborhood points over {alpha_scale} × {z_threshold_current} ×
{z_threshold_prior}. persistence_days is pinned at 2. Verdict is STABLE if
>=22/27 agree on the sign of the base-fit (model - strongest_naive) margin,
else PARAMETER-FRAGILE.

The caller (runner.py) is responsible for driving each point through
event_filter + feature_builder + fit_lasso + naive-margin computation;
this module owns the grid definition and verdict logic.
"""
from __future__ import annotations

from itertools import product

import numpy as np


ALPHA_SCALES = (0.8, 1.0, 1.2)
Z_THRESHOLD_CURRENT_GRID = (2.5, 3.0, 3.5)
Z_THRESHOLD_PRIOR_GRID = (1.5, 2.0, 2.5)
SIGN_AGREEMENT_FLOOR = 22  # of 27


def neighborhood(base_alpha: float) -> list[dict]:
    return [
        {"alpha": float(base_alpha * s),
         "z_threshold_current": float(zc),
         "z_threshold_prior": float(zp)}
        for s, zc, zp in product(ALPHA_SCALES, Z_THRESHOLD_CURRENT_GRID, Z_THRESHOLD_PRIOR_GRID)
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

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git -C C:/Users/Claude_Anka/askanka.com add \
  pipeline/autoresearch/phase_c_cross_sectional/fragility_sweep.py \
  pipeline/tests/autoresearch/phase_c_cross_sectional/test_fragility_sweep.py
git -C C:/Users/Claude_Anka/askanka.com commit -m "feat(fragility_sweep): v2 27-point grid (alpha x z_current x z_prior)

Replaces the v1 plan's persistence_days grid axis with a prior-day z-threshold
axis {1.5, 2.0, 2.5} to test robustness to the new asymmetric-threshold
binding in H-2026-04-24-003. persistence_days is pinned at 2 for all points.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 9: `runner.py` end-to-end orchestration

**Files:**
- Create: `pipeline/autoresearch/phase_c_cross_sectional/runner.py`

Heavy file — ~300 lines. Structure is 95% identical to v1 plan Task 9 (`df63fe2`), but with two call-site changes driven by v2 bindings:

1. `TRAIN_END = "2025-05-31"` (was `"2025-12-31"`); test split is everything after that date.
2. Fragility orchestration loop calls `EF.filter_persistent_breaks(... z_threshold_current=pt["z_threshold_current"], z_threshold_prior=pt["z_threshold_prior"], persistence_days=2 ...)` instead of v1's `(z_threshold=pt["z_threshold"], persistence_days=pt["persistence_days"])`.

- [ ] **Step 1: Create `runner.py` following the v1 template**

Use the full code block from v1 plan Task 9 Step 1 (commit `df63fe2`) as the base. Apply these **three** exact changes:

**Change 1 — `_split` signature:**

v1 code:
```python
def _split(events: pd.DataFrame, cutoff: str = "2025-12-31") -> tuple[pd.DataFrame, pd.DataFrame]:
```

v2 code:
```python
def _split(events: pd.DataFrame, cutoff: str = "2025-05-31") -> tuple[pd.DataFrame, pd.DataFrame]:
```

**Change 2 — primary `run()` call site:**

v1 code (top of filter call in `run()`):
```python
persistent = EF.filter_persistent_breaks(
    parent, z_panel, z_threshold=z_threshold,
    persistence_days=persistence_days, min_history_days=min_history_days,
)
```

v2 code:
```python
persistent = EF.filter_persistent_breaks(
    parent, z_panel,
    z_threshold_current=z_threshold_current,
    z_threshold_prior=z_threshold_prior,
    persistence_days=persistence_days,
    min_history_days=min_history_days,
)
```

Also update the `run()` function signature to take `z_threshold_current=3.0, z_threshold_prior=2.0, persistence_days=2, min_history_days=60` in place of v1's `z_threshold=3.0, persistence_days=2, min_history_days=60`.

**Change 3 — fragility sweep orchestration:**

v1 code inside the `for pt in FS.neighborhood(bundle["alpha"]):` loop:
```python
pts_events = EF.filter_persistent_breaks(
    parent, z_panel, z_threshold=pt["z_threshold"],
    persistence_days=pt["persistence_days"], min_history_days=min_history_days,
)
```

v2 code:
```python
pts_events = EF.filter_persistent_breaks(
    parent, z_panel,
    z_threshold_current=pt["z_threshold_current"],
    z_threshold_prior=pt["z_threshold_prior"],
    persistence_days=2,
    min_history_days=min_history_days,
)
```

**Change 4 — hypothesis ID and manifest strategy_version:**

Every literal `"H-2026-04-24-002"` in the v1 runner becomes `"H-2026-04-24-003"`. Every `"cross_sectional_v1"` becomes `"cross_sectional_v2"`.

**Change 5 — artifact output directory:**

v1:
```python
REPO_ROOT / f"pipeline/autoresearch/results/compliance_H-2026-04-24-002_{_now_stamp()}"
```
v2:
```python
REPO_ROOT / f"pipeline/autoresearch/results/compliance_H-2026-04-24-003_{_now_stamp()}"
```

**Change 6 — manifest.config keys:**

Replace `"z_threshold": z_threshold` with `"z_threshold_current": z_threshold_current, "z_threshold_prior": z_threshold_prior`.

- [ ] **Step 2: Verify import works**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -c "from pipeline.autoresearch.phase_c_cross_sectional import runner; print(runner.PARENT_EVENTS); print(runner._split.__defaults__)"
```
Expected:
```
<absolute path to events.json>
('2025-05-31',)
```

- [ ] **Step 3: Commit**

```bash
git -C C:/Users/Claude_Anka/askanka.com add pipeline/autoresearch/phase_c_cross_sectional/runner.py
git -C C:/Users/Claude_Anka/askanka.com commit -m "feat(runner): v2 end-to-end orchestration for H-2026-04-24-003

Inherits the v1 runner template (df63fe2) with 6 call-site deltas:
train cutoff 2025-05-31, filter_persistent_breaks kwargs
(z_threshold_current, z_threshold_prior), fragility loop uses new dict
keys, hypothesis ID and artifact dir reflect H-003, manifest config
records both thresholds.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

### Task 10: End-to-end smoke test on synthetic panel

**Inherited from v1 plan Task 10 (at commit `df63fe2`, titled "Task 10: End-to-end smoke test on synthetic panel").**

**Files:**
- Create: `pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py`

**Structural deltas from v1:** the `R.run(...)` call passes `z_threshold_current=3.0, z_threshold_prior=3.0` (both equal to keep synthetic fixture's 3 persistent events in the filter), instead of v1's single `z_threshold=3.0`. Also `persistence_days=2` explicit. Tests assert `gate_checklist.json` has `hypothesis_id == "H-2026-04-24-003"`.

**Steps:**
- [ ] **Step 1:** Write smoke test — base code from v1 plan Task 10 Step 1 with the kwargs swap and the hypothesis-id assertion update.
- [ ] **Step 2:** `pytest pipeline/tests/autoresearch/phase_c_cross_sectional/test_runner_smoke.py -v -s` expects `1 passed` (may take ~1 min). If the `overshoot_compliance/*.run(...)` primitives reject synthetic inputs, add `smoke=True` shims in `runner.py` exactly as v1 plan Task 10 Step 2 describes.
- [ ] **Step 3:** Commit with message `feat(phase_c_cross_sectional): end-to-end smoke test for v2 (H-003)`.

---

### Task 11: Real 100k-permutation compliance run + registry terminal_state update

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl` (set H-003 `terminal_state`)
- New artifact directory: `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<stamp>/`

- [ ] **Step 1: Execute the full pipeline**

```bash
cd C:/Users/Claude_Anka/askanka.com
python -m pipeline.autoresearch.phase_c_cross_sectional.runner --n-shuffles 100000
```
Expected wall time: ~10–20 min for 100k permutations on 8 cores. On a smaller machine, pass `--n-workers 4` to cap parallelism.

Output: new directory `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<stamp>/` containing 15 artifact JSONs + 2 parquet feature matrices + `model.pkl`.

- [ ] **Step 2: Read `gate_checklist.json` and record the decision**

```bash
python -c "
import json, pathlib, glob
dirs = sorted(glob.glob('pipeline/autoresearch/results/compliance_H-2026-04-24-003_*'))
gc = json.loads(open(dirs[-1] + '/gate_checklist.json').read())
print('decision:', gc['decision'])
for row in gc['rows']:
    print(row['pass_fail'], row['section'], row['requirement'])
"
```

- [ ] **Step 3: Update registry terminal_state**

If `decision == "PASS"`:
```bash
python -c "
import json
lines = open('docs/superpowers/hypothesis-registry.jsonl').readlines()
d = json.loads(lines[-1])
assert d['hypothesis_id'] == 'H-2026-04-24-003'
d['terminal_state'] = 'PASS_2026-04-24'
d['status'] = 'PASS'
lines[-1] = json.dumps(d) + '\n'
open('docs/superpowers/hypothesis-registry.jsonl', 'w').writelines(lines)
"
```

If `decision == "FAIL"` or `"PARTIAL"`:
```bash
python -c "
import json
lines = open('docs/superpowers/hypothesis-registry.jsonl').readlines()
d = json.loads(lines[-1])
assert d['hypothesis_id'] == 'H-2026-04-24-003'
d['terminal_state'] = 'FAIL_2026-04-24'
d['status'] = 'FAIL'
lines[-1] = json.dumps(d) + '\n'
open('docs/superpowers/hypothesis-registry.jsonl', 'w').writelines(lines)
"
```

- [ ] **Step 4: Commit artifact directory and registry update**

```bash
git -C C:/Users/Claude_Anka/askanka.com add -f pipeline/autoresearch/results/compliance_H-2026-04-24-003_*
git -C C:/Users/Claude_Anka/askanka.com add docs/superpowers/hypothesis-registry.jsonl
git -C C:/Users/Claude_Anka/askanka.com commit -m "compliance(H-2026-04-24-003): <PASS|FAIL|PARTIAL> — <1-line summary of numbers>"
```
Replace `<PASS|FAIL|PARTIAL>` and `<summary>` with the actual decision and headline numbers (n_train, n_test, chosen_alpha, model_S1_sharpe, strongest_naive and its sharpe, observed_margin, permutation p_value, fragility verdict).

---

### Task 12: Docs sync (SYSTEM_OPERATIONS_MANUAL + memory files)

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_overshoot_reversion_backtest.md`
- Create: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_persistent_break_v2_cross_sectional.md`
- Modify: `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`

Do NOT modify `CLAUDE.md` or `pipeline/config/anka_inventory.json` — this run is ad-hoc research, not a scheduled task.

- [ ] **Step 1: Add SYSTEM_OPERATIONS_MANUAL subsection**

Locate "Compliance runner: H-2026-04-23-001" (search). After that subsection add:

```markdown
### Compliance runner: H-2026-04-24-003 (persistent-break v2 + cross-sectional)

- **Entry:** `python -m pipeline.autoresearch.phase_c_cross_sectional.runner`
- **Source:** `pipeline/autoresearch/phase_c_cross_sectional/`
- **Hypothesis:** v2 of H-2026-04-24-002. Lasso regression on 236-feature cross-sectional vector over asymmetric persistent-break events (`|z|≥3 on T AND |z|≥2 on T-1, same-sign`). Single-model family (Bonferroni α = 0.05).
- **Scheduling:** ad-hoc research, NOT a scheduled task.
- **Output:** `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<stamp>/` with manifest, feature matrices, model, predictions, slippage grid, naive comparators, permutation null, fragility sweep (α × z_current × z_prior grid), §11B/§11C/§12 sections, §15.1 gate checklist.
- **Runtime:** ~10–20 min for 100k permutations on 8 cores.
- **H-2026-04-24-002 (abandoned) and the superseded v1 plan are historical context only:** see registry line 5 (`b50773f`) and `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md`.
```

- [ ] **Step 2: Append outcome to existing memory**

Append a new section `## 2026-04-24 H-2026-04-24-003 cross-sectional v2 audit — outcome` to `project_overshoot_reversion_backtest.md` with the final decision and top-level numbers (chosen alpha, n_train, n_test, model S1 Sharpe, strongest naive + sharpe, observed margin, permutation p-value, fragility verdict).

- [ ] **Step 3: Create the v2 memory file**

`C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/project_persistent_break_v2_cross_sectional.md`:

```markdown
---
name: Persistent-break v2 cross-sectional model (H-2026-04-24-003)
description: Asymmetric-threshold Lasso on 236-feature cross-sectional vector. v2 after H-002 abandoned at n=116. Built 2026-04-24 on feat/phase-c-v5. Decision <PASS|FAIL|PARTIAL>.
type: project
---

**Built:** 2026-04-24 on `feat/phase-c-v5`. Decision <PASS|FAIL|PARTIAL>.

- **Spec:** `docs/superpowers/specs/2026-04-24-persistent-break-v2-design.md` (commit 97054a7).
- **Plan:** `docs/superpowers/plans/2026-04-24-persistent-break-v2.md`.
- **Parent spec (inherited):** `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (eb80ae5).
- **Superseded v1 plan:** `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md` (df63fe2). Superseded because H-002 abandoned at n=116 (b50773f).

**Event filter:** `|z|≥3 on T AND |z|≥2 on T-1, same-sign`. Expected ~318 events from parent panel; actual <n>.

**Features:** 236 = 212 peer z's + 17 sector means + VIX + 3 regime one-hots + 2 self z's + break direction.

**Model:** LassoCV, alpha grid logspace(-5, 0, 25), 4-fold purged walk-forward CV with 2-day embargo, alpha selected on mean OOS Sharpe. Chosen alpha: <alpha>.

**Holdout:** 2025-06-01 → 2026-04-23 (~18% of panel). n_train=<n>, n_test=<n>.

**Trading rule:** epsilon = 0.5 × median(|train_preds|) = <eps>. LONG if pred>eps, SHORT if pred<-eps, else FLAT.

**Headline numbers (S1 = 30 bps round-trip):**
- Model S1 Sharpe: <val>
- Strongest naive: <name> (Sharpe <val>)
- Observed margin: <val>
- Permutation null p-value (100k shuffles): <val>
- Fragility verdict (27 points, ≥22 same-sign required): <STABLE|PARAMETER-FRAGILE>, n_same_sign=<n>

**Artifact directory:** `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<stamp>/`

**Interpretation:** <1-2 sentence plain-English summary>.
```

Backfill `<n>`, `<alpha>`, etc. from the run before committing.

- [ ] **Step 4: Update MEMORY.md index**

Append to `C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`:
```markdown
- [Persistent-break v2 cross-sectional](project_persistent_break_v2_cross_sectional.md) — H-2026-04-24-003 asymmetric-threshold Lasso, <PASS|FAIL|PARTIAL> 2026-04-24
```

- [ ] **Step 5: Commit repo docs**

```bash
git -C C:/Users/Claude_Anka/askanka.com add docs/SYSTEM_OPERATIONS_MANUAL.md
git -C C:/Users/Claude_Anka/askanka.com commit -m "docs(SYSTEM_OPERATIONS_MANUAL): add H-2026-04-24-003 compliance runner subsection"
```

Memory files live outside the repo and persist automatically — no git commit needed for them.

---

## Self-review

**Spec coverage:** every binding in `2026-04-24-persistent-break-v2-design.md` (commit 97054a7) has a task:

| Spec requirement | Task |
|---|---|
| Pre-registration entry (§0.3) with rule-A disclosure | Task 1 |
| Event filter asymmetric binding (`|z|≥3` T, `|z|≥2` T-1) | Task 3 |
| 236-feature matrix (inherited v1) | Task 4 |
| Label = `next_ret_pct` | Task 4 (builds y) |
| Data split (train ≤ 2025-05-31, test 2025-06-01…2026-04-23) | Task 9 `_split()` default cutoff |
| LassoCV + 4-fold purged walk-forward + 2-day embargo | Task 5 |
| Alpha selection on mean OOS Sharpe | Task 5 |
| Standardizer persisted | Task 5 + Task 9 serialize |
| Refit on full training | Task 5 |
| Epsilon frozen from training preds | Task 5 `compute_epsilon` + Task 9 |
| Trading rule LONG/SHORT/FLAT | Task 9 ledger builder |
| Naive comparators | Task 6 |
| Slippage grid applied (§1) | Task 9 |
| §2 metrics + CI | Task 6/9 via `per_bucket_metrics` |
| §5A data audit | Task 9 |
| §6.1/§6.2 universe + waiver | Task 9 |
| §7.1 MODE_A declaration | Task 9 gate_inputs |
| §8 direction audit | Task 9 gate_inputs |
| §9.3 power (≥50 holdout events) | Task 9 gate_inputs + Task 11 verifies |
| §9A fragility (27 points α×z_current×z_prior, ≥22 same-sign) | Task 8 + Task 9 |
| §9B.1 naive comparator (strongest) | Task 6 + Task 9 |
| §9B.2 100k streaming permutation | Task 7 + Task 9 |
| §10.1 holdout PARTIAL note | Task 9 gate_inputs |
| §10.2 purged walk-forward CV (2-day embargo) | Task 5 |
| §11 ADV (reused) | Task 9 via `impl_risk.run` |
| §11A impl risk (10 scenarios) | Task 9 |
| §11B NIFTY-beta + residual Sharpe | Task 9 |
| §11C portfolio gate | Task 9 |
| §12 CUSUM decay | Task 9 |
| §13A.1 manifest + SHA-256 | Task 9 (uses `manifest.build_manifest`) |
| §14.5 multiplicity family=1 | Task 1 registers, Task 9 gate_inputs |
| §15.1 gate checklist | Task 9 |
| Reproducibility (seed=42, versions) | Task 9 manifest |
| Success criteria verification | Task 11 reads gate_checklist |
| PASS/FAIL terminal_state | Task 11 Step 3 |
| Docs sync | Task 12 |
| Scope non-goals | respected by plan scope |

**Placeholder scan:** `<PASS|FAIL|PARTIAL>`, `<n>`, `<alpha>`, etc. in Task 11 Step 4 commit message and Task 12 memory body are **intentional** — must be backfilled from actual run output. No other TBDs.

**Type consistency:** `filter_persistent_breaks` signature uses `z_threshold_current`, `z_threshold_prior`, `persistence_days`, `min_history_days` consistently across Tasks 3, 9, 10. `neighborhood()` returns dicts with keys `alpha`, `z_threshold_current`, `z_threshold_prior` — these match the keys Task 9's fragility loop reads. `per_bucket_metrics` return keys (`sharpe`, `hit_rate`, `max_drawdown_pct`) match how Task 9 gate_inputs reads them.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-24-persistent-break-v2.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, two-stage review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans.

**Which approach?**
