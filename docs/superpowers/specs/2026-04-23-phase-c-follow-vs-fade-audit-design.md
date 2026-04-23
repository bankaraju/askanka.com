# Task #107 — Phase C FOLLOW vs FADE Direction Spec

## 1. Objective

Resolve the thesis mismatch between the **tested Phase C edge** (FADE of residual correlation breaks) and the **live engine behavior** (FOLLOW of expected_return sign), and make direction explicit and auditable for every (ticker, event).

No Phase C promotion or guardrail wiring may proceed until direction is correctly classified and checked.

---

## 2. Core Concepts

### 2.1 Event definition

Each Phase C event is:

- symbol
- event_timestamp
- peer_basket_return over lookback
- symbol_return over lookback
- residual = symbol_return − peer_basket_return
- sigma = residual / residual_vol_estimate
- expected_return (scalar, current sign used by live engine)
- phase_c_label (OPPORTUNITY / WARNING / …)
- tested_edge_p_value (from correlation-breaks backtest, FADE direction)

### 2.2 Direction types

For each event, define an intended trading thesis:

- **FOLLOW**: trade **with** the expected_return sign (e.g. expected_return > 0 → LONG).
- **FADE**: trade **against** the expected_return sign (e.g. expected_return > 0 → SHORT).
- **NEUTRAL**: do not trade; signal is informational only.

Direction is about the *strategic thesis*, not implementation artifacts (e.g. “because the code uses > instead of <”).

---

## 3. Data model additions

Add to the event schema:

- `direction_intended`: `"FOLLOW" | "FADE" | "NEUTRAL"`
- `direction_tested`: `"FOLLOW" | "FADE" | "NEUTRAL"` (what the backtest actually validated)
- `direction_consistent`: `true | false | null`
  - `true` if `direction_intended == direction_tested`
  - `false` if they differ
  - `null` if no tested edge (e.g. no stats for this cell)
- `event_geometry`: `"LAG" | "OVERSHOOT" | "DEGENERATE"`
  - `LAG` when `sign(expected_return) != sign(residual)` — peers moved; stock lagged. Backtest FADE and live FOLLOW agree on the trade side.
  - `OVERSHOOT` when `sign(expected_return) == sign(residual)` — peers moved; stock moved further on the same side. Backtest FADE and live FOLLOW are opposite.
  - `DEGENERATE` when `|expected_return| < 0.1%` or `|residual| < 0.1%`; classification ambiguous, excluded from sub-bucket tests.

`event_geometry` and `direction_consistent` encode the same split from different angles. `direction_consistent == true` ⇔ `event_geometry == LAG`; `direction_consistent == false` ⇔ `event_geometry == OVERSHOOT`. Both fields are persisted so consumers can filter on either.

### 3.1 classify_break code fix

`reverse_regime_breaks.py::classify_break` currently emits `OPPORTUNITY` for both lag and overshoot geometries. Split into two labels:

- `OPPORTUNITY_LAG` — catch-up thesis; tested direction is FOLLOW; backtest FADE and live FOLLOW agree.
- `OPPORTUNITY_OVERSHOOT` — reversion thesis; tested direction is FADE; backtest FADE and live FOLLOW are opposite.

Until the sub-bucket tests (§7.5) complete, `break_signal_generator.py` routes only `OPPORTUNITY_LAG` to signal emission at TIER_EXPLORING. `OPPORTUNITY_OVERSHOOT` becomes an alert-only classification tagged RESEARCH and does not reach the shadow ledger. This is a hard routing rule, not a config flag — the live engine must not trade overshoot-geometry events until a registered FADE hypothesis passes.

For correlation-breaks v1:

- `direction_tested` is **always `"FADE"`** (by construction).
- `direction_intended` is currently **implicitly `"FOLLOW"`** for OPPORTUNITY/positive expected_return in the live engine.

This mismatch must be made explicit.

---

## 4. Engine / backtest wiring

### 4.1 Live engine (Phase C consumers)

- At signal generation time, each Phase C consumer must set `direction_intended` per event, routed by `event_geometry` (not `expected_return` sign alone).
  - Rule (post-§3.1 code fix):
    - `OPPORTUNITY_LAG` → trade the expected_return sign → `direction_intended = "FOLLOW"` (LONG if expected_return > 0, else SHORT).
    - `OPPORTUNITY_OVERSHOOT` → `direction_intended = "NEUTRAL"` (alert-only until §7.5 FADE registration passes).
    - `WARNING` and `POSSIBLE_OPPORTUNITY` → `"NEUTRAL"`.
  - Legacy rule (pre-§3.1, deprecated and retained only for reading historical event logs):
    - `OPPORTUNITY` + `expected_return > 0` → `direction_intended = "FOLLOW"` (LONG).
    - `OPPORTUNITY` + `expected_return < 0` → `direction_intended = "FOLLOW"` (SHORT).

