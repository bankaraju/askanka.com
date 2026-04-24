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
     `hurdle_source`, `passes_delta_in` (Δ_in = 0.15).

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

5 tests stub proposer + in-sample + `input()`; no real Haiku or real panel
is touched.
