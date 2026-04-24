# Regime-Aware Autoresearch Engine v2 — Design Spec

**Date:** 2026-04-25
**Status:** FROZEN, ready for implementation plan
**Supersedes:** none. Layers on top of `2026-04-24-regime-aware-autoresearch-design.md` (v1 frozen). v1 infrastructure is correct and reused wholesale.
**Parked v1 state:** engine at commit `09847ef` on `feat/phase-c-v5`. 139 autoresearch tests green. NEUTRAL pilot outcome: feature library v1 does not yield alpha surviving the 3-gate verdict.

---

## §0. Why v2 exists

v1 Task 8 NEUTRAL pilot (20 Haiku proposals + walk-forward reanalysis, commit `09847ef`) established three findings the spec now addresses:

1. **Fold 0 empty on 252-bar features.** `TRAIN_VAL_START = 2021-04-23` equals the panel start, so 252-bar trailing-window features had no history on day 1. Walk-forward fold 0 came back empty and silently averaged as 0.0 until #198 added the coverage gate.
2. **Long-only NIFTY B&H is a weak hurdle.** NEUTRAL NIFTY at h=5 was −0.586. Any strategy losing slightly less than NIFTY "beat" the hurdle trivially. The 2 survivors of the 3-gate verdict reanalysis both had negative net Sharpe.
3. **Feature library v1 is narrow.** 20 features, heavily clustered on momentum/vol/correlation. Even with panel + hurdle fixed, a narrow library caps the upper bound of what can be discovered.

**v2 is a three-lever upgrade** to address these findings while reusing every v1 component that wasn't the bottleneck. No rewrite.

**v2 is also the first real exercise of Mode 2** (autonomous execution, specified but unexercised in v1). The user requirement is explicit: no human-in-loop during the research loop. Decision-making leakage from Mode 1 is the thing being eliminated.

---

## §1. Scope decisions (frozen)

Captured from brainstorming on 2026-04-25:

| # | Decision | Chosen | Rationale |
|---|---|---|---|
| Q1 | Feature-library scope | **Tight v2** — realistic features only from existing data | Microstructure (OI/PCR/basis) has no historical depth (5 days of OI data). Deferred to v2.1 after a data-backfill project. |
| Q2 | Hurdle construction | **Construction-matched random basket** | Weaker nulls (universe B&H) give credit for sector tilt. Only a construction-matched null isolates feature quality. |
| Q3 | Feature list | 14 added on top of v1's 20 = **34 total**; `trust_sector_rank_delta_30d` dropped (no daily trust history) | Every feature must be computable from data that exists today. |
| Q4 | Autonomy boundary | **Stops at forward-shadow** | Paper-trade stage is reversible; live-commit is a money decision that stays a human act. |
| Q5 | Pair construction | **Deferred to v2.1** | Feature-library bottleneck is independent of construction type. Proving features work first is the right order. |
| Q6 | BH-FDR firing cadence | **v1 whichever-first trigger, per regime** | Statistical procedure unchanged; only the volume of proposals changes. |

---

## §2. Load-bearing changes vs v1

### §2.1 Data panel extension

- **Change:** `PANEL_START = 2020-04-23`, 252 trading days earlier than v1's implicit panel start.
- **Unchanged:** `TRAIN_VAL_START = 2021-04-23`, `TRAIN_VAL_END = 2024-04-22`, `HOLDOUT_START = 2024-04-23`, `HOLDOUT_END = 2026-04-23`, regime quantile cutpoints (still frozen on 2018-01-01..2021-04-22 window).
- **Why:** 252-bar trailing-window features need 252 trading days of history on day 1 of the evaluation window. This fix makes fold 0 of walk-forward populated for those features.
- **Separation already correct** (from v1 fix at `d97ef7d`): panel = unfiltered price history; event dates = regime-filtered evaluation days. v2 only extends the panel backward; event dates stay put.
- **Coverage gate:** tickers with <100 missing days in 2020-04-23..2024-04-22 get yfinance backfill. Tickers with ≥100 missing days are dropped from v2 universe. Audit written to `panel_coverage_audit_2026-04-25.json`.