- Persist `direction_intended` into:
  - event logs,
  - any ledger used by unified_backtest to reconstruct live decisions.

### 4.2 Unified backtest

- For each Phase C event, backtest must:

  1. Read `direction_intended`.
  2. Look up `direction_tested` from the correlation-breaks backtest results (currently `"FADE"` for all cells with stats).
  3. Set `direction_consistent` flag per event.

- When re-running strategy backtests:
  - Compute performance separately for:
    - events where `direction_consistent == true`,
    - events where `direction_consistent == false`.

This enables “direction-suspect” classification (see below).

### 4.3 Sub-bucket null tests (precondition for §5 DIRECTION-SUSPECT verdicts)

Raw PnL comparison between sub-buckets is not a significance test. Each slice must get its own bootstrap against an unconditional null before any DIRECTION-SUSPECT verdict is justified.

Procedure per (ticker, direction, slice):

1. Restrict the event set to slice ∈ {LAG, OVERSHOOT} — exclude DEGENERATE.
2. Require `n_events ≥ 10` after the restriction (per §9.1 of backtesting-specs v1.0). Cells with fewer events are reported as `INSUFFICIENT_POWER` and skipped.
3. Run a 100k-permutation bootstrap against the unconditional ticker return distribution, per §9B.2. Reuse the compliance engine from H-2026-04-23-001 — do not write a new permutation loop. The 5-yr panel at `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/` supplies the event inventory; the slice-restricted re-run writes sibling artifacts:
   - `compliance_phase_c_lag_{ticker}_{direction}_*.json`
   - `compliance_phase_c_overshoot_{ticker}_{direction}_*.json`
4. Family size for multiplicity correction is the count of (ticker, direction, slice) cells actually tested (after the n ≥ 10 filter). Bonferroni α = 0.05 / family_size per §14.5 ticker-family scope. BH-FDR at α = 0.05 reported alongside for research context only — survivors stay TIER_EXPLORING per the standing rule.
5. The DIRECTION-SUSPECT rule in §5 is valid only when the tested-direction bootstrap clears Bonferroni on the specific slice. A cell where the full-panel bootstrap was significant but the slice-specific bootstrap is not → the original significance was a mixture artifact, not alpha on the traded geometry.

Defense-stock filter (standing user rule) applies here unchanged: defense tickers are flagged in the per-slice output but not dropped from the event count.

---

## 5. Direction-suspect classification

For each (strategy, ticker, label, direction) cell, compute:

- Sharpe / PnL of the **tested direction** (from correlation-breaks backtest).
- Sharpe / PnL of the **opposite direction**.
- Realised PnL of the **live engine** (FOLLOW path).

Rules:

- If **opposite-direction Sharpe** > tested-direction Sharpe at S0, mark the cell `PARAMETER-FRAGILE-DIRECTION` (this is the “backtest says UP, DOWN actually works better” case).
- If `direction_intended != direction_tested` for a majority of events **and** the tested edge is statistically significant (under Bonferroni or FDR), mark the cell `DIRECTION-SUSPECT`.

Section 8 (Direction audit) implication:

- A strategy containing any `DIRECTION-SUSPECT` Phase C path cannot progress beyond RESEARCH / TIER_EXPLORING until:
  - its thesis is rewritten to match the tested direction, **or**
  - a new backtest is run in the direction it actually trades.

---

## 6. Interaction with FDR FADE edges

### 6.0 Scope limit (added 2026-04-23)

The "Suggested use" bullets below (size-cap, regime-suppress, FADE-product scoping) are **informational only in this spec**. Guardrail implementation is deferred to a separate spec: `docs/superpowers/specs/YYYY-MM-DD-phase-c-fdr-guardrails-design.md`.

Scope of #107 is strictly: direction audit fields + `classify_break` code fix + sub-bucket null tests + §7 gate. Guardrail wiring, size-capping, and FADE-product design are out of scope and should not be bundled into the #107 plan — bundling would make the plan unreviewable and would mix a forensic task with a product design task.

### 6.1 FDR survivor context

From the FDR research memo:

- 5 FADE survivors at BH-FDR α=0.05:
  - TORNTPHARM UP (p=0.00070, +0.935%)
  - 360ONE UP (0.00080, +1.611%)
  - TORNTPOWER UP (0.00120, +1.384%)
  - SBIN UP (0.00130, +1.244%)
  - IDFCFIRSTB DOWN (0.00210, +1.544%)

For these cells:

- `direction_tested = "FADE"`.
- Current engine behavior on overshoots is approximately `"FOLLOW"` of expected_return sign.

Until #107 is complete:

- These 5 are **evidence of FADE alpha** only.
- They must *not* be treated as proof that the current FOLLOW implementation has edge.

