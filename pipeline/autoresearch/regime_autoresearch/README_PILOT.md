# Autoresearch Pilot — Mode 1 (human-in-loop)

## Invocation

```bash
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_pilot --regime NEUTRAL
```

Each invocation runs **one iteration** and exits. Re-invoke to drive the next.

## The one-iteration loop

1. Prints `approved so far: N+1 of ~20` — the NEUTRAL proposal counter.
2. Calls the Haiku proposer (pinned: `claude-haiku-4-5-20251001`) through a
   `ProposerView` that sees `proposal_log.jsonl` + `strategy_results_10.json`
   and **cannot** read `holdout_outcomes.jsonl`.
3. Prints the DSL proposal (construction_type, feature, threshold_op/value,
   hold_horizon, regime).
4. Prompts: `Approve this proposal? [y/n/s]`.
   - `n` — appends a `REJECTED` row, exits.
   - `s` — exits without writing anything.
   - `y` — builds the train+val panel filtered to NEUTRAL dates
     (`2021-04-23 .. 2024-04-22`), computes the hurdle via
     `incumbents.hurdle_sharpe_for_regime`, calls
     `in_sample_runner.run_in_sample`, appends one `APPROVED` row
     with `net_sharpe_mean`, `n_events`, `hurdle_sharpe`,
     `hurdle_source`, `fold_sharpes`, `fold_n_events`,
     `insufficient_for_folds`, and the three verdict gate booleans
     (`passes_delta_in`, `passes_min_events`, `passes_all_folds_populated`).

## Verdict gates (all three must PASS)

A rule is considered a real candidate iff ALL three gates fire. Any single
FAIL → verdict FAIL.

1. **`passes_delta_in`** (`Δ_in = 0.15`) — `net_sharpe_mean - hurdle_sharpe
   >= DELTA_IN_SAMPLE`. The core Sharpe uplift requirement. Without this
   gate a rule that merely matches the incumbent can sneak through.

2. **`passes_min_events`** (`MIN_EVENTS_FOR_PASS = 20`) — `n_events >=
   20`. Prevents `n_events=0` from trivially passing when the hurdle is
   sufficiently negative (observed 2026-04-24 pilot on `trust_score
   top_20`). 20 is the smallest sample where a per-event Sharpe estimate
   is meaningful at 5-day holds.

3. **`passes_all_folds_populated`** (`MIN_EVENTS_PER_FOLD_FOR_PASS = 5`) —
   every K-fold time-series CV fold has at least 5 events AND the runner
   did not fall back to a single-pass evaluation. Catches the fold-0-empty
   failure mode: features with a 252-bar trailing requirement
   (`days_from_52w_high`, `dist_from_52w_high_pct`, `vol_percentile_252d`,
   `adv_percentile_252d`) silently empty fold 0 when the panel only goes
   back 3 years before `TRAIN_VAL_START`. The empty fold averages in as
   0.0 but the non-empty folds can still pull the mean above
   hurdle+delta_in — falsely passing. Single-pass fallback rows
   (`insufficient_for_folds=True`) auto-fail this gate because their
   in-sample window is too short for a trustworthy cross-time Sharpe.

## Reading the log

```bash
tail -5 pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl
```

Each line is one proposal: DSL fields, approval status, in-sample metrics
(only when `APPROVED`), and ISO timestamp. Append-only — never rewritten.

## Stopping criteria

- **Hard target:** ~20 APPROVED NEUTRAL proposals before switching to
  autonomous mode.
- **Soft stop:** 50 consecutive non-improving proposals (manual judgment).

## If something breaks

- **`anthropic SDK not installed`** — `pip install anthropic` or set
  `ANTHROPIC_API_KEY`. The CLI loads the SDK lazily so tests never need it.
- **`missing regime history`** — rebuild with
  `python -m pipeline.autoresearch.regime_autoresearch.scripts.build_regime_history`.
- **`no parquets under daily_bars`** — Task 0 panel build is missing;
  re-run Task 0 before the pilot.
- **DSL grammar ValueError** — the LLM returned an off-grid threshold.
  `dsl.validate()` enforces strict grid membership; re-run the iteration.

## Tests

```bash
pytest pipeline/tests/autoresearch/regime_autoresearch/test_run_pilot.py -v
```

Tests stub proposer + in-sample + `input()`; no real Haiku or real panel
is touched. The full autoresearch suite (138 tests) includes 4 verdict-gate
tests covering the fold-0-empty, any-fold-below-min, happy-path, and
insufficient-for-folds scenarios.
