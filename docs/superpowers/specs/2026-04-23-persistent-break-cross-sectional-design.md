# Persistent-Break + Cross-Sectional Model Design

**Hypothesis ID:** H-2026-04-24-002 (next available after H-2026-04-24-001 TA pilot)
**Date registered:** 2026-04-24 (first run date; spec frozen 2026-04-23)
**Standards version:** `docs/superpowers/specs/backtesting-specs.txt` v1.0
**Prior context:** `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` (H-002/H-003 FAIL)

## Motivation

Three Phase C residual-reversion hypotheses have failed Bonferroni:

- **H-2026-04-23-001** (full panel, 426 cells): 0 survivors at α = 1.17e-4.
- **H-2026-04-23-002** (LAG slice, 344 cells): 0 survivors at α = 1.45e-4.
- **H-2026-04-23-003** (OVERSHOOT slice, 267 cells): 0 survivors at α = 1.87e-4.

Near-misses concentrate on 5 tickers (360ONE UP, NAM-INDIA DOWN, ZYDUSLIFE UP, IDFCFIRSTB DOWN, SBIN UP) but none clear strict Bonferroni. The cell-by-cell approach is crushed by multiplicity: 5 years × 400 cells averages ~35 events per cell, which is thin for any reliable edge detection.

The reframing this spec registers:

1. **Single-event 4σ prints are noise-ridden.** Persistence — a break that was building for at least two days — filters away most idiosyncratic one-offs and keeps the "setup matured" subset.
2. **Cross-sectional context carries information.** When a stock breaks, the z-score vector of the other 212 F&O stocks on the same day contains joint-distribution information that single-cell tests discard.
3. **A learnable model of (persistence, cross-sectional vector) → next-day return** is a family-of-1 hypothesis — Bonferroni α = 0.05 is cheap to satisfy, but the model still has to beat naive comparators on held-out data.

This is the honest next test: if a regularized linear model on hybrid features cannot beat the strongest naive on 12 weeks of out-of-sample data, the persistent-break + cross-sectional narrative is exhausted. If it does beat them, the Lasso coefficients tell the story in plain English ("when HINDALCO is up and BANKNIFTY is flat, the model expects broken-stock reversion").

## Hypothesis

**H-2026-04-24-002 (persistent-break cross-sectional predictive model)**

**Claim:** A Lasso regression model, trained on the persistent-break subset of the 14,907-event Phase C parent panel using cross-sectional z-scores of all 212 other F&O stocks as features, produces out-of-sample T+1-return predictions whose sign-triggered trading rule achieves a higher Sharpe on the 2026-01-01 → 2026-04-23 holdout window than the strongest of three naive comparators, with p ≤ 0.05 under a 100,000-sample label-permutation null test.

**Family size:** 1 (the single trained model vs. the single strongest naive comparator).
**Bonferroni α:** 0.05 / 1 = 0.05.
**Execution mode:** MODE A EOD (entry at T close, exit at T+1 close).
**Slippage level:** S1 (20 bps round-trip Zerodha SSF) as the primary bar; S2/S3 reported as stress points.

## Event filter (pre-registration binding)

Persistent-break events are the subset of parent panel events satisfying:

```
|z_{i,T}| ≥ 3.0
AND |z_{i,T-1}| ≥ 3.0
AND sign(z_{i,T}) = sign(z_{i,T-1})
AND ticker i has ≥ 60 trading days of price history through T-1
```

The same-sign requirement ensures the break has persisted in *direction*, not just in magnitude. A stock that was +3σ yesterday and −3σ today is not a persistent break — it is two opposing one-day prints.

**Expected event count:** 1,000–2,000 on the 2021–2026 panel. The implementation plan includes a smoke-run count check before full training; if n < 500, spec is revisited and not run.

## Feature set (pre-registration binding)

Feature vector has **236 dimensions**, composed of:

| Block | Count | Description |
|---|---:|---|
| Cross-sectional ticker z-scores | 212 | `z_{j,T}` for every other F&O ticker j ≠ i, same day T as the break. Missing bar (ticker didn't trade) imputed to 0.0. |
| Sector-mean z-scores | 17 | Mean `z` across all tickers in each of the 17 broad sectors on day T (see `BROAD_SECTOR` map in `overshoot_reversion_backtest.py`). |
| Market context | 4 | `vix_close_T` plus three regime dummies `regime_RISK_OFF`, `regime_NEUTRAL`, `regime_RISK_ON` (one-hot, no drop-one because Lasso handles collinearity via regularization). |
| Break event identity | 2 | `z_self_T` (the broken stock's own z on T), `z_self_T_minus_1` (same on T-1). |
| Break direction | 1 | `break_direction` = +1 if `z_{i,T} > 0`, −1 if `z_{i,T} < 0`. |

**Total: 212 + 17 + 4 + 2 + 1 = 236 features.**

All features are computed at T close. No T+1 or later data is used (no look-ahead).

**Feature-matrix storage:** written to `feature_matrix_train.parquet` and `feature_matrix_test.parquet` alongside the run artifacts for reproducibility.

## Label

`y = next_ret_pct_{i, T+1}` — the broken stock's T-close to T+1-close percentage return. Units: percent (consistent with the parent panel schema).

## Data split (pre-registration binding)

Chronological split by event date:

- **Training set:** events with date ≤ 2025-12-31.
- **Holdout (test) set:** events with 2026-01-01 ≤ date ≤ 2026-04-23.

The holdout is approximately 6% of the panel — under standards §10.1 (which requests 20%) but consistent with H-2026-04-23-001/002/003 and flagged as a warning in the run manifest. The spec declares the 6% accepted at registration time; the gate checklist reports the warning but does not fail on it alone.

## Model (pre-registration binding)

- **Class:** `sklearn.linear_model.LassoCV`.
- **Alpha grid:** `numpy.logspace(-5, 0, 25)` — 25 points from 1e-5 to 1.0, log-spaced.
- **CV within training window:** 4-fold purged walk-forward (fold boundaries embargoed ±2 days to handle the T+1-label overlap). Alpha selected to maximize **mean OOS Sharpe across the 4 CV folds**, not R².
- **Feature standardization:** z-scored per column on training set only; same transform applied to holdout. Standardizer persisted alongside the model.
- **Final fit:** after alpha selection, the model is refit on the full training set (no CV held-out).

**Model artifact:** saved as `model.pkl` and `model_coefs.json` (human-readable coefficient vector with feature names).

## Trading rule (pre-registration binding)

For each holdout event:

```
prediction = model.predict(feature_vector)  # scalar, units: % T+1 return
if prediction > ε:        trade_direction = "LONG"
elif prediction < -ε:     trade_direction = "SHORT"
else:                     trade_direction = "FLAT"  (no trade, no P&L)

ε (epsilon) = 0.5 × median(|training_predictions|)  # frozen on training set
```

The epsilon is calibrated on training-set prediction magnitudes and **frozen** — it is not tuned on the holdout. This prevents the trading-rule threshold from being an implicit second hyperparameter.

Realized P&L per held-out trade (pre-slippage):

```
pnl_gross_pct = (1 if trade_direction == "LONG" else -1) × next_ret_pct  for LONG/SHORT
pnl_gross_pct = 0                                                         for FLAT
```

Slippage grid S0/S1/S2/S3 is applied by the runner per §1 of the compliance standards.

## Naive comparators (§9B.1)

On the same holdout event set, three naive strategies are evaluated:

1. **Always-fade:** `trade_direction = -sign(residual_{i,T})` — the direction that H-2026-04-23-001 backtest used.
2. **Always-follow:** `trade_direction = sign(expected_return_{i,T})` — the direction that the live Phase C engine uses.
3. **Buy-and-hold broken stock:** `trade_direction = +1` regardless of break direction (null trade — just holds the stock long on T→T+1).

The **strongest comparator** is the one with the highest S1 Sharpe on the holdout. The model must exceed that value for the hypothesis to have a chance at PASS.

## Permutation null test (§9B.2)

**Null hypothesis:** the model's OOS Sharpe margin over the strongest naive is achievable by chance on label-permuted training data.

**Procedure:**

1. Hold feature matrix X_train fixed.
2. Shuffle y_train (100,000 times, with a fixed seed sequence for reproducibility).
3. For each shuffle, refit LassoCV (same alpha grid, same CV splits) on the shuffled labels, predict on X_test, apply the same trading rule, compute S1 Sharpe of (model − strongest_naive).
4. Empirical p-value = fraction of shuffles where the permuted-model margin ≥ observed-model margin.

**Implementation:** streaming — each shuffle produces one scalar (the margin), accumulated into a running histogram. No (100k × n_test) prediction matrix in memory.

**Performance budget:** a single Lasso fit on ~1,500 × 236 takes ~50 ms on cold cache; 100k fits ≈ 1.4 hours. Parallelizable across 8 cores → ~10 minutes wall-clock. Acceptable for a compliance run.

## Fragility sweep (§9A)

**Neighborhood** (pre-registration binding):

- Lasso alpha: {0.8×, 1.0×, 1.2×} of the CV-selected alpha.
- Z-threshold: {2.5, 3.0, 3.5}.
- Persistence window: {1 day (just T), 2 days (T and T-1), 3 days (T, T-1, T-2)}.

Total: 3 × 3 × 3 = 27 neighborhood points.

**Pass condition:** the sign of the model-vs-strongest-naive Sharpe margin must be stable across ≥22 of the 27 (i.e., ≥81%) neighborhood points. Magnitude may vary.

## Other standards sections

| Section | Treatment |
|---|---|
| §5A data audit | Reused from `overshoot_compliance/data_audit.py`. Classification INSUFFICIENT_DATA halts the run. |
| §6.1 / §6.2 | Inherits H-2026-04-23-001 survivorship waiver (expires 2026-07-23). |
| §7.1 | Manifest declares `execution_mode: "MODE_A_EOD"`. |
| §8 direction audit | Holdout trades logged with (ticker, predicted_sign, fade_sign, follow_sign, realized_sign). Mismatch between model and live engine flagged but not fatal. |
| §10.1 holdout | 6% flagged as warning in manifest. Accepted at registration. |
| §10.2 walk-forward CV | Used only for alpha selection inside training window. Purge = 2 days. |
| §11 ADV | Reused `impl_risk.py`. |
| §11A impl-risk | Same 10-scenario stress as prior runs. |
| §11B NIFTY-beta | Residual Sharpe must be ≥70% of gross Sharpe. |
| §11C portfolio gate | Pairwise correlation and concentration on holdout trades. |
| §12 CUSUM decay | Runs on *training-window* per-month realized P&L (holdout is too short). Recent-24m ≥ 50% of full-history. |
| §13A.1 manifest | SHA-256 per input price file + seed + alpha grid + cost model version. |
| §14.5 multiplicity | Family = 1, declared at spec time. |
| §15.1 gate checklist | Final PASS/FAIL artifact. PASS → TIER_EXPLORING at 0.5-unit forward shadow for ~100 trades. |

## Success criteria (pass/fail boundary)

**PASS** (all must hold):

- Holdout S1 Sharpe of model > Holdout S1 Sharpe of strongest naive.
- Permutation-null p-value ≤ 0.05.
- Fragility: sign stable on ≥22 of 27 neighborhood points.
- §11B residual Sharpe ≥ 70% gross.
- §11C portfolio correlation and concentration within limits.
- §12 recent-24m edge ≥ 50% of full-history edge.
- Data audit not INSUFFICIENT_DATA.
- At least 50 holdout events survive the persistence filter.

**FAIL** on any violation. No partial credit — the hypothesis is single-model by construction, so there is no sub-slice to rescue.

**If PASS:** register `terminal_state = "PASS_YYYY-MM-DD"` in `docs/superpowers/hypothesis-registry.jsonl`. Forward-deploy the model at `TIER_EXPLORING` (0.5-unit sizing) via a separate daily scheduled task that scores every new persistent-break event — this wiring is a follow-on spec, NOT part of this hypothesis' scope.

**If FAIL:** register `terminal_state = "FAIL_YYYY-MM-DD"`. Do not retry with different features, model class, or thresholds to "fix" it — that is p-hacking under a new name. The next hypothesis, if any, is a fresh pre-registration.

## Scope boundaries (explicit non-goals)

- NOT training on live `correlation_breaks.json` — uses the frozen parent panel only.
- NOT an intraday model (no 1-min bar history exists).
- NOT replacing Phase C residual-reversion engine — additive research; existing engine keeps running.
- NOT touching task #112 (entry-snap fix) — MODE A EOD is our execution mode for this run.
- NOT a gradient-boost model — Lasso is pre-registered. If it fails, the answer is "linear cross-sectional model on persistent breaks doesn't work," not "quietly try XGBoost and check if it looks better."

## Components

Five new files under `pipeline/autoresearch/phase_c_cross_sectional/`:

1. `event_filter.py` — `filter_persistent_breaks(events_df, z_threshold, persistence_days)` → filtered DataFrame.
2. `feature_builder.py` — `build_feature_matrix(events_df, price_panel, regime_history, vix_series)` → (X, y).
3. `model.py` — `fit_lasso(X_train, y_train, alpha_grid, cv_splits)` + `predict(model, X)` + serialization.
4. `permutation_null.py` — `run_label_permutation_null(X_train, y_train, X_test, y_test, strongest_naive_sharpe, n_shuffles, seed)` → p-value.
5. `runner.py` — end-to-end orchestration, emits the compliance artifact.

New test files mirror module structure under `pipeline/tests/autoresearch/phase_c_cross_sectional/`.

Infrastructure reused without modification: `overshoot_compliance/{slippage_grid, metrics, naive_comparators, fragility, beta_regression, impl_risk, cusum_decay, portfolio_gate, gate_checklist, manifest, data_audit, universe_snapshot, execution_window}`, `overshoot_reversion_backtest.{compute_residuals, classify_events, load_price_panel, load_sector_map, BROAD_SECTOR}`.

## Data flow

```
events.json (parent 14,907 rows)
    → event_filter.filter_persistent_breaks
        → ~1,500-2,000 persistent events
            → feature_builder.build_feature_matrix
                → (X, y) with 236 columns
                    → chronological split (≤2025-12-31 train, 2026 test)
                        → model.fit_lasso (LassoCV, alpha grid, 4-fold purged CV)
                            → predictions on holdout
                                → trading rule (LONG/SHORT/FLAT per epsilon)
                                    → slippage grid S0/S1/S2/S3
                                        → metrics + CI + naive comparators
                                            → permutation null (100k label shuffles)
                                                → fragility sweep (27 neighborhood points)
                                                    → §11B/§11C/§12/other sections
                                                        → gate_checklist → PASS/FAIL
```

Output directory: `pipeline/autoresearch/results/compliance_H-2026-04-24-002_<timestamp>/`. Contains manifest, feature matrices, model, coefficients, predictions, all compliance section JSONs, and final gate_checklist.

## Testing discipline

- TDD for every new function. Failing test first, implementation second.
- Synthetic fixtures for all unit tests — no real price data dependency in unit tests.
- End-to-end smoke (`test_runner.py`) on a ~20-event synthetic panel with a known Lasso solution so the pipeline produces a deterministic artifact.
- Full `pipeline/tests/autoresearch/phase_c_cross_sectional/` directory must be green before any commit.
- Verification-before-completion: the hypothesis is not "promising" until gate_checklist.json exists on disk with `decision: PASS` and has been read.

## Reproducibility

- Manifest writes: random seed (42), SHA-256 per input price file, alpha grid, holdout boundary date, cost model version (`zerodha-ssf-2025-04`), n_features, n_train_events, n_test_events, Python + sklearn + numpy versions.
- Same inputs → same outputs, byte-for-byte on model coefficients and predictions.
- Permutation test uses a derived seed sequence (`numpy.random.SeedSequence(42).spawn(100_000)`) so re-running the permutation alone does not re-fit the model.

## Failure-mode handling

| Failure | Response |
|---|---|
| Missing ticker z-score on day T | Imputed 0.0; logged to data_audit. |
| VIX series missing | VIX column dropped from feature set; manifest warning. |
| Fewer than 50 holdout events | Runner exits `decision: INSUFFICIENT_POWER`; gate_checklist FAIL at §9.3. |
| Lasso CV picks alpha at grid boundary | Grid auto-expanded, refitted, manifest warning. |
| Permutation null computation timeout | Partial result persisted with n_completed; gate_checklist flags INCOMPLETE. |
| Data audit INSUFFICIENT_DATA | Run halted before fit. |

## Open questions (flagged, not blocking)

- **Forward deployment plumbing.** If PASS, we need a daily scheduled task that computes features for every new persistent-break event and emits a predicted direction. That wiring is a follow-on spec (~1 day of work) — deliberately excluded here to keep this spec focused on the research question.
- **Sector-mean denominators.** Sector z-score mean uses arithmetic mean. If a sector has very few tickers on a given day (fewer than 3), the mean may be noisy. Mitigation: sector-mean column NaN-masked and imputed to 0.0 when n<3 tickers; no special-case logic needed.
- **Persistence edge case.** If a stock breaks at |z|=3.0 on T and T-1 but has a data gap on T-2 (e.g., trading halt), it's still a persistent break by this spec. This is accepted behavior — the 2-day persistence window is what the spec freezes.

## Related documents

- Parent hypotheses: `docs/superpowers/hypothesis-registry.jsonl` lines 1–4.
- Parent events: `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json`.
- Direction audit that preceded this registration: `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` and `docs/superpowers/phase_c_direction.md`.
- Compliance standards: `docs/superpowers/specs/backtesting-specs.txt` v1.0.
- Survivorship waiver (inherited): `docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md`.