### §2.2 Construction-matched random-basket hurdle

Replaces `regime_buy_and_hold_sharpe` (long-only NIFTY) with a bootstrap null that matches the proposed strategy's construction, cardinality, and holding horizon.

**Algorithm.** For each (construction `C`, cardinality `k`, hold horizon `h`, regime `R`):

```
for trial in range(1000):
    per_event_returns = []
    for event_date d in regime-R-in days (train+val window):
        pick k tickers uniformly at random from F&O universe active on d
        apply C's sign semantics (long / short / long-short)
        hold h trading days
        compute net-of-cost return via slippage_grid S1
        append to per_event_returns
    trial_sharpe = annualized_sharpe(per_event_returns)
    trials.append(trial_sharpe)
hurdle_sharpe_median[C,k,h,R] = median(trials)
hurdle_sharpe_p95[C,k,h,R] = percentile(trials, 95)  # diagnostic only
```

**Output table.** `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet`

| Column | Type |
|---|---|
| construction | str |
| k | int |
| hold_horizon | int |
| regime | str |
| window | str (`"train_val"` or `"holdout"`) |
| hurdle_sharpe_median | float |
| hurdle_sharpe_p95 | float |
| n_events | int |
| n_trials | int |
| seed | int |
| generated_at_sha | str |

**Why two windows.** In-sample verdicts compare against the train+val hurdle (the strategy must beat random selection on the data it was discovered on). Holdout verdicts compare against the holdout hurdle (the strategy must beat random selection on the frozen future). Using train+val hurdle on holdout data would give credit or blame for regime-shift effects that are shared between the strategy and its null, which is dishonest.

**Row count:** 5 constructions × 8 k-values × 3 horizons × 5 regimes × 2 windows = **1,200 rows**.
**Compute cost:** ~192M total return draws, ~40 min on one core. One-shot at setup.
**Determinism:** seed = `hash(f"{construction}|{k}|{h}|{regime}|{window}")` mod 2^32. Reproducibility test asserts re-run matches within float tolerance.

**Gate integration.** The verdict block in `in_sample_runner.py` changes one line:

```python
# v1: hurdle_sharpe = regime_buy_and_hold_sharpe(...)
hurdle_sharpe = load_null_basket_hurdle(
    proposal.construction, proposal.k,
    proposal.hold_horizon, proposal.regime,
    window="train_val"
)
passes_delta_in = (net_sharpe_mean - hurdle_sharpe) >= DELTA_IN_SAMPLE
```

`DELTA_IN_SAMPLE = 0.15` unchanged.

**Scarcity fallback deleted.** v1's `<3 clean incumbents → regime B&H` branch in `incumbents.py` is obsolete — every proposal now gets a construction-matched null regardless of incumbent count. Delete the branch, update its tests.

### §2.3 Feature library (14 additions → 34 total)

All 20 v1 features carry over unchanged. Vectorized `_fast_*` kernels and drift-assertion in `features.py` extend to the 14 new features.

**Price/return transforms (5):**
| # | Name | Definition |
|---|---|---|
| 1 | `return_1d` | `close[t-1]/close[t-2] - 1` |
| 2 | `return_5d` | `close[t-1]/close[t-6] - 1` |
| 3 | `return_60d` | `close[t-1]/close[t-61] - 1` |
| 4 | `skewness_20d` | `scipy.stats.skew(daily_returns[t-21..t-1])` |
| 5 | `kurtosis_20d` | `scipy.stats.kurtosis(daily_returns[t-21..t-1])` (excess) |

**Volume/liquidity (3):**
| # | Name | Definition |
|---|---|---|
| 6 | `volume_zscore_20d` | `(volume[t-1] - mean(volume[t-21..t-1])) / std(volume[t-21..t-1])` |
| 7 | `turnover_percentile_252d` | cross-time rank of `volume[t-1]*close[t-1]` within trailing 252-bar window for the ticker |
| 8 | `volume_trend_5d` | `mean(volume[t-5..t-1]) / mean(volume[t-21..t-1])` |

**Sector-relative (3):**
| # | Name | Definition |
|---|---|---|
| 9 | `excess_return_vs_sector_20d` | ticker 20d return minus sector equal-weight 20d return |
| 10 | `rank_in_sector_20d_return` | cross-sectional percentile of 20d return within same-sector tickers on day t-1 |
| 11 | `peer_spread_zscore_20d` | z-score of (ticker_20d_return − sector_mean_20d_return) over trailing 60-day rolling window |

**Cross-market (2):**
| # | Name | Definition |
|---|---|---|
| 12 | `correlation_to_sector_60d` | Pearson correlation of ticker's daily returns to sector equal-weight daily returns, trailing 60 bars |
| 13 | `residual_return_5d` | 5d sum of residuals from regressing ticker daily returns on NIFTY daily returns over trailing 60d window |

**Fundamentals-lite (1):**
| # | Name | Definition |
|---|---|---|
| 14 | `adv_ratio_to_sector_mean_20d` | ticker 20d mean (value traded) ÷ sector mean 20d mean (value traded) |

**Dropped:** `trust_sector_rank_delta_30d` — requires daily trust-score snapshots (not available). Deferred to v2.1.

**Causality invariant (per v1 convention):** every feature computes from `panel` rows where `date < eval_date`. No look-ahead. Enforced by the existing `assert past["date"].max() < eval_date` in `_build_context`.

**Grammar impact.** 34 features × 4 non-pair constructions × 4 threshold ops × 8 threshold values × 3 hold horizons × 5 regimes = **65,280 non-pair grammar points**. Haiku's 500-proposal/regime cap samples 0.76% — still larger than v1's 1.7% at 28,800 points, but any single regime's proposer is sampling a tiny fraction. That's fine; BH-FDR at holdout is the sharpness gate, not exhaustiveness.

---

## §3. Autonomy mechanics (Mode 2 orchestration)

### §3.1 Orchestrator

New CLI at `pipeline/autoresearch/regime_autoresearch/scripts/run_mode2.py`.

- Spawns **5 worker subprocesses**, one per regime
- Each worker runs the proposer → in-sample loop independently
- Main process waits, collects exit codes, writes summary at `run_mode2_summary_{timestamp}.json`

### §3.2 Per-regime worker loop

```
while not stopped:
    proposal = Haiku.propose(regime, forbidden_tuples=dedup_cache)
    if is_duplicate(proposal.tuple5): retry (≤3 attempts, else skip)
    verdict = in_sample_runner.run(proposal, panel, event_dates_for_regime,
                                   hurdle=load_null_basket_hurdle(...),
                                   n_folds=4)
    append to proposal_log_{regime}.jsonl
    if verdict.passes_delta_in
       and verdict.passes_min_events
       and verdict.passes_all_folds_populated:
        append to pre_registered_{regime}.jsonl
        append hypothesis-registry entry (state=PRE_REGISTERED)
    check stopping rules
```

### §3.3 Per-regime sharded log files

v1 single `proposal_log.jsonl` → v2 sharded to avoid file-lock contention:

```
pipeline/autoresearch/regime_autoresearch/logs/
├── proposal_log_risk_off.jsonl       pre_registered_risk_off.jsonl
├── proposal_log_caution.jsonl        pre_registered_caution.jsonl
├── proposal_log_neutral.jsonl        pre_registered_neutral.jsonl
├── proposal_log_risk_on.jsonl        pre_registered_risk_on.jsonl
└── proposal_log_euphoria.jsonl       pre_registered_euphoria.jsonl
```

**v1 log migration.** On first v2 commit, `proposal_log.jsonl` (22 rows, all NEUTRAL) → `proposal_log_neutral.jsonl`. Old rows preserved unchanged. v2 rows append with a new `schema_version: "v2"` field to distinguish.

### §3.4 Stopping rules (unchanged from v1 §15)

- **Hard cap:** 500 proposals per regime.
- **Soft stop:** 50 consecutive proposals with no net-Sharpe improvement over the best-so-far for that regime.

Either triggers per-regime stop. When all 5 workers stop, orchestrator exits.

