# Analysis Framework — How to Run a New Test

> **Purpose:** Pick this up cold and run a new analysis end-to-end in 30 minutes.
>
> Before you read this, scan: [`DATA_INVENTORY.md`](./DATA_INVENTORY.md) (what data we have) and [`ANALYSIS_CATALOG.md`](./ANALYSIS_CATALOG.md) (what's already running).

**Last revised:** 2026-04-29 (after the NEUTRAL VWAP filter shipped at 70% win rate).

## The standard recipe (every new analysis follows it)

```
   ┌───────────────────────┐
   │ 1. Hypothesis spec     │  docs/superpowers/specs/<date>-<name>-design.md
   │   (registered)         │  pre-registered before any data look
   └────────────┬───────────┘
                ▼
   ┌───────────────────────┐
   │ 2. Forward ledger CSV │  pipeline/data/research/<name>/recommendations.csv
   │   (open + close)      │  scheduled tasks write OPEN at 09:30, CLOSE at 14:30
   └────────────┬───────────┘
                ▼
   ┌───────────────────────┐
   │ 3. TrackerSpec config  │  pipeline/research/<name>_tracker.py (~30 lines)
   │   (cells, features)    │  imports cohort_harness.run_tracker
   └────────────┬───────────┘
                ▼
   ┌───────────────────────┐
   │ 4. Register in         │  pipeline/research/run_all_trackers.py
   │   run_all_trackers     │  add to TRACKERS dict
   └────────────┬───────────┘
                ▼
   ┌───────────────────────┐
   │ 5. master_evidence.json│  pipeline/data/research/master_evidence.json
   │   updates daily        │  every PUBLISH/MONITOR cell aggregates here
   └────────────┬───────────┘
                ▼
   ┌───────────────────────┐
   │ 6. Memory + catalog    │  memory/project_<name>_<date>.md
   │   record               │  + ANALYSIS_CATALOG.md row
   └───────────────────────┘
```

## When to use which lever

| Want to test… | Mechanism |
|---|---|
| A new exit rule on existing entries | Variant of existing tracker; mark hindsight clearly |
| A new filter on existing entries | Add a `cell_fn` to TrackerSpec; harness aggregates automatically |
| A new feature for tertile cells | Add to `feature_fns` + `tertile_features` |
| A new signal source entirely | Spec + ledger + new TrackerSpec; register in run_all_trackers |
| A regime-specific subset | Set `regime_filter` on TrackerSpec |

## Cell publication thresholds

```python
PUBLISH = N >= 30        # real evidence, can be cited
MONITOR = 10 <= N < 30   # watching it grow
INSUFFICIENT = N < 10    # do not act
```

These are constants in `pipeline/research/cohort_harness.py`. They apply uniformly to every tracker. When a cell crosses 30, it auto-becomes PUBLISH on the next run.

## Existing trackers (call sites in run_all_trackers.py)

| Tracker | Source ledger | Status |
|---|---|---|
| neutral_cohort | h001 NEUTRAL CLOSED | 5 PUBLISH cells (VWAP/ORB/baseline) |
| h001_full | h001 all CLOSED | 5 PUBLISH cells (regime/side/sigma/filter_tag) |
| secrsi | secrsi CLOSED | NO_LEDGER (no closed yet) |

Add a new tracker by:
1. Writing a `_run_<name>()` function in `run_all_trackers.py` that returns the harness summary dict
2. Adding it to the `TRACKERS = {...}` dict
3. Running `python -m pipeline.research.run_all_trackers --print` to verify

## What this framework forbids

1. **Citing in-sample replay numbers as forward edge.** The 93% Phase C number lived for weeks before audit caught that it was hindsight-tuned (NO_Z_CROSS variant). Replay outputs are research artifacts, not edge claims.

2. **Filtering on data after seeing the answer.** If you discover a filter cell improves the win rate, the filter is a hypothesis to pre-register, not a closed claim. Promote to live-gated only after a fresh single-touch holdout per `backtesting-specs §10.4`.

3. **Adding rules during a holdout window.** Holdouts are sealed. Display-only tags are fine; gating logic changes are not.

4. **Pooling across regimes without the regime breakdown.** Pooled means contaminate. Always show regime-conditional cells when N permits.

5. **Skipping the data inventory check.** No analysis on a dataset that isn't in `DATA_INVENTORY.md` with PASS quality gate.

## What this framework guarantees

1. **Every claim has N**, sample threshold, and clear PUBLISH / MONITOR / INSUFFICIENT label.
2. **Every PUBLISH cell** is reproducible from forward CLOSED trades + a fixed cell definition.
3. **Every analysis** has a single-page memory note with date, sample, verdict.
4. **Master state** lives in one JSON (`master_evidence.json`), updated daily.
5. **Future sessions** can reconstruct the world from `DATA_INVENTORY.md` + `ANALYSIS_CATALOG.md` + `master_evidence.json`.

## How to add a new analysis in 30 minutes

```python
# Example: BB-position filter on H-001 NEUTRAL trades

# 1. Write feature function
def bb_position_at_entry(row: dict) -> float | None:
    """Z-score of close vs BB(20,2) on entry day."""
    # ... read daily history, compute BB, return z
    return z

# 2. Write the spec
from pipeline.research.cohort_harness import TrackerSpec, run_tracker
SPEC = TrackerSpec(
    name="bb_position_neutral",
    ledger_path=Path("pipeline/data/research/h_2026_04_26_001/recommendations.csv"),
    regime_filter="NEUTRAL",
    feature_fns={"bb_z": bb_position_at_entry},
    tertile_features=["bb_z"],
    extra_columns=["side", "filter_tag"],
    out_subdir="bb_position_cohort",
)

# 3. Run it
summary = run_tracker(SPEC)

# 4. Register in run_all_trackers.TRACKERS

# 5. Write memory note + ANALYSIS_CATALOG row
```

That's the whole framework.
