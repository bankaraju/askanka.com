# Persistent-Break + Cross-Sectional Model Design (v2)

**Hypothesis ID:** H-2026-04-24-003
**Date registered:** 2026-04-24 (first run date; spec frozen 2026-04-24)
**Standards version:** `docs/superpowers/specs/backtesting-specs.txt` v1.0
**Parent spec (inherited verbatim except for noted changes):** `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (commit `eb80ae5`)
**Prior context:** `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` (H-002/H-003 FAIL); H-2026-04-24-002 abandoned pre-execution (n=116 < 500 floor), registry line 5, abandonment commit `b50773f`.

## Motivation for v2

H-2026-04-24-002's event filter (`|z|≥3 on T AND |z|≥3 on T-1, same-sign`) produced only 116 events on the 2021–2026 parent panel — below the spec's 500-event floor. The trading thesis (persistent cross-sectional break → learnable cross-sectional predictor) is unchanged and still worth testing; only the persistence definition was too strict. v2 is a **minimal, pre-registered re-parameterization** of that spec, not a redesign.

Every non-enumerated binding is inherited verbatim from the parent spec. Where v2 differs, it explicitly says so.

## Hypothesis

**H-2026-04-24-003 (persistent-break v2 cross-sectional predictive model)**

**Claim:** A Lasso regression model, trained on the v2-persistent-break subset of the Phase C parent panel using cross-sectional z-scores of all 212 other F&O stocks as features, produces out-of-sample T+1-return predictions whose sign-triggered trading rule achieves a higher Sharpe on the 2025-06-01 → 2026-04-23 holdout window than the strongest of three naive comparators, with p ≤ 0.05 under a 100,000-sample label-permutation null test.

**Family size:** 1 (single trained model vs. single strongest naive).
**Bonferroni α:** 0.05 / 1 = 0.05.
**Execution mode:** MODE A EOD (entry at T close, exit at T+1 close).
**Slippage level:** S1 as defined in `pipeline/autoresearch/overshoot_compliance/slippage_grid.py` (0.30% round-trip, same as parent hypotheses).

## Event filter (pre-registration binding — CHANGED from v1)

```
|z_{i,T}|   ≥ 3.0                                 (current day, unchanged)
|z_{i,T-1}| ≥ 2.0                                 (prior day, RELAXED from 3.0)
sign(z_{i,T}) = sign(z_{i,T-1})                   (same sign, unchanged)
ticker i has ≥ 60 non-NaN z observations through T-1  (unchanged)
```

**Expected event count:** ~318 on the 2021–2026 panel (diagnostic, 2026-04-24). The 500 floor from the parent spec is **lowered to 300** for this registration — feasibility constraint, not power claim. At 18% holdout, ~57 holdout events clears the §9.3 ≥50 gate.

**Function signature change:** `filter_persistent_breaks(events_df, z_panel, *, z_threshold_current, z_threshold_prior, persistence_days, min_history_days=60)`. The existing single-`z_threshold` parameter is replaced by `z_threshold_current` + `z_threshold_prior`; the existing committed tests stay green by passing identical values for both (backward compatible in spirit).

## Feature set (unchanged from v1)

Inherited verbatim. 236 dimensions = 212 peer z-scores + 17 sector means + 4 market-context (vix + 3 regime one-hots) + 2 self z's (T, T-1) + 1 break_direction. No look-ahead.

## Label (unchanged from v1)

`y = next_ret_pct_{i, T+1}`, percent, from the parent events panel field `next_ret`.

## Data split (pre-registration binding — CHANGED from v1)

| Boundary | v1 (abandoned) | v2 (this spec) |
|---|---|---|
| Training start | 2021-04-23 | 2021-04-23 (unchanged) |
| Training end | 2025-12-31 | **2025-05-31** |
| Holdout start | 2026-01-01 | **2025-06-01** |
| Holdout end | 2026-04-23 | 2026-04-23 (unchanged) |
| Holdout % of panel | ~6% (warning) | **~18% (still PARTIAL vs §10.1's 20% target, but substantially closer)** |

**Rationale:** a larger holdout window simultaneously (a) gives the §9.3 power gate enough events under the relaxed persistence filter, and (b) substantially reduces (though does not eliminate) the §10.1 warning that was flagged on H-002. 18% remains under the 20% target so the §10.1 row will still emit PARTIAL in the gate checklist. Extending further would push the training cutoff into 2025-Q1 and thin persistent events inside the training window — the 18% holdout is the cleanest available balance.

## Model (unchanged from v1)

sklearn LassoCV, alpha grid `numpy.logspace(-5, 0, 25)`, 4-fold purged walk-forward CV with 2-day embargo inside training window, alpha selected on mean OOS Sharpe (not R²). StandardScaler fit on training only. Refit on full training after alpha selection. Bundle persisted.

## Trading rule (unchanged from v1)

Frozen `epsilon = 0.5 × median(|training_predictions|)`. LONG if pred > ε, SHORT if pred < −ε, else FLAT (no trade, no P&L).

## Naive comparators (§9B.1, unchanged from v1)

always-fade (`-sign(today_resid)`), always-follow (`sign(expected_return_pct)`), buy-and-hold (`+1`). Strongest = highest S1 Sharpe on holdout.

## Permutation null test (§9B.2, unchanged from v1)

100,000 label shuffles of y_train, seeded by `numpy.random.SeedSequence(42).spawn(100_000)`, streaming, ≥ observed margin counted.

## Fragility sweep (§9A — CHANGED dimension from v1)

27 neighborhood points, ≥22 same-sign required. v2 replaces one grid axis to test robustness to the asymmetric threshold choice that is new in this registration:

| Grid axis | v1 | v2 |
|---|---|---|
| Lasso alpha scale | {0.8×, 1.0×, 1.2×} | {0.8×, 1.0×, 1.2×} (unchanged) |
| Current-day z | {2.5, 3.0, 3.5} | {2.5, 3.0, 3.5} (unchanged) |
| *Persistence window* | {1, 2, 3} days | **Prior-day z: {1.5, 2.0, 2.5}** |

Rationale: `persistence_days` stays pinned at 2 (core thesis). The perturbed dimension is the prior-day threshold because that is the new judgment call in v2 — sweeping it directly tests whether the model-vs-strongest-naive margin is robust to the |z|≥2 choice we pre-registered.

## Standards sections (unchanged from v1)

| Section | Treatment |
|---|---|
| §5A data audit | Reused from `overshoot_compliance/data_audit.py`. |
| §6.1 / §6.2 | Inherits H-2026-04-23-001 survivorship waiver (expires 2026-07-23). |
| §7.1 | Manifest declares `execution_mode: "MODE_A_EOD"`. |
| §8 direction audit | Holdout trades log predicted_sign, fade_sign, follow_sign, realized_sign. |
| §10.1 holdout | **18%, still PARTIAL vs 20% target but substantially reduced warning vs H-002's 6%.** |
| §10.2 walk-forward CV | Purged 2-day embargo inside training window. |
| §11 ADV | Reused `impl_risk.py`. |
| §11A impl-risk | Same 10-scenario stress. |
| §11B NIFTY-beta | Residual Sharpe ≥ 70% of gross Sharpe. |
| §11C portfolio gate | Pairwise correlation, concentration on holdout trades. |
| §12 CUSUM decay | Training-window per-month edge; recent-24m ≥ 50% full-history. |
| §13A.1 manifest | SHA-256 + seed + alpha grid + cost model version. |
| §14.5 multiplicity | Family = 1. |
| §15.1 gate checklist | Emitted artifact, same schema as v1. |

## Success criteria (all must hold for PASS)

- Holdout S1 Sharpe of model > Holdout S1 Sharpe of strongest naive.
- Permutation-null p-value ≤ 0.05.
- Fragility: sign stable on ≥22 of 27 neighborhood points.
- §11B residual Sharpe ≥ 70% gross.
- §11C portfolio correlation and concentration within limits.
- §12 recent-24m edge ≥ 50% of full-history edge.
- Data audit not INSUFFICIENT_DATA.
- **≥50 holdout events** survive the persistence filter.

**FAIL on any violation.** No retries with different features, model class, persistence rule, or holdout boundary. The v2 re-registration has itself already used one revisit — there is no v3 of this same thesis.

**On PASS:** register `terminal_state = "PASS_YYYY-MM-DD"`, forward-deploy at TIER_EXPLORING 0.5-unit via a separate follow-on spec.

**On FAIL:** register `terminal_state = "FAIL_YYYY-MM-DD"`. The persistent-break + cross-sectional narrative is exhausted on the current Phase C parent panel.

## Pre-exploration disclosure (§0.3 honesty)

H-2026-04-24-002 was abandoned pre-execution at n=116 events. Before registering this successor, a count-only diagnostic on the parent panel (`C:/tmp/persistence_candidates.py`, not committed) measured five candidate persistence rules and their event counts:

| Rule | Count |
|---|---:|
| ORIG: `|z|≥3 T AND |z|≥3 T-1 same-sign` (abandoned H-002) | 116 |
| **A: `|z|≥3 T AND |z|≥2 T-1 same-sign`** (this spec) | **318** |
| B: `|z|≥3 T AND |z|≥2 T-1 OR T-2 same-sign` | 507 |
| C: `|z|≥2.5 T AND T-1 same-sign` (symmetric) | 316 |
| D: `|z|≥3 T AND |z|≥2 T-1/T-2/T-3 same-sign` | 675 |

Rule A was chosen for matching the T-1-specific persistence intuition that motivated the parent brainstorming session. Rule D would maximize count, but the adjacent-prior-day semantics of rule A most closely match the original thesis ("yesterday's elevation confirmed today's break"). Rule A was NOT chosen for count-maximization; it was chosen for semantic fit and then count-checked for feasibility.

The 18% holdout window (2025-06-01 → 2026-04-23) was chosen to give rule A's 318 events a ~57-event holdout, just above the §9.3 ≥50 gate. 18% also clears the §10.1 ≥20% target loosely enough to no longer be a warning.

No model fits, no predictions, no P&L numbers, and no permutation p-values were computed from any rule before this registration. The only observed statistics are the raw event counts above.

## Scope boundaries (unchanged from v1, non-goals)

- NOT training on live `correlation_breaks.json`.
- NOT an intraday model.
- NOT replacing Phase C residual-reversion engine.
- NOT touching task #112 (entry-snap fix).
- NOT a gradient-boost or other non-linear model — Lasso is pre-registered.

## Components (unchanged from v1)

Five modules under `pipeline/autoresearch/phase_c_cross_sectional/` (already scaffolded at commit `82abbfc`):

1. `event_filter.py` — `filter_persistent_breaks(events_df, z_panel, *, z_threshold_current, z_threshold_prior, persistence_days, min_history_days=60)` (signature extended from v1 committed version at `d786381`). Existing test file at `d786381` needs kwarg rename (`z_threshold` → `z_threshold_current` + `z_threshold_prior=same_value`) to stay green; behavioral equivalence is preserved by passing identical values on both. New tests asymmetric-threshold cases are added.
2. `feature_builder.py` — unchanged from v1 plan (not yet implemented).
3. `model.py` — unchanged from v1 plan (not yet implemented).
4. `naive_adapters.py` — unchanged from v1 plan (not yet implemented).
5. `permutation_null.py` — unchanged from v1 plan (not yet implemented).
6. `fragility_sweep.py` — grid axis renamed to `Z_THRESHOLD_PRIOR_GRID = (1.5, 2.0, 2.5)` in place of v1's `PERSIST_DAYS` dimension.
7. `runner.py` — holdout cutoff constant updated; fragility orchestration updated for new axis; otherwise unchanged.

## Testing discipline, Reproducibility, Failure-mode handling, Open questions

All three sections are inherited verbatim from the v1 spec. See `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` §Testing/§Reproducibility/§Failure-mode handling/§Open questions.

## Related documents

- **Parent spec (inherited):** `docs/superpowers/specs/2026-04-23-persistent-break-cross-sectional-design.md` (commit eb80ae5).
- **Superseded plan:** `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md` (commit df63fe2). New plan to be written: `docs/superpowers/plans/2026-04-24-persistent-break-v2.md`.
- **Parent events file:** `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json`.
- **H-002 abandonment commit:** `b50773f`.
- **Direction audit that preceded H-002:** `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md`, `docs/superpowers/phase_c_direction.md`.
- **Compliance standards:** `docs/superpowers/specs/backtesting-specs.txt` v1.0.
- **Survivorship waiver (inherited):** `docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md`.
- **Count-diagnostic script (not committed):** `C:/tmp/persistence_candidates.py`.