### §3.5 BH-FDR firing (daily scheduled, per regime)

New scheduled task: `AnkaAutoresearchBHFDR`, runs 05:00 IST daily.

```python
# pipeline/autoresearch/regime_autoresearch/scripts/run_bh_fdr_check.py
for regime in REGIMES:
    batch_state = load_batch_state(regime)
    n_new = count_pre_registered_since_last_batch(regime)
    days_since = today - batch_state.last_batch_date
    if n_new >= 10 or days_since >= 30:
        survivors = run_bh_fdr(regime, q=0.1)
        append_to_holdout_queue(survivors, regime)
        mark_registry_states(survivors, "HOLDOUT_QUEUED")
        reset_batch_counter(regime)
```

### §3.6 Holdout (daily scheduled, unchanged from v1 Task 4)

New scheduled task: `AnkaAutoresearchHoldout`, runs 05:30 IST daily.

```python
# pipeline/autoresearch/regime_autoresearch/scripts/run_holdout.py
for regime in REGIMES:
    queue = load_holdout_queue(regime)
    for rule in queue:
        holdout_sharpe = evaluate_once(rule, HOLDOUT_START, HOLDOUT_END)
        hurdle = load_null_basket_hurdle(
            rule.construction, rule.k, rule.hold_horizon,
            rule.regime, window="holdout"
        )
        if (holdout_sharpe - hurdle) >= DELTA_HOLDOUT:
            append_to_forward_shadow_queue(rule)
            mark_registry_state(rule, "HOLDOUT_PASS")
        else:
            mark_registry_state(rule, "HOLDOUT_FAIL")
    clear_holdout_queue(regime)
```

`DELTA_HOLDOUT = 0.10` unchanged. Single-touch invariant preserved: each rule evaluates on holdout **once** in its lifetime.

### §3.7 Forward-shadow (existing v1 infrastructure)

Existing `forward_shadow.py` (v1 Task 5) unchanged. Reads `forward_shadow_queue.jsonl`, paper-trades, after 60 trading days AND ≥50 events evaluates forward Sharpe vs incumbent, writes survivors to **`pending_live_promotion.jsonl`**, marks registry state=FORWARD_SHADOW_PASS.

### §3.8 The human gate (new in v2)

`pending_live_promotion.jsonl` is the terminal autonomous state. **No scheduled task writes live strategy files.** The human reads the file, decides yes/no, and if yes runs:

```
python -m pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live <rule_id>
```

`promote_to_live.py` does three things in a single commit:
1. Generates the strategy file at `pipeline/autoresearch/regime_autoresearch/generated/<rule_id>_strategy.py` (so it matches the kill-switch naming pattern)
2. Appends a hypothesis-registry entry
3. `git add` + `git commit -m "promote: <rule_id> to live"` — single commit so the kill-switch pre-commit hook passes

This is the only path where a strategy file lands in the repo. Autonomy does not write strategy files.

---

## §4. Wall-clock and cost budgets

**Per-proposal cost:**
- Haiku API call: ~2-3s (Haiku 4.5 is fast)
- Features + verdict: ~60-90s (vectorized; 34-feature vector × ~160 regime-in event dates × 4 folds × 213-ticker universe)
- Hurdle lookup: O(1) post-precompute

**Per-regime budget:** 500 × 90s ≈ 12.5h
**Full run wall-clock:** parallel across 5 regimes = 12.5h (same as single-regime). Fits one overnight window (20:00 → 08:30 IST).

**Haiku cost:** ~$0.001/proposal × 500 × 5 = **$2.50/full-run**.

Mode 2 is cheap. The constraint is wall-clock, and parallel execution solves that.

---

## §5. Constant changes

Diff of `constants.py` vs v1:

```python
# NEW
PANEL_START = "2020-04-23"  # 252 trading days before TRAIN_VAL_START

# UNCHANGED (listed for clarity)
TRAIN_VAL_START = "2021-04-23"
TRAIN_VAL_END = "2024-04-22"
HOLDOUT_START = "2024-04-23"
HOLDOUT_END = "2026-04-23"
DELTA_IN_SAMPLE = 0.15
DELTA_HOLDOUT = 0.10
MIN_EVENTS_FOR_PASS = 20
MIN_EVENTS_PER_FOLD_FOR_PASS = 5
SLOTS_PER_REGIME = 10
PROPOSER_MODEL = "claude-haiku-4-5-20251001"
FORWARD_SHADOW_MIN_DAYS = 60
FORWARD_SHADOW_MIN_EVENTS = 50
REGIMES = ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")
BH_FDR_Q = 0.1
BH_FDR_MIN_BATCH = 10
BH_FDR_MAX_DAYS = 30
MODE2_HARD_CAP_PER_REGIME = 500    # promoted from v1 §15
MODE2_SOFT_STOP_NO_IMPROVE = 50    # promoted from v1 §15
```

---

## §6. Testing

### §6.1 Unit coverage

- `tests/test_features_v2.py` — 14 tests, one per new feature. Each asserts causality (no peek at `panel[date >= eval_date]`), correct NaN semantics, output shape, synthetic-fixture numeric correctness.
- `tests/test_null_basket_hurdle.py`:
  - `test_precompute_reproducible` — fixed seed → byte-identical-within-tolerance parquet on re-run
  - `test_lookup_interpolation` — correct row returned for valid (C, k, h, R) tuples
  - `test_lookup_raises_on_unknown_tuple` — explicit failure mode
  - `test_hurdle_matches_naive_for_single_long` — single_long on equal-weight universe should produce universe-mean-Sharpe within tolerance
- `tests/test_mode2_orchestration.py`:
  - `test_spawns_five_workers` — each regime gets its own subprocess
  - `test_stopping_rule_hard_cap` — worker stops at 500
  - `test_stopping_rule_soft_stop` — worker stops after 50 no-improvement
  - `test_per_regime_logs_no_contention` — 5 concurrent workers don't corrupt each other's logs
- `tests/test_bh_fdr_per_regime.py`:
  - `test_fires_on_ten_accumulated` — batch triggers at 10 pre-registered
  - `test_fires_on_monthly` — batch triggers at 30 days since last
  - `test_q_value_0_1` — known mixture survives correctly
- `tests/test_promote_to_live.py`:
  - `test_writes_strategy_file_with_registry_entry` — kill-switch pattern respected
  - `test_single_commit_atomic` — both files committed together
  - `test_refuses_if_rule_not_in_forward_shadow_pass` — refuses promotion of non-surviving rule

### §6.2 Reproducibility smoke

`tests/test_features_v2.py::test_drift_assert_covers_34_keys` — `FEATURE_FUNCS` must have exactly 34 entries, asserted in the defensive check the v1 perf rework added.

### §6.3 End-to-end smoke

`tests/test_mode2_e2e.py::test_short_run` — run `run_mode2.py --regime NEUTRAL --cap 5` (test flag, not production). Asserts 5 rows appended to `proposal_log_neutral.jsonl`, verdicts populated, hurdle values loaded (not inline-computed), no exceptions.

### §6.4 Target

`pytest pipeline/autoresearch/regime_autoresearch/tests/` green at ≥155 tests (v1 = 139; +16 new). No test flakiness — deterministic by construction.

---

## §7. Migration checklist (for the implementation plan)

**Commit 1 — constants + panel extension:**
- `PANEL_START = 2020-04-23` added to `constants.py`
- `build_regime_history.py` re-runs with extended window
- `panel_coverage_audit_2026-04-25.json` committed

**Commit 2 — null-basket hurdle precompute:**
- `null_basket_hurdle.py` + `build_null_basket_hurdles.py` added
- `null_basket_hurdles_v2.parquet` committed (600 rows, ~20KB)
- Tests added

**Commit 3 — hurdle integration:**
- `in_sample_runner.py` swaps `regime_buy_and_hold_sharpe` → `load_null_basket_hurdle`
- Scarcity-fallback branch deleted from `incumbents.py`
- Tests updated

**Commit 4 — feature library expansion:**
- 14 new entries in `features.py` (`FEATURE_FUNCS`, `_fast_*` kernels, drift-assert extended to 34 keys)
- 14 new unit tests

**Commit 5 — proposal log sharding:**
- v1 `proposal_log.jsonl` renamed → `proposal_log_neutral.jsonl`
- Proposer code updated to write per-regime logs
- Tests updated

**Commit 6 — Mode 2 orchestrator:**
- `run_mode2.py`, `run_bh_fdr_check.py`, `promote_to_live.py` added
- Tests added

**Commit 7 — scheduled-task wiring:**
- `anka_inventory.json` entries for `AnkaAutoresearchMode2`, `AnkaAutoresearchBHFDR`, `AnkaAutoresearchHoldout`
- `pipeline/scripts/Anka*.bat` wrappers for the three tasks
- Watchdog freshness contracts

**Commit 8 — docs sync + memory:**
- SYSTEM_OPERATIONS_MANUAL Station 11 updated (v2 differences)
- CLAUDE.md note: "v2 activated" if/when first Mode 2 run completes
- `memory/project_regime_aware_autoresearch.md` updated
- MEMORY.md index entry updated

**Commit 9 — first Mode 2 dry run (observation only):**
- Run `run_mode2.py --dry-run` to verify orchestrator spawns + stops cleanly without actually proposing
- Commit the dry-run summary JSON

---

## §8. Acceptance criteria

v2 is considered shipped when:

1. ≥155 autoresearch tests green.
2. `null_basket_hurdles_v2.parquet` committed; build script re-runnable in ≤30 min end-to-end.
3. One full Mode 2 nightly run completes across all 5 regimes without process crash and produces populated `proposal_log_*.jsonl` files.
4. At least one BH-FDR batch fires per regime within 7 calendar days of first Mode 2 run (evidence the trigger works at Mode-2 volume).
5. SYSTEM_OPERATIONS_MANUAL.md Station 11 updated with v2 diffs.
6. `memory/project_regime_aware_autoresearch.md` updated with v2 status.

**Not required for shipping v2:** a rule actually surviving forward-shadow. Forward-shadow takes 60 trading days — shipping the infrastructure is the v2 deliverable; shipping any live strategy is a downstream, human-gated decision that may or may not happen.

---

## §9. Non-goals (YAGNI)

- **No** pair construction (deferred to v2.1)
- **No** OI/PCR/basis features (deferred to v2.1, gated on data backfill project)
- **No** trust-score-delta features (deferred to v2.1, gated on daily trust snapshotting)
- **No** auto-commit of live strategy files — every live promotion is a human act
- **No** new UI — results inspected via JSONL logs + optional Telegram summary
- **No** live Kite execution wiring — strategy files, once committed, get picked up by existing infra

---

## §10. Outcome matrix

What v2 can teach us after 2-4 weeks of nightly Mode 2 runs:

| Observation | Interpretation | Next move |
|---|---|---|
| ≥1 rule survives forward-shadow, beats incumbent | Feature library v2 produces alpha. | Promote to live (human gate). |
| Pre-registered rules accumulate but all FAIL holdout | Regime decay or in-sample overfit. | Extend holdout window; investigate fold leakage. |
| No rules clear BH-FDR at q=0.1 in any regime after full run | Feature library v2 still insufficient. | **v2.1 justified** — data backfill project for OI/PCR/basis. |
| Runner crashes or hits wall-clock limits | Infrastructure problem. | Fix before further research. |

All four outcomes are informative. v2 is scientifically valuable even if no live strategy emerges — a clean "feature library v2 does not produce alpha" is a honest negative result that justifies the v2.1 data investment.

---

## §11. References

- v1 design spec: `docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md`
- v1 plan: `docs/superpowers/plans/2026-04-24-regime-aware-autoresearch.md`
- v1 parked state: commit `09847ef` on `feat/phase-c-v5`
- v1 pilot finding: commit `09847ef` — `reanalyze_log.py` output
- Station 11 in `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Memory: `memory/project_regime_aware_autoresearch.md`
- Kill switch: `pipeline/scripts/hooks/pre-commit-strategy-gate.sh` + `.github/workflows/strategy-gate.yml`