Suggested use once #107 is wired:

- Guardrails:
  - For cells with strong FADE edge but FOLLOW live behavior, consider:
    - **Reducing size** (cap) when such events fire.
    - **Suppressing trades** in regimes where FADE edge is strong and FOLLOW is weak.
- Future FADE product:
  - If a dedicated FADE strategy is ever built, these cells are natural starting candidates, subject to a fresh hypothesis and backtest in FADE direction.

---

## 7. Promotion conditions for Phase C

Phase C remains TIER_EXPLORING until **all** of the following hold:

1. Direction mapping:
   - `direction_intended` is defined for all live Phase C events.
   - `direction_tested` is defined for all cells with backtest stats.
   - `direction_consistent` is computed and surfaced.

2. Direction audit:
   - No `DIRECTION-SUSPECT` cells in the deployable path, or an explicit waiver exists.
   - For any cell used in deployment:
     - the **tested** edge and the **live** thesis match (both FOLLOW or both FADE).

3. Multiplicity:
   - Any “Phase C is deployable” claim uses a **Bonferroni-corrected** bar.
   - FDR-only survivors are tagged as RESEARCH / TIER_EXPLORING only.

4. Documentation:
   - A short note in `docs/superpowers/phase_c_direction.md` explaining:
     - what direction is tested,
     - what direction is traded,
     - how inconsistencies are flagged and resolved.

5. Pre-registration (§0.3 of backtesting-specs v1.0):
   - The sub-bucket null tests in §4.3 are new hypotheses and must be pre-registered in `docs/superpowers/hypothesis-registry.jsonl` **before** thresholds are set, slice-specific p-values are computed, or any promotion claim is made. The two registrations are distinct families:
     - `H-2026-04-XX-LAG`: FOLLOW on `OPPORTUNITY_LAG` events. Tests the live engine's current thesis on the subset where it is, in fact, running the residual-reversion bet.
     - `H-2026-04-XX-OVERSHOOT`: FADE on `OPPORTUNITY_OVERSHOOT` events. Tests the opposite of what the live engine does today; passing this + failing `LAG` would mean the live engine is actively mis-trading overshoots.
   - Threshold-setting rule: may NOT be derived from the slice's observed numbers. Use the same `claimed_edge` shape as H-2026-04-23-001 (net T+1 ≥ 0.5%, hit-rate ≥ 55%, p ≤ 1e-4) for framework consistency. Deviation requires an explicit justification in the registry entry.
   - Family-size declaration: each registration's `primary_family_size_estimate` is the post-filter cell count (after n ≥ 10 survives); Bonferroni adjusted α is `0.05 / family_size`.

Only after this can Phase C be reconsidered for promotion above TIER_EXPLORING.

---

## Markup log

### 2026-04-23 — gap-fill pass 1

Added by assistant after comparing the original spec against memory sketch `project_phase_c_follow_vs_fade_audit.md` and the H-2026-04-23-001 FDR research memo.

1. **§3 — `event_geometry` field added.** The original spec only had `direction_consistent` as a derived boolean; the geometric LAG/OVERSHOOT/DEGENERATE encoding makes the physical split persistable and filterable at both the event log and the backtest level.
2. **§3.1 — `classify_break` code fix added.** Without splitting `OPPORTUNITY` → `OPPORTUNITY_LAG` / `OPPORTUNITY_OVERSHOOT` at classification time, the signal generator has no mechanism to route by geometry and §4.1's rule is unimplementable.
3. **§4.1 — example rule rewritten to route on geometry label, not raw `expected_return` sign.** The legacy rule is retained (commented-deprecated) only for reading historical event logs.
4. **§4.3 — sub-bucket null-test procedure added.** Original §4.2 said "compute performance separately for the two slices" but not how to establish significance. Without a slice-specific 100k bootstrap the §5 DIRECTION-SUSPECT rule has no statistical basis. The re-run reuses the H-2026-04-23-001 compliance engine rather than introducing a new permutation loop.
5. **§6.0 — scope limit added.** The original §6 "Suggested use" section had the seeds of a separate product — size-cap, regime-suppress, FADE-product scoping. Explicitly deferred to a standalone guardrails spec so #107's plan stays reviewable.
6. **§7.5 — pre-registration step added.** Both sub-bucket tests are new hypotheses under §0.3 of backtesting-specs v1.0. Thresholds must be set from framework consistency (copy H-2026-04-23-001's shape), not from the slice's observed numbers. Registration happens before the bootstrap, not after.

### Sections unchanged from the original

§1, §2 (concepts), §5 (DIRECTION-SUSPECT label rules), §6.1 FDR survivor list, §7 items 1–4. The original spec's framing was sound — the markup is gap-fills, not rewrites.

---