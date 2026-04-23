# Phase C FOLLOW vs FADE Direction Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Phase C `OPPORTUNITY` label into `OPPORTUNITY_LAG` (live engine aligned with backtest) and `OPPORTUNITY_OVERSHOOT` (live engine opposite to backtest), route only `OPPORTUNITY_LAG` to signal emission, and produce Bonferroni-scored evidence for each geometric slice so the DIRECTION-SUSPECT gate in the spec has statistical footing.

**Architecture:** Layered, additive change on top of the existing Phase C classifier and the existing H-2026-04-23-001 compliance runner. No new permutation loops — the slice-restricted compliance run reuses `pipeline/autoresearch/overshoot_compliance/runner.py`, filtered to a single geometry slice. Pre-registration (§0.3 backtesting-specs) comes first; data model changes second; code-fix + routing third; slice compliance runs fourth; DIRECTION-SUSPECT classifier fifth; docs + memory sync last.

**Tech Stack:** Python 3.11, pandas, numpy, pytest, existing FastAPI terminal backend, vanilla JS terminal frontend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` (commit 3bc574d).

**Scope boundary:** `classify_break` split + direction fields + sub-bucket null tests + DIRECTION-SUSPECT classifier + UI copy updates + docs note. Guardrails (size-cap, regime-suppress, FADE product) are explicitly out of scope per §6.0 of the spec.

---

## File Structure

**New files:**
- `pipeline/autoresearch/overshoot_compliance/runner_phase_c_slice.py` — slice-restricted compliance runner (wrapper over `runner.py` that filters by `event_geometry` before event enumeration)
- `pipeline/autoresearch/overshoot_compliance/direction_suspect.py` — §5 classifier that reads slice artifacts and emits per-cell DIRECTION-SUSPECT / PARAMETER-FRAGILE-DIRECTION / CLEAN verdicts
- `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py` — tests for the new geometry classifier + label split
- `pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py` — tests for slice filtering
- `pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py` — tests for DIRECTION-SUSPECT rules
- `docs/superpowers/phase_c_direction.md` — promotion-condition §4 docs note (what's tested, what's traded, how mismatch is flagged)

**Modified files:**
- `pipeline/autoresearch/reverse_regime_breaks.py` — add `classify_event_geometry`, split `classify_break` output into `OPPORTUNITY_LAG` / `OPPORTUNITY_OVERSHOOT`, emit new fields in `scan_for_breaks`
- `pipeline/break_signal_generator.py` — route only `OPPORTUNITY_LAG` to actionable signals; `OPPORTUNITY_OVERSHOOT` becomes informational
- `pipeline/phase_c_shadow.py` — skip `OPPORTUNITY_OVERSHOOT` in shadow ledger (no entry row, no TIME_STOP close)
- `pipeline/telegram_bot.py` — render `OPPORTUNITY_LAG` and `OPPORTUNITY_OVERSHOOT` with distinct copy; overshoot rows labelled RESEARCH-ONLY
- `pipeline/terminal/static/js/components/positions-table.js` — break-detail sub-row names geometry
- `pipeline/terminal/static/js/pages/research.js` — research digest split rendering
- `docs/superpowers/hypothesis-registry.jsonl` — append H-2026-04-23-002 (LAG) and H-2026-04-23-003 (OVERSHOOT)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — Phase C section updated for new label vocabulary
- `memory/project_overshoot_reversion_backtest.md` — note audit completion + slice findings
- `memory/project_phase_c_follow_vs_fade_audit.md` — mark the pre-spec sketch as superseded by design doc
- `.claude/projects/.../memory/MEMORY.md` — index entry for DIRECTION-SUSPECT verdicts

**Unchanged but touched for verification:**
- `pipeline/autoresearch/overshoot_compliance/runner.py` — the slice wrapper delegates here; no logic changes
- `pipeline/autoresearch/overshoot_compliance/perm_scaling.py` — reused unchanged
- `pipeline/autoresearch/overshoot_compliance/gate_checklist.py` — reused unchanged

---

## Task Ordering Rationale

1. **Tasks 1-2: Pre-registration (§7.5).** Register both new hypothesis families *before* any code that computes slice p-values exists, per §0.3 of backtesting-specs v1.0. Thresholds copy H-2026-04-23-001's shape (net T+1 ≥ 0.5%, hit ≥ 55%, p ≤ 1e-4) for framework consistency.
2. **Tasks 3-5: Geometry classifier + label split.** Pure-function additions, easy TDD, ship before any consumer change.
3. **Tasks 6-8: Consumer updates.** Engine, shadow ledger, Telegram, UI — routing changes riding on the new labels.
4. **Tasks 9-10: Slice-restricted compliance runner.** Reuses existing engine; tests prove filter correctness; smoke run on a single ticker validates wire-up.
5. **Tasks 11-12: The actual compliance runs.** Each is one command + artifact commit. Overnight compute.
6. **Tasks 13-14: DIRECTION-SUSPECT classifier + integration.** Reads committed artifacts; emits per-cell verdicts.
7. **Tasks 15-16: Docs + memory sync.** Per CLAUDE.md doc-sync mandate.

---

### Task 1: Pre-register H-2026-04-23-002 (LAG family)

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl`

**Rationale:** Per §7.5 of the spec and §0.3 of backtesting-specs v1.0, pre-registration must happen before thresholds are set or slice p-values are computed. This task writes the registry entry with thresholds copied from H-2026-04-23-001's shape.

- [ ] **Step 1: Append the LAG family registration line**

Append a single JSON line (no line break inside) to `docs/superpowers/hypothesis-registry.jsonl`:

```json
{"hypothesis_id": "H-2026-04-23-002", "author": "bharatankaraju", "date_registered": "2026-04-23", "strategy_name": "phase-c-lag-follow-eod", "strategy_class": "residual-reversion-lag", "description": "FOLLOW trades on Phase C OPPORTUNITY_LAG events — the geometric slice where sign(expected_return) != sign(residual). Backtest FADE direction and live engine FOLLOW direction agree on this slice by construction. Entry LONG if expected_return>0 else SHORT at EOD close; exit T+1 close. MODE A EOD. Registered as a distinct family from H-2026-04-23-001 because the event-restriction changes the null distribution and the family size.", "claimed_edge": {"metric": "net_mean_next_day_edge_pct", "threshold": 0.5, "units": "percent", "slippage_level": "S1", "hit_rate_min": 0.55, "alpha_for_significance": 0.05, "multiplicity_correction": "bonferroni", "ci_level": 0.95, "notes": "Thresholds copied from H-2026-04-23-001 for framework consistency (spec §7.5). Not derived from slice's observed numbers (§0.3 pre-registration rule)."}, "universe": {"source": "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/permutations_100k.json filtered to event_geometry==LAG", "point_in_time_compliant": false, "survivorship_status": "UNCORRECTED-PENDING-fno_universe_history — inherited from H-2026-04-23-001", "n_tickers_current": 213, "coverage_ratio_estimate_pct_delisted": "<5% per H-2026-04-23-001 waiver"}, "date_range": {"start": "2021-04-23", "end": "2026-01-23", "holdout_start": "2026-01-24", "holdout_end": "2026-04-23", "holdout_pct": 0.06, "notes": "Inherits H-2026-04-23-001 holdout window; same 3-month forward slice."}, "statistical_test": {"method": "bootstrap_against_unconditional_ticker_return_distribution", "n_permutations_required": 100000, "rationale": "Reuse H-2026-04-23-001 compliance engine — see runner_phase_c_slice.py. Family size depends on post-filter cell count (n>=10 after LAG-only restriction)."}, "hypothesis_family_scope": {"primary": "ticker-family-slice", "primary_family_size_estimate": "TBD_post_filter", "audit_scopes": ["strategy-class:residual-reversion-lag", "geometry:LAG", "universe-scope:F&O-213"], "notes": "Family size finalized after n>=10 filter applies — written into the slice run's manifest.json."}, "execution_mode": "MODE_A_EOD_close_to_close", "power_analysis": {"required_n_per_ticker_regime": 30, "regimes_required": 3, "min_detectable_effect_pct_at_80_power": "to be computed per cell from the slice's standard deviation before gate evaluation"}, "pre_exploration_disclosure": "The parent hypothesis H-2026-04-23-001 was executed and failed Bonferroni (0 survivors at 1.17e-4). An FDR research memo flagged 5 positive-edge survivors at BH-FDR alpha=0.05; separately, the spec 2026-04-23-phase-c-follow-vs-fade-audit-design.md observed that backtest FADE and live engine FOLLOW agree on LAG-geometry events but disagree on OVERSHOOT-geometry events. This registration tests the LAG slice in isolation. No slice p-values have been computed prior to this registration. No thresholds are derived from slice-observed numbers — all thresholds copied from H-2026-04-23-001 (Section 0.3 pre-registration upheld).", "status": "PRE_REGISTERED", "terminal_state": null, "git_commit_at_registration": null, "standards_version": "1.0_2026-04-23", "raw_bar_canonicity_policy": "docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md v1.0 — MODE A T, T+1 execution window gate applies."}
```

- [ ] **Step 2: Commit the registration**

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: H-2026-04-23-002 Phase C LAG-slice FOLLOW hypothesis"
```

- [ ] **Step 3: Update `git_commit_at_registration`**

After the commit lands, get the SHA and update the line in-place so the entry points to the commit that birthed it.

```bash
git rev-parse HEAD
```

Copy the SHA (first 7 chars is fine for readability), then edit `docs/superpowers/hypothesis-registry.jsonl` and replace `"git_commit_at_registration": null` with `"git_commit_at_registration": "<sha>"` on the line added in Step 1. Then:

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: backfill H-2026-04-23-002 registration commit SHA"
```

---

### Task 2: Pre-register H-2026-04-23-003 (OVERSHOOT family)

**Files:**
- Modify: `docs/superpowers/hypothesis-registry.jsonl`

- [ ] **Step 1: Append the OVERSHOOT family registration line**

Append a single JSON line to `docs/superpowers/hypothesis-registry.jsonl`:

```json
{"hypothesis_id": "H-2026-04-23-003", "author": "bharatankaraju", "date_registered": "2026-04-23", "strategy_name": "phase-c-overshoot-fade-eod", "strategy_class": "residual-reversion-overshoot", "description": "FADE trades on Phase C OPPORTUNITY_OVERSHOOT events — the geometric slice where sign(expected_return) == sign(residual). Backtest FADE direction and live engine FOLLOW direction are opposite on this slice by construction. Entry SHORT if expected_return>0 else LONG at EOD close (the OPPOSITE of what the live engine does today); exit T+1 close. MODE A EOD. If this passes and H-2026-04-23-002 does not, the live engine is actively mis-trading overshoot events.", "claimed_edge": {"metric": "net_mean_next_day_edge_pct", "threshold": 0.5, "units": "percent", "slippage_level": "S1", "hit_rate_min": 0.55, "alpha_for_significance": 0.05, "multiplicity_correction": "bonferroni", "ci_level": 0.95, "notes": "Thresholds copied from H-2026-04-23-001 for framework consistency (spec §7.5). Not derived from slice's observed numbers (§0.3 pre-registration rule)."}, "universe": {"source": "pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/permutations_100k.json filtered to event_geometry==OVERSHOOT", "point_in_time_compliant": false, "survivorship_status": "UNCORRECTED-PENDING-fno_universe_history — inherited from H-2026-04-23-001", "n_tickers_current": 213, "coverage_ratio_estimate_pct_delisted": "<5% per H-2026-04-23-001 waiver"}, "date_range": {"start": "2021-04-23", "end": "2026-01-23", "holdout_start": "2026-01-24", "holdout_end": "2026-04-23", "holdout_pct": 0.06, "notes": "Inherits H-2026-04-23-001 holdout window; same 3-month forward slice."}, "statistical_test": {"method": "bootstrap_against_unconditional_ticker_return_distribution", "n_permutations_required": 100000, "rationale": "Reuse H-2026-04-23-001 compliance engine — see runner_phase_c_slice.py. Family size depends on post-filter cell count (n>=10 after OVERSHOOT-only restriction)."}, "hypothesis_family_scope": {"primary": "ticker-family-slice", "primary_family_size_estimate": "TBD_post_filter", "audit_scopes": ["strategy-class:residual-reversion-overshoot", "geometry:OVERSHOOT", "universe-scope:F&O-213"], "notes": "Family size finalized after n>=10 filter applies — written into the slice run's manifest.json."}, "execution_mode": "MODE_A_EOD_close_to_close", "power_analysis": {"required_n_per_ticker_regime": 30, "regimes_required": 3, "min_detectable_effect_pct_at_80_power": "to be computed per cell from the slice's standard deviation before gate evaluation"}, "pre_exploration_disclosure": "Same as H-2026-04-23-002. No slice p-values computed before registration. No thresholds derived from slice-observed numbers.", "status": "PRE_REGISTERED", "terminal_state": null, "git_commit_at_registration": null, "standards_version": "1.0_2026-04-23", "raw_bar_canonicity_policy": "docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md v1.0 — MODE A T, T+1 execution window gate applies."}
```

- [ ] **Step 2: Commit + backfill SHA**

Same two-commit pattern as Task 1.

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: H-2026-04-23-003 Phase C OVERSHOOT-slice FADE hypothesis"
git rev-parse HEAD
```

Then edit the line to replace `"git_commit_at_registration": null` with the SHA and commit again:

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: backfill H-2026-04-23-003 registration commit SHA"
```

---

### Task 3: Add `classify_event_geometry` pure function

**Files:**
- Modify: `pipeline/autoresearch/reverse_regime_breaks.py`
- Create: `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py`

**Rationale:** Pure function that maps `(expected_return, actual_return)` to `"LAG" | "OVERSHOOT" | "DEGENERATE"`. This is the ground-truth geometric classifier that every downstream consumer references.

- [ ] **Step 1: Write the failing test file**

Create `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py`:

```python
"""Tests for the geometric classifier in reverse_regime_breaks."""
import pytest

from pipeline.autoresearch.reverse_regime_breaks import classify_event_geometry


class TestClassifyEventGeometry:
    def test_lag_same_direction_undershoot(self):
        # expected +2%, actual +0.5% → residual -1.5% → signs differ → LAG
        assert classify_event_geometry(expected_return=2.0, actual_return=0.5) == "LAG"

    def test_overshoot_same_direction(self):
        # expected +2%, actual +3% → residual +1% → signs same → OVERSHOOT
        assert classify_event_geometry(expected_return=2.0, actual_return=3.0) == "OVERSHOOT"

    def test_lag_opposite_direction(self):
        # expected +2%, actual -1% → residual -3% → signs differ → LAG (FADE and FOLLOW agree: both LONG)
        assert classify_event_geometry(expected_return=2.0, actual_return=-1.0) == "LAG"

    def test_overshoot_negative_direction(self):
        # expected -2%, actual -3% → residual -1% → signs same (both negative) → OVERSHOOT
        assert classify_event_geometry(expected_return=-2.0, actual_return=-3.0) == "OVERSHOOT"

    def test_lag_negative_direction_undershoot(self):
        # expected -2%, actual -0.5% → residual +1.5% → signs differ → LAG
        assert classify_event_geometry(expected_return=-2.0, actual_return=-0.5) == "LAG"

    def test_degenerate_tiny_expected(self):
        # |expected| < 0.1% → DEGENERATE
        assert classify_event_geometry(expected_return=0.05, actual_return=3.0) == "DEGENERATE"

    def test_degenerate_tiny_residual(self):
        # expected 2%, actual 2.05% → residual 0.05% → |residual| < 0.1% → DEGENERATE
        assert classify_event_geometry(expected_return=2.0, actual_return=2.05) == "DEGENERATE"

    def test_degenerate_negative_tiny_expected(self):
        assert classify_event_geometry(expected_return=-0.05, actual_return=-2.0) == "DEGENERATE"

    def test_boundary_at_01pct(self):
        # exactly 0.1% on both is NOT degenerate (strict less-than)
        assert classify_event_geometry(expected_return=0.1, actual_return=2.0) != "DEGENERATE"
```

- [ ] **Step 2: Run to verify the tests fail with ImportError**

```bash
cd C:/Users/Claude_Anka/askanka.com
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py -v
```

Expected: `ImportError: cannot import name 'classify_event_geometry' from 'pipeline.autoresearch.reverse_regime_breaks'`

- [ ] **Step 3: Implement `classify_event_geometry`**

Open `pipeline/autoresearch/reverse_regime_breaks.py` and insert BEFORE the existing `def classify_break` at line 110:

```python
# ===================================================================
# Geometric classifier (spec §3)
# ===================================================================
# Inputs are in PERCENT (e.g. 2.0 means 2%). Matches scan_for_breaks line 365.
_DEGENERATE_THRESHOLD_PCT = 0.1  # absolute percent


def classify_event_geometry(expected_return: float, actual_return: float) -> str:
    """
    Classify a Phase C event by its geometric geometry per spec §3:

      LAG         — sign(expected_return) != sign(residual)
                    Peers moved; stock lagged or went opposite.
                    Backtest FADE and live engine FOLLOW agree on trade side.
      OVERSHOOT   — sign(expected_return) == sign(residual)
                    Peers moved; stock moved further on the same side.
                    Backtest FADE and live engine FOLLOW are opposite.
      DEGENERATE  — |expected_return| < 0.1% or |residual| < 0.1%
                    Classification ambiguous; excluded from sub-bucket tests.

    residual = actual_return - expected_return (matches line 369).
    """
    residual = actual_return - expected_return
    if abs(expected_return) < _DEGENERATE_THRESHOLD_PCT or abs(residual) < _DEGENERATE_THRESHOLD_PCT:
        return "DEGENERATE"
    same_sign = (expected_return > 0 and residual > 0) or (expected_return < 0 and residual < 0)
    return "OVERSHOOT" if same_sign else "LAG"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/reverse_regime_breaks.py pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py
git commit -m "feat(phase-c): add classify_event_geometry (LAG/OVERSHOOT/DEGENERATE)"
```

---

### Task 4: Split `classify_break` OPPORTUNITY into OPPORTUNITY_LAG / OPPORTUNITY_OVERSHOOT

**Files:**
- Modify: `pipeline/autoresearch/reverse_regime_breaks.py` (lines 110-162)
- Modify: `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py` (add more tests)

- [ ] **Step 1: Add failing tests for the split**

Append to `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py`:

```python
from pipeline.autoresearch.reverse_regime_breaks import classify_break


class TestClassifyBreakLabelSplit:
    def test_lag_opportunity_yields_opportunity_lag(self):
        # expected +2%, actual +0.5% → LAG; PCR agrees; no anomaly → OPPORTUNITY_LAG
        label, action = classify_break(
            expected_return=2.0, actual_return=0.5,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "OPPORTUNITY_LAG"
        assert action == "ADD"

    def test_overshoot_opportunity_yields_opportunity_overshoot(self):
        # expected +2%, actual +3% → OVERSHOOT; PCR agrees; no anomaly → OPPORTUNITY_OVERSHOOT (alert-only)
        label, action = classify_break(
            expected_return=2.0, actual_return=3.0,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "OPPORTUNITY_OVERSHOOT"
        # action for overshoot is ALERT, not ADD — signals must not be traded
        assert action == "ALERT"

    def test_degenerate_yields_uncertain(self):
        # expected 0.05%, actual 3% → DEGENERATE → UNCERTAIN, HOLD
        label, action = classify_break(
            expected_return=0.05, actual_return=3.0,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "UNCERTAIN"
        assert action == "HOLD"

    def test_warning_branch_unchanged(self):
        # Existing WARNING decision-matrix branch must not be affected by the split
        label, action = classify_break(
            expected_return=2.0, actual_return=0.5,
            z_score=3.0, pcr_class="BEARISH", oi_anomaly=True,
        )
        assert label == "WARNING"
        assert action == "REDUCE"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py::TestClassifyBreakLabelSplit -v
```

Expected: first three tests fail with `AssertionError` (current code returns `"OPPORTUNITY"` + `"ADD"`). Fourth should already pass.

- [ ] **Step 3: Update `classify_break` to emit the split labels**

In `pipeline/autoresearch/reverse_regime_breaks.py`, replace lines 138-162 (the body of `classify_break`) with:

```python
    # Degenerate geometry is uncertain — too small to classify
    geometry = classify_event_geometry(expected_return, actual_return)
    if geometry == "DEGENERATE":
        return "UNCERTAIN", "HOLD"

    # Determine if price is lagging or moving opposite (legacy decision matrix)
    same_direction = (expected_return >= 0 and actual_return >= 0) or \
                     (expected_return < 0 and actual_return < 0)

    is_lagging = same_direction or abs(actual_return) < abs(expected_return) * 0.3
    is_opposite = not same_direction and abs(actual_return) > abs(expected_return) * 0.3

    if is_lagging and not is_opposite:
        # Price is lagging expected move OR overshooting same-direction
        if pcr_agrees_with_expected(pcr_class, expected_return) and not oi_anomaly:
            # Split OPPORTUNITY by geometry — spec §3.1
            if geometry == "LAG":
                return "OPPORTUNITY_LAG", "ADD"
            # geometry == "OVERSHOOT": alert-only until H-2026-04-23-003 passes
            return "OPPORTUNITY_OVERSHOOT", "ALERT"
        elif pcr_class == "NEUTRAL" and not oi_anomaly:
            return "POSSIBLE_OPPORTUNITY", "HOLD"
        elif pcr_disagrees_with_expected(pcr_class, expected_return) or oi_anomaly:
            return "WARNING", "REDUCE"
        else:
            return "POSSIBLE_OPPORTUNITY", "HOLD"
    elif is_opposite:
        pcr_agrees_with_break = pcr_agrees_with_expected(pcr_class, actual_return)
        if pcr_agrees_with_break and oi_anomaly:
            return "CONFIRMED_WARNING", "EXIT"
        elif not pcr_agrees_with_break and not oi_anomaly:
            return "UNCERTAIN", "HOLD"
        elif oi_anomaly:
            return "WARNING", "REDUCE"
        else:
            return "UNCERTAIN", "HOLD"
    else:
        return "UNCERTAIN", "HOLD"
```

Also update the docstring at line 117-128:

```python
    """
    Classify a correlation break according to the decision matrix.

    Returns (classification, action) tuple.

    Matrix (post-§3.1 geometric split):
      LAG-geometry + PCR agrees + no anomaly      -> OPPORTUNITY_LAG, ADD
      OVERSHOOT-geometry + PCR agrees + no anom   -> OPPORTUNITY_OVERSHOOT, ALERT
      Either geometry + PCR neutral + no anomaly  -> POSSIBLE_OPPORTUNITY, HOLD
      Either geometry + PCR disagrees or anomaly  -> WARNING, REDUCE
      Opposite + PCR agrees w/ break + anomaly    -> CONFIRMED_WARNING, EXIT
      Opposite + PCR disagrees + no anomaly       -> UNCERTAIN, HOLD
      Degenerate geometry                         -> UNCERTAIN, HOLD

    OPPORTUNITY_OVERSHOOT carries action=ALERT (not ADD): it is an alert-only
    classification until H-2026-04-23-003 (FADE hypothesis) passes. See
    docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md §3.1.
    """
```

- [ ] **Step 4: Run full test file**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/autoresearch/reverse_regime_breaks.py pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py
git commit -m "feat(phase-c): split OPPORTUNITY into OPPORTUNITY_LAG / OPPORTUNITY_OVERSHOOT"
```

---

### Task 5: Emit direction + geometry fields in `scan_for_breaks` output

**Files:**
- Modify: `pipeline/autoresearch/reverse_regime_breaks.py` (lines 375-445, inside `scan_for_breaks` and `save_breaks`)
- Modify: `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py`

**Rationale:** Each break record written to `correlation_breaks.json` must now carry `event_geometry`, `direction_intended`, `direction_tested`, and `direction_consistent` per spec §3 + §4.1.

- [ ] **Step 1: Add a failing test for enriched output**

Append to `pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py`:

```python
from pipeline.autoresearch.reverse_regime_breaks import enrich_break_with_direction


class TestEnrichBreakWithDirection:
    def test_lag_break_direction_follow(self):
        brk = {
            "symbol": "RELIANCE",
            "expected_return": 2.0,
            "actual_return": 0.5,
            "classification": "OPPORTUNITY_LAG",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "LAG"
        assert enriched["direction_intended"] == "FOLLOW"
        assert enriched["direction_tested"] == "FADE"
        assert enriched["direction_consistent"] is True  # FADE and FOLLOW agree on LAG by construction
        assert enriched["trade_rec"] == "LONG"  # expected_return > 0

    def test_overshoot_break_direction_neutral(self):
        brk = {
            "symbol": "TORNTPOWER",
            "expected_return": 2.0,
            "actual_return": 3.0,
            "classification": "OPPORTUNITY_OVERSHOOT",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "OVERSHOOT"
        assert enriched["direction_intended"] == "NEUTRAL"  # alert-only
        assert enriched["direction_tested"] == "FADE"
        assert enriched["direction_consistent"] is False
        assert enriched["trade_rec"] is None  # no trade

    def test_warning_break_direction_neutral(self):
        brk = {
            "symbol": "SBIN",
            "expected_return": 2.0,
            "actual_return": 0.5,
            "classification": "WARNING",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["direction_intended"] == "NEUTRAL"
        assert enriched["trade_rec"] is None

    def test_negative_expected_follow_is_short(self):
        brk = {
            "symbol": "IDFCFIRSTB",
            "expected_return": -2.0,
            "actual_return": -0.5,
            "classification": "OPPORTUNITY_LAG",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "LAG"
        assert enriched["trade_rec"] == "SHORT"
```

- [ ] **Step 2: Run tests to verify they fail with ImportError**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py::TestEnrichBreakWithDirection -v
```

Expected: `ImportError: cannot import name 'enrich_break_with_direction'`

- [ ] **Step 3: Implement `enrich_break_with_direction` and wire it into `scan_for_breaks`**

Add the following function to `pipeline/autoresearch/reverse_regime_breaks.py` immediately after `classify_break` (around line 163):

```python
def enrich_break_with_direction(brk: dict) -> dict:
    """
    Add direction-audit fields to a break record (spec §3 + §4.1).

    Mutates and returns the input dict. Computes:
      - event_geometry (LAG/OVERSHOOT/DEGENERATE)
      - direction_intended (FOLLOW/NEUTRAL — FADE is currently never intended)
      - direction_tested (FADE — hard-coded per spec for correlation-breaks v1)
      - direction_consistent (bool) — True iff geometry==LAG (backtest FADE and
        live FOLLOW agree on LAG by construction)
      - trade_rec (LONG/SHORT/None) — None for overshoots and non-actionable labels
    """
    expected = brk.get("expected_return", 0.0)
    actual = brk.get("actual_return", 0.0)
    classification = brk.get("classification", "")

    geometry = classify_event_geometry(expected, actual)
    brk["event_geometry"] = geometry
    brk["direction_tested"] = "FADE"

    if classification == "OPPORTUNITY_LAG":
        brk["direction_intended"] = "FOLLOW"
        brk["direction_consistent"] = True
        brk["trade_rec"] = "LONG" if expected > 0 else "SHORT"
    elif classification == "OPPORTUNITY_OVERSHOOT":
        brk["direction_intended"] = "NEUTRAL"
        brk["direction_consistent"] = False
        brk["trade_rec"] = None
    else:
        brk["direction_intended"] = "NEUTRAL"
        brk["direction_consistent"] = None
        brk["trade_rec"] = None

    return brk
```

Then wire it into `scan_for_breaks`. Find the section around line 378-410 where each break dict is constructed and appended. After `classification, action = classify_break(...)`, call the enricher on the break dict before appending. Example (adapt to the real append point):

```python
        label, action = classify_break(
            expected_return=expected_return,
            actual_return=actual_return,
            z_score=z_score,
            pcr_class=pcr_class,
            oi_anomaly=oi_anomaly,
        )

        brk = {
            "symbol": symbol,
            "timestamp": datetime.now(IST).isoformat(),
            "expected_return": expected_return,
            "actual_return": actual_return,
            "z_score": z_score,
            "classification": label,
            "action": action,
            "regime": regime,
            "pcr_class": pcr_class,
            "oi_anomaly": oi_anomaly,
            # ... existing fields ...
        }
        brk = enrich_break_with_direction(brk)
        breaks.append(brk)
```

Note: the exact field list must match what already exists in `scan_for_breaks`. Do not remove any existing fields — only add the four new ones via `enrich_break_with_direction`.

- [ ] **Step 4: Run tests to verify pass**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py -v
```

Expected: 17 passed.

- [ ] **Step 5: Smoke-run the scanner on one symbol to check output shape**

```bash
PYTHONPATH=. python -c "
from pipeline.autoresearch.reverse_regime_breaks import enrich_break_with_direction
brk = {'symbol': 'TEST', 'expected_return': 2.0, 'actual_return': 3.0, 'classification': 'OPPORTUNITY_OVERSHOOT'}
import json
print(json.dumps(enrich_break_with_direction(brk), indent=2))
"
```

Expected output includes the four new fields. No exceptions.

- [ ] **Step 6: Commit**

```bash
git add pipeline/autoresearch/reverse_regime_breaks.py pipeline/tests/autoresearch/test_reverse_regime_breaks_geometry.py
git commit -m "feat(phase-c): emit event_geometry + direction fields in correlation_breaks.json"
```

---

### Task 6: Update `break_signal_generator.py` to route only OPPORTUNITY_LAG to signals

**Files:**
- Modify: `pipeline/break_signal_generator.py`
- Create: `pipeline/tests/test_break_signal_generator_geometry.py`

- [ ] **Step 1: Write failing routing test**

Create `pipeline/tests/test_break_signal_generator_geometry.py`:

```python
"""Routing tests for the post-§3.1 geometry-aware signal generator."""
from pipeline.break_signal_generator import generate_signals_from_breaks


class TestGeometryRouting:
    def _make_break(self, symbol, classification, expected, actual, trade_rec):
        return {
            "symbol": symbol,
            "classification": classification,
            "expected_return": expected,
            "actual_return": actual,
            "z_score": 3.5,
            "event_geometry": "LAG" if classification == "OPPORTUNITY_LAG" else "OVERSHOOT",
            "direction_intended": "FOLLOW" if classification == "OPPORTUNITY_LAG" else "NEUTRAL",
            "direction_tested": "FADE",
            "direction_consistent": classification == "OPPORTUNITY_LAG",
            "trade_rec": trade_rec,
            "regime": "NEUTRAL",
            "oi_anomaly": False,
        }

    def test_lag_opportunity_emits_signal(self):
        breaks = [self._make_break("RELIANCE", "OPPORTUNITY_LAG", 2.0, 0.5, "LONG")]
        signals = generate_signals_from_breaks(breaks, scan_date="2026-04-23", scan_time="2026-04-23T11:00:00+05:30")
        assert len(signals) == 1
        assert signals[0]["_break_metadata"]["classification"] == "OPPORTUNITY_LAG"
        assert signals[0]["_break_metadata"]["event_geometry"] == "LAG"

    def test_overshoot_opportunity_does_not_emit_signal(self):
        breaks = [self._make_break("TORNTPOWER", "OPPORTUNITY_OVERSHOOT", 2.0, 3.0, None)]
        signals = generate_signals_from_breaks(breaks, scan_date="2026-04-23", scan_time="2026-04-23T11:00:00+05:30")
        assert signals == []

    def test_legacy_opportunity_label_not_emitted(self):
        """Historic correlation_breaks.json may still have bare OPPORTUNITY label.
        The signal generator must not emit a signal for that — only OPPORTUNITY_LAG."""
        breaks = [self._make_break("LEGACY", "OPPORTUNITY", 2.0, 0.5, "LONG")]
        breaks[0]["event_geometry"] = "LAG"
        signals = generate_signals_from_breaks(breaks, scan_date="2026-04-23", scan_time="2026-04-23T11:00:00+05:30")
        assert signals == []
```

- [ ] **Step 2: Run tests — expect 2 failures**

```bash
PYTHONPATH=. pytest pipeline/tests/test_break_signal_generator_geometry.py -v
```

Expected: `test_lag_opportunity_emits_signal` passes (if route still trades bare OPPORTUNITY); `test_overshoot_opportunity_does_not_emit_signal` and `test_legacy_opportunity_label_not_emitted` both fail because the current `_ACTIONABLE` filter lets any break with a non-None `trade_rec` through.

Actually, test_overshoot should already skip because trade_rec is None for overshoots. Run and see which ones fail. The legacy one is the real catch.

- [ ] **Step 3: Update `_ACTIONABLE` filter to require OPPORTUNITY_LAG by name**

In `pipeline/break_signal_generator.py`, find the `_ACTIONABLE` constant (around line 20-40) and the main conversion loop (line 66+). Replace the filtering logic so only `classification == "OPPORTUNITY_LAG"` is actionable. Change:

```python
_ACTIONABLE = {"LONG", "SHORT"}  # existing
```

to:

```python
_ACTIONABLE_DIRECTIONS = {"LONG", "SHORT"}
_ACTIONABLE_CLASSIFICATIONS = {"OPPORTUNITY_LAG"}
# OPPORTUNITY_OVERSHOOT and legacy OPPORTUNITY are informational only — see
# docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md §3.1
# and §4.1. They become actionable only after H-2026-04-23-003 FADE hypothesis passes.
```

And update the filter in the loop (around line 73):

```python
        if trade_rec not in _ACTIONABLE_DIRECTIONS:
            continue
        if classification not in _ACTIONABLE_CLASSIFICATIONS:
            continue  # informational — skip (OVERSHOOT alert-only, WARNING defensive)
```

Also add geometry passthrough in the metadata block (around line 108):

```python
            "_break_metadata": {
                "symbol": symbol,
                "classification": classification,
                "event_geometry": brk.get("event_geometry"),
                "direction_intended": brk.get("direction_intended"),
                "direction_tested": brk.get("direction_tested"),
                "direction_consistent": brk.get("direction_consistent"),
                "z_score": z_score,
                "regime": regime,
                "oi_anomaly": oi_anomaly,
            },
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
PYTHONPATH=. pytest pipeline/tests/test_break_signal_generator_geometry.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full break_signal_generator tests**

```bash
PYTHONPATH=. pytest pipeline/tests/test_break_signal_generator.py -v
```

Expected: all pre-existing tests still pass. If any fail, fix them — the most likely issue is pre-existing tests built fake breaks with bare `OPPORTUNITY`; update those fixtures to `OPPORTUNITY_LAG`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/break_signal_generator.py pipeline/tests/test_break_signal_generator_geometry.py
git commit -m "feat(phase-c): route only OPPORTUNITY_LAG to actionable signals"
```

---

### Task 7: Update `phase_c_shadow.py` ledger filter

**Files:**
- Modify: `pipeline/phase_c_shadow.py`

**Rationale:** Shadow ledger opens paper positions on scan. It must not open rows for `OPPORTUNITY_OVERSHOOT` (and obviously not for legacy bare `OPPORTUNITY` which should no longer be emitted — defensive filter). If the ledger already filters on `trade_rec`, this is a no-op; but an explicit classification filter documents the invariant.

- [ ] **Step 1: Read the shadow module to find the row-open site**

```bash
grep -n "OPPORTUNITY" pipeline/phase_c_shadow.py
grep -n "open_row\|OPEN\|scan_date" pipeline/phase_c_shadow.py | head -20
```

Locate the function that enumerates breaks and opens ledger rows. Let's call it `open_shadow_rows_for_today` or similar.

- [ ] **Step 2: Add a classification filter at the row-open site**

Insert a guard:

```python
_ACTIONABLE_CLASSIFICATIONS = {"OPPORTUNITY_LAG"}
# OPPORTUNITY_OVERSHOOT is alert-only — no shadow row opened. See
# docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md §3.1.

for brk in breaks:
    if brk.get("classification") not in _ACTIONABLE_CLASSIFICATIONS:
        continue
    # existing row-open logic
```

- [ ] **Step 3: Run the shadow test suite**

```bash
PYTHONPATH=. pytest pipeline/tests/test_phase_c_shadow.py -v
```

Expected: all existing tests pass. If a fixture uses `OPPORTUNITY`, update it to `OPPORTUNITY_LAG`.

- [ ] **Step 4: Commit**

```bash
git add pipeline/phase_c_shadow.py pipeline/tests/test_phase_c_shadow.py
git commit -m "feat(phase-c): shadow ledger skips OPPORTUNITY_OVERSHOOT"
```

---

### Task 8: Update Telegram + terminal UI copy for the label split

**Files:**
- Modify: `pipeline/telegram_bot.py`
- Modify: `pipeline/terminal/static/js/components/positions-table.js`
- Modify: `pipeline/terminal/static/js/pages/research.js`

**Rationale:** UI surfaces must distinguish `OPPORTUNITY_LAG` (tracked paper position) from `OPPORTUNITY_OVERSHOOT` (research alert, no paper position).

- [ ] **Step 1: Telegram icon and label map**

In `pipeline/telegram_bot.py`, find the icon map (around line 989-1007, from prior relabel work). Update to distinguish LAG vs OVERSHOOT:

```python
_PHASE_C_ICON_MAP = {
    "OPPORTUNITY_LAG": "🔬",      # research-tier, actionable at 0.5 unit
    "OPPORTUNITY_OVERSHOOT": "📊",  # alert-only, no paper trade
    "OPPORTUNITY": "🔬",          # legacy — treat as LAG for backwards read
    "POSSIBLE_OPPORTUNITY": "🧪",
    "WARNING": "⚠️",
    "CONFIRMED_WARNING": "🚨",
    "UNCERTAIN": "❓",
}

_PHASE_C_LABEL_COPY = {
    "OPPORTUNITY_LAG": "CORRELATION LAG — EXPLORATORY",
    "OPPORTUNITY_OVERSHOOT": "OVERSHOOT ALERT — RESEARCH-ONLY (no trade)",
    "OPPORTUNITY": "CORRELATION BREAK — EXPLORATORY",  # legacy
}
```

Wherever the header is built, use `_PHASE_C_LABEL_COPY.get(classification, "CORRELATION BREAK — EXPLORATORY")`.

- [ ] **Step 2: positions-table.js — break-detail sub-row**

Find the `SOURCE_DEFS["CORRELATION_BREAK"]` block and the break-detail sub-row renderer. Add geometry-aware copy:

```javascript
const GEOMETRY_LABELS = {
  LAG: "Peers moved; stock lagged. FOLLOW thesis (aligned with backtest FADE).",
  OVERSHOOT: "Peers moved; stock overshot. Live engine thesis is opposite to backtest FADE — research-only, no paper trade opened.",
  DEGENERATE: "Both expected and residual magnitudes < 0.1% — classification ambiguous.",
};

// inside the break-detail sub-row renderer:
const geom = row._break_metadata?.event_geometry;
if (geom) {
  subRow.appendChild(renderGeometryRow(geom, GEOMETRY_LABELS[geom] || ""));
}
```

Also ensure the classification badge shows `OPPORTUNITY_LAG` or `OPPORTUNITY_OVERSHOOT` rather than bare `OPPORTUNITY`.

- [ ] **Step 3: research.js — correlation-break card**

In `pipeline/terminal/static/js/pages/research.js`, find `_breaksCard` (around line 97). The `classification` rendering (line 114) currently special-cases `CONFIRMED_WARNING`; extend it to render OVERSHOOT differently from LAG:

```javascript
    const cls = classification === 'CONFIRMED_WARNING' ? 'text-red'
      : classification === 'OPPORTUNITY_OVERSHOOT' ? 'text-muted'
      : 'text-secondary';
    // ...
    const badgeCls = classification === 'CONFIRMED_WARNING' ? 'badge--red'
      : classification === 'OPPORTUNITY_OVERSHOOT' ? 'badge--muted'
      : classification.startsWith('OPPORTUNITY') ? 'badge--gold'
      : 'badge--muted';
    const title = classification === 'OPPORTUNITY_OVERSHOOT'
      ? 'Research alert — live engine is opposite to backtest FADE. No shadow row opened. H-2026-04-23-003 will test if FADE is tradeable.'
      : classification.startsWith('OPPORTUNITY')
      ? 'LAG-geometry: live engine FOLLOW agrees with backtest FADE. Shadow row opened at 0.5 unit per H-2026-04-23-002.'
      : 'Phase C defensive signal.';
```

- [ ] **Step 4: Smoke-test the terminal locally**

```bash
PYTHONPATH=. python -m pipeline.terminal.server &
# Open http://127.0.0.1:8765/research in a browser
# Verify Correlation Breaks card renders; no JS console errors
# Kill the server
```

Note: this is a manual visual smoke test. If the UI can't be tested (e.g., this is running in a headless context), state that explicitly in the commit body.

- [ ] **Step 5: Commit**

```bash
git add pipeline/telegram_bot.py pipeline/terminal/static/js/components/positions-table.js pipeline/terminal/static/js/pages/research.js
git commit -m "feat(phase-c): UI copy distinguishes OPPORTUNITY_LAG from OPPORTUNITY_OVERSHOOT"
```

---

### Task 9: Create `runner_phase_c_slice.py` — slice-restricted compliance runner

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/runner_phase_c_slice.py`
- Create: `pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py`

**Rationale:** Wraps `runner.run_compliance` with a pre-filter step that restricts the event set to a single geometry slice ({"LAG", "OVERSHOOT"}). Writes outputs under a sibling directory so the parent H-2026-04-23-001 artifact stays untouched.

- [ ] **Step 1: Write failing test for the slice filter**

Create `pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py`:

```python
"""Tests for the slice-restricted Phase C compliance wrapper."""
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice import (
    filter_events_by_geometry,
    SliceSpec,
)


class TestFilterEventsByGeometry:
    def _events_df(self):
        return pd.DataFrame([
            {"ticker": "A", "direction": "UP", "expected_return_pct": 2.0, "actual_return_pct": 0.5},   # LAG
            {"ticker": "A", "direction": "UP", "expected_return_pct": 2.0, "actual_return_pct": 3.0},   # OVERSHOOT
            {"ticker": "B", "direction": "DOWN", "expected_return_pct": -2.0, "actual_return_pct": -0.5},  # LAG
            {"ticker": "B", "direction": "DOWN", "expected_return_pct": -2.0, "actual_return_pct": -3.0},  # OVERSHOOT
            {"ticker": "C", "direction": "UP", "expected_return_pct": 0.05, "actual_return_pct": 3.0},  # DEGENERATE
        ])

    def test_lag_slice_keeps_lag_events_only(self):
        events = self._events_df()
        filtered = filter_events_by_geometry(events, "LAG")
        assert len(filtered) == 2
        assert set(filtered["ticker"]) == {"A", "B"}

    def test_overshoot_slice_keeps_overshoot_events_only(self):
        events = self._events_df()
        filtered = filter_events_by_geometry(events, "OVERSHOOT")
        assert len(filtered) == 2
        assert set(filtered["ticker"]) == {"A", "B"}

    def test_degenerate_excluded_from_both_slices(self):
        events = self._events_df()
        lag = filter_events_by_geometry(events, "LAG")
        overshoot = filter_events_by_geometry(events, "OVERSHOOT")
        total = len(lag) + len(overshoot)
        assert total == 4  # 1 DEGENERATE is dropped

    def test_invalid_slice_raises(self):
        with pytest.raises(ValueError):
            filter_events_by_geometry(self._events_df(), "BOGUS")


class TestSliceSpec:
    def test_output_path_lag(self):
        spec = SliceSpec(slice_name="LAG", hypothesis_id="H-2026-04-23-002")
        path = spec.output_path("2026-04-23T12:00:00")
        assert "compliance_phase_c_lag" in str(path).lower()
        assert "H-2026-04-23-002" in str(path)

    def test_output_path_overshoot(self):
        spec = SliceSpec(slice_name="OVERSHOOT", hypothesis_id="H-2026-04-23-003")
        path = spec.output_path("2026-04-23T12:00:00")
        assert "compliance_phase_c_overshoot" in str(path).lower()
        assert "H-2026-04-23-003" in str(path)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the slice runner**

Create `pipeline/autoresearch/overshoot_compliance/runner_phase_c_slice.py`:

```python
"""Slice-restricted Phase C compliance runner (spec §4.3).

Wraps overshoot_compliance.runner.run_compliance with a geometric filter so
the existing 100k-permutation engine can be applied to LAG events only or
OVERSHOOT events only. Used by H-2026-04-23-002 (LAG family) and
H-2026-04-23-003 (OVERSHOOT family).

The slice runner does NOT introduce a new permutation loop. It loads the
parent H-2026-04-23-001 event inventory, filters by event_geometry, and
delegates to the existing runner with the restricted event set.
"""
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from pathlib import Path

from pipeline.autoresearch.reverse_regime_breaks import classify_event_geometry


def filter_events_by_geometry(events: pd.DataFrame, slice_name: str) -> pd.DataFrame:
    """Return only rows matching the requested geometric slice.

    Expects columns `expected_return_pct` and `actual_return_pct` (percent).
    Raises ValueError for unknown slice names.
    """
    if slice_name not in {"LAG", "OVERSHOOT"}:
        raise ValueError(f"slice_name must be LAG or OVERSHOOT, got {slice_name!r}")

    def _geom(row):
        return classify_event_geometry(row["expected_return_pct"], row["actual_return_pct"])

    events = events.copy()
    events["_geometry"] = events.apply(_geom, axis=1)
    filtered = events[events["_geometry"] == slice_name].drop(columns=["_geometry"]).reset_index(drop=True)
    return filtered


@dataclass
class SliceSpec:
    slice_name: str               # "LAG" or "OVERSHOOT"
    hypothesis_id: str            # "H-2026-04-23-002" or "-003"
    results_root: Path = Path("pipeline/autoresearch/results")

    def output_path(self, run_timestamp: str) -> Path:
        """Build the output directory for this slice's compliance run."""
        safe_ts = run_timestamp.replace(":", "").replace("-", "")[:15]
        slice_tag = self.slice_name.lower()
        return (
            self.results_root
            / f"compliance_phase_c_{slice_tag}_{self.hypothesis_id}_{safe_ts}"
        )


def run_slice_compliance(
    parent_events_path: Path,
    slice_spec: SliceSpec,
    run_timestamp: str,
    n_permutations: int = 100_000,
    min_events_per_cell: int = 10,
) -> dict:
    """Run the existing compliance engine restricted to one geometric slice.

    Returns the manifest dict. Writes artifacts to `slice_spec.output_path(...)`.
    """
    # Local import so tests can patch the downstream runner easily
    from pipeline.autoresearch.overshoot_compliance.runner import run_compliance

    events = pd.read_json(parent_events_path, orient="records")
    filtered = filter_events_by_geometry(events, slice_spec.slice_name)

    # Drop cells below the n-per-cell minimum (§9.1 + spec §4.3 step 2)
    cell_counts = filtered.groupby(["ticker", "direction"]).size()
    eligible_cells = cell_counts[cell_counts >= min_events_per_cell].index
    filtered = filtered.set_index(["ticker", "direction"]).loc[list(eligible_cells)].reset_index()

    output_dir = slice_spec.output_path(run_timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = run_compliance(
        events=filtered,
        output_dir=output_dir,
        hypothesis_id=slice_spec.hypothesis_id,
        n_permutations=n_permutations,
        family_size=len(eligible_cells),
        run_timestamp=run_timestamp,
    )
    return manifest
```

Note: the signature of `run_compliance` in the implementation above may not match the existing one. Before implementing, read `pipeline/autoresearch/overshoot_compliance/runner.py::run_compliance` (or equivalent entry point) to confirm the real signature, and pass the right kwargs. If the runner reads events from disk rather than accepting a DataFrame, adapt — maybe write `filtered` to a temp events.json and point the runner at it.

- [ ] **Step 4: Run tests — should pass**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add -f pipeline/autoresearch/overshoot_compliance/runner_phase_c_slice.py
git add pipeline/tests/autoresearch/overshoot_compliance/test_runner_phase_c_slice.py
git commit -m "feat(compliance): slice-restricted runner for Phase C LAG/OVERSHOOT audit"
```

(Note: `pipeline/autoresearch/` is in `.gitignore` — force-add is required per project convention.)

---

### Task 10: Smoke-run the slice runner on a single ticker

**Files:**
- No code changes; adds an artifact.

**Rationale:** Prove the wire-up works end-to-end before the full overnight run. Use a small n_permutations (1,000) and restrict to a single well-known ticker.

- [ ] **Step 1: Run a smoke compliance on TORNTPOWER UP (LAG slice, n_perm=1,000)**

```bash
PYTHONPATH=. python -m pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice \
  --parent-events pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json \
  --slice LAG \
  --hypothesis-id H-2026-04-23-002 \
  --n-permutations 1000 \
  --ticker-filter TORNTPOWER \
  --run-timestamp 20260423-smoke
```

(If `runner_phase_c_slice.py` doesn't yet expose a CLI, add a minimal `argparse`-based `main()` in this step. Keep the CLI surface thin — just pass-through args.)

- [ ] **Step 2: Verify the output artifact shape**

```bash
ls pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423smoke/
cat pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423smoke/manifest.json | python -m json.tool | head -40
```

Expected: the standard compliance artifacts (manifest.json, metrics.json, gate_checklist.json, etc.) exist and the manifest names the slice + hypothesis id.

- [ ] **Step 3: Commit the smoke artifact**

```bash
git add -f pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_20260423smoke/
git commit -m "smoke: Phase C LAG slice runner on TORNTPOWER (n_perm=1000)"
```

---

### Task 11: Full compliance run — H-2026-04-23-002 LAG family

**Files:**
- No code changes; adds the canonical artifact.

- [ ] **Step 1: Run the full LAG-slice compliance**

```bash
PYTHONPATH=. python -m pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice \
  --parent-events pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json \
  --slice LAG \
  --hypothesis-id H-2026-04-23-002 \
  --n-permutations 100000 \
  --run-timestamp $(date +%Y%m%d-%H%M%S)
```

Expected runtime: 30-90 minutes depending on post-filter cell count.

- [ ] **Step 2: Verify `gate_checklist.json` decision**

```bash
cat pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_*/gate_checklist.json | python -m json.tool
```

Record the decision (PASS/FAIL), family size, Bonferroni α, number of Bonferroni survivors, number of BH-FDR survivors.

- [ ] **Step 3: Commit the artifact**

```bash
git add -f pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_*/
git commit -m "run: H-2026-04-23-002 LAG compliance artifact (decision = <PASS|FAIL>)"
```

- [ ] **Step 4: Update registry terminal_state**

Open `docs/superpowers/hypothesis-registry.jsonl`, find the H-2026-04-23-002 line, set `"terminal_state": "<PASS|FAIL>_YYYY-MM-DD"` based on the gate decision.

```bash
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: H-2026-04-23-002 terminal_state from compliance run"
```

---

### Task 12: Full compliance run — H-2026-04-23-003 OVERSHOOT family

**Files:**
- No code changes; adds the canonical artifact.

- [ ] **Step 1: Run the full OVERSHOOT-slice compliance**

```bash
PYTHONPATH=. python -m pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice \
  --parent-events pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/events.json \
  --slice OVERSHOOT \
  --hypothesis-id H-2026-04-23-003 \
  --n-permutations 100000 \
  --run-timestamp $(date +%Y%m%d-%H%M%S)
```

- [ ] **Step 2-4: Same verify/commit/registry-update pattern as Task 11.**

```bash
cat pipeline/autoresearch/results/compliance_phase_c_overshoot_H-2026-04-23-003_*/gate_checklist.json | python -m json.tool
git add -f pipeline/autoresearch/results/compliance_phase_c_overshoot_H-2026-04-23-003_*/
git commit -m "run: H-2026-04-23-003 OVERSHOOT compliance artifact (decision = <PASS|FAIL>)"
# edit registry terminal_state
git add docs/superpowers/hypothesis-registry.jsonl
git commit -m "register: H-2026-04-23-003 terminal_state from compliance run"
```

---

### Task 13: DIRECTION-SUSPECT classifier

**Files:**
- Create: `pipeline/autoresearch/overshoot_compliance/direction_suspect.py`
- Create: `pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py`

**Rationale:** §5 of the spec. Reads the two slice artifacts from Tasks 11-12 and emits per-(ticker, direction) verdicts: `DIRECTION-SUSPECT`, `PARAMETER-FRAGILE-DIRECTION`, or `CLEAN`. This artifact is the input to the §7 promotion gate.

- [ ] **Step 1: Write failing tests**

Create `pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py`:

```python
"""Tests for the §5 DIRECTION-SUSPECT classifier."""
from pipeline.autoresearch.overshoot_compliance.direction_suspect import (
    classify_direction_verdict,
    CellResult,
)


class TestClassifyDirectionVerdict:
    def test_clean_when_lag_clears_bonferroni(self):
        # Live engine trades LAG (FOLLOW); LAG slice clears Bonferroni → the
        # live thesis has statistical support on the slice it actually runs on.
        lag = CellResult(ticker="RELIANCE", direction="UP", slice_name="LAG",
                          n_events=30, bonferroni_pass=True, edge_net_pct=0.6, p_value=1e-5)
        overshoot = CellResult(ticker="RELIANCE", direction="UP", slice_name="OVERSHOOT",
                                n_events=15, bonferroni_pass=False, edge_net_pct=-0.2, p_value=0.5)
        assert classify_direction_verdict(lag, overshoot) == "CLEAN"

    def test_direction_suspect_when_overshoot_clears_but_lag_does_not(self):
        # Live engine trades OVERSHOOT as FOLLOW but backtest FADE clears → live is wrong-sided
        lag = CellResult(ticker="TORNTPOWER", direction="UP", slice_name="LAG",
                          n_events=20, bonferroni_pass=False, edge_net_pct=0.1, p_value=0.4)
        overshoot = CellResult(ticker="TORNTPOWER", direction="UP", slice_name="OVERSHOOT",
                                n_events=12, bonferroni_pass=True, edge_net_pct=1.4, p_value=1e-5)
        assert classify_direction_verdict(lag, overshoot) == "DIRECTION_SUSPECT"

    def test_parameter_fragile_when_both_pass(self):
        # Both slices have edge in their tested direction — the original full-panel
        # significance was genuine but the direction-audit reveals both geometries
        # carry edge; this is a fragility flag, not a blocker.
        lag = CellResult(ticker="SBIN", direction="UP", slice_name="LAG",
                          n_events=25, bonferroni_pass=True, edge_net_pct=0.7, p_value=1e-5)
        overshoot = CellResult(ticker="SBIN", direction="UP", slice_name="OVERSHOOT",
                                n_events=20, bonferroni_pass=True, edge_net_pct=1.2, p_value=1e-6)
        assert classify_direction_verdict(lag, overshoot) == "PARAMETER_FRAGILE_DIRECTION"

    def test_insufficient_power_when_either_slice_too_few_events(self):
        lag = CellResult(ticker="RARE", direction="UP", slice_name="LAG",
                          n_events=5, bonferroni_pass=False, edge_net_pct=None, p_value=None)
        overshoot = CellResult(ticker="RARE", direction="UP", slice_name="OVERSHOOT",
                                n_events=8, bonferroni_pass=False, edge_net_pct=None, p_value=None)
        assert classify_direction_verdict(lag, overshoot) == "INSUFFICIENT_POWER"

    def test_clean_when_neither_slice_passes(self):
        # Nothing significant on either slice — the original full-panel significance
        # (if any) was a mixture artifact. Not DIRECTION_SUSPECT because the
        # opposite-direction edge doesn't clear the bar either.
        lag = CellResult(ticker="NOISE", direction="UP", slice_name="LAG",
                          n_events=20, bonferroni_pass=False, edge_net_pct=0.1, p_value=0.3)
        overshoot = CellResult(ticker="NOISE", direction="UP", slice_name="OVERSHOOT",
                                n_events=15, bonferroni_pass=False, edge_net_pct=-0.05, p_value=0.6)
        assert classify_direction_verdict(lag, overshoot) == "CLEAN"
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py -v
```

- [ ] **Step 3: Implement the classifier**

Create `pipeline/autoresearch/overshoot_compliance/direction_suspect.py`:

```python
"""DIRECTION-SUSPECT classifier (spec §5).

Reads the LAG and OVERSHOOT slice compliance artifacts (H-2026-04-23-002 and
H-2026-04-23-003) and emits a per-(ticker, direction) verdict used by the §7
promotion gate.

Verdicts:
  CLEAN                       — LAG slice clears Bonferroni; live FOLLOW is
                                statistically supported. OVERSHOOT does not
                                need to pass anything.
  DIRECTION_SUSPECT           — OVERSHOOT FADE clears Bonferroni but LAG
                                FOLLOW does not. The live engine is trading
                                the wrong side on overshoot events and has no
                                demonstrated edge on lag events either.
  PARAMETER_FRAGILE_DIRECTION — Both slices clear Bonferroni. Edge exists
                                under multiple direction theses; the original
                                full-panel significance was real but the
                                mechanism is not crisp. Flag for follow-up,
                                not a blocker.
  INSUFFICIENT_POWER          — Either slice had n_events < 10. Not enough
                                data to rule on direction.

Usage:
    from pipeline.autoresearch.overshoot_compliance.direction_suspect import (
        classify_all_cells,
    )
    verdicts = classify_all_cells(
        lag_artifact_path=Path("...compliance_phase_c_lag.../metrics_per_cell.json"),
        overshoot_artifact_path=Path("...compliance_phase_c_overshoot.../metrics_per_cell.json"),
        output_path=Path("direction_suspect_verdicts.json"),
    )
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class CellResult:
    ticker: str
    direction: str           # "UP" or "DOWN"
    slice_name: str          # "LAG" or "OVERSHOOT"
    n_events: int
    bonferroni_pass: bool    # True if p_value <= Bonferroni alpha AND edge_net_pct > 0
    edge_net_pct: float | None
    p_value: float | None


def classify_direction_verdict(lag: CellResult, overshoot: CellResult) -> str:
    """Emit a per-cell verdict from paired LAG and OVERSHOOT results."""
    if lag.ticker != overshoot.ticker or lag.direction != overshoot.direction:
        raise ValueError(
            f"Paired results must share (ticker, direction); got "
            f"{(lag.ticker, lag.direction)} vs {(overshoot.ticker, overshoot.direction)}"
        )

    if lag.n_events < 10 or overshoot.n_events < 10:
        return "INSUFFICIENT_POWER"

    if lag.bonferroni_pass and overshoot.bonferroni_pass:
        return "PARAMETER_FRAGILE_DIRECTION"
    if overshoot.bonferroni_pass and not lag.bonferroni_pass:
        return "DIRECTION_SUSPECT"
    # Either LAG passed alone → CLEAN, or neither passed → CLEAN (no alpha either way)
    return "CLEAN"


def classify_all_cells(
    lag_artifact_path: Path,
    overshoot_artifact_path: Path,
    output_path: Path,
) -> dict:
    """Walk both artifacts and produce a combined verdict table."""
    lag_cells = _load_cells(lag_artifact_path, slice_name="LAG")
    overshoot_cells = _load_cells(overshoot_artifact_path, slice_name="OVERSHOOT")

    lag_by_key = {(c.ticker, c.direction): c for c in lag_cells}
    overshoot_by_key = {(c.ticker, c.direction): c for c in overshoot_cells}

    all_keys = sorted(set(lag_by_key.keys()) | set(overshoot_by_key.keys()))
    verdicts = []
    for key in all_keys:
        lag = lag_by_key.get(key) or _empty_cell(key, "LAG")
        overshoot = overshoot_by_key.get(key) or _empty_cell(key, "OVERSHOOT")
        verdict = classify_direction_verdict(lag, overshoot)
        verdicts.append({
            "ticker": key[0],
            "direction": key[1],
            "verdict": verdict,
            "lag": _as_dict(lag),
            "overshoot": _as_dict(overshoot),
        })

    output = {"verdicts": verdicts, "summary": _summarize(verdicts)}
    output_path.write_text(json.dumps(output, indent=2))
    return output


def _empty_cell(key: tuple[str, str], slice_name: str) -> CellResult:
    return CellResult(ticker=key[0], direction=key[1], slice_name=slice_name,
                       n_events=0, bonferroni_pass=False, edge_net_pct=None, p_value=None)


def _load_cells(path: Path, slice_name: str) -> Iterable[CellResult]:
    blob = json.loads(Path(path).read_text())
    cells = []
    for row in blob.get("cells", []):
        cells.append(CellResult(
            ticker=row["ticker"],
            direction=row["direction"],
            slice_name=slice_name,
            n_events=row.get("n_events", 0),
            bonferroni_pass=bool(row.get("bonferroni_pass", False)),
            edge_net_pct=row.get("edge_net_pct"),
            p_value=row.get("p_value"),
        ))
    return cells


def _as_dict(c: CellResult) -> dict:
    return {
        "n_events": c.n_events,
        "bonferroni_pass": c.bonferroni_pass,
        "edge_net_pct": c.edge_net_pct,
        "p_value": c.p_value,
    }


def _summarize(verdicts: list[dict]) -> dict:
    counts = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    return {"verdict_counts": counts, "n_cells": len(verdicts)}
```

Note: the exact key names in the compliance artifact JSON (`cells`, `bonferroni_pass`, etc.) depend on the existing runner's output schema. Before implementing, read one row of `pipeline/autoresearch/results/compliance_H-2026-04-23-001_20260423-150125/metrics_per_cell.json` (or equivalent) to confirm and adapt `_load_cells` to match the real schema.

- [ ] **Step 4: Run tests — should pass**

```bash
PYTHONPATH=. pytest pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the classifier on the real artifacts from Tasks 11-12**

```bash
PYTHONPATH=. python -m pipeline.autoresearch.overshoot_compliance.direction_suspect \
  --lag-artifact pipeline/autoresearch/results/compliance_phase_c_lag_H-2026-04-23-002_*/metrics_per_cell.json \
  --overshoot-artifact pipeline/autoresearch/results/compliance_phase_c_overshoot_H-2026-04-23-003_*/metrics_per_cell.json \
  --output pipeline/autoresearch/results/direction_suspect_verdicts_20260423.json
```

(Add an `argparse`-based `main()` if the module doesn't already have one — same pattern as Task 10.)

- [ ] **Step 6: Verify the verdict summary**

```bash
cat pipeline/autoresearch/results/direction_suspect_verdicts_20260423.json | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['summary'], indent=2))"
```

Record the verdict distribution (count of CLEAN, DIRECTION_SUSPECT, PARAMETER_FRAGILE_DIRECTION, INSUFFICIENT_POWER).

- [ ] **Step 7: Commit**

```bash
git add -f pipeline/autoresearch/overshoot_compliance/direction_suspect.py pipeline/autoresearch/results/direction_suspect_verdicts_20260423.json
git add pipeline/tests/autoresearch/overshoot_compliance/test_direction_suspect.py
git commit -m "feat(compliance): DIRECTION-SUSPECT classifier + verdict artifact"
```

---

### Task 14: End-to-end smoke test — new Phase C scan respects the split

**Files:**
- No code changes; runs the real intraday scan in dry-run mode.

**Rationale:** Verify that a live Phase C scan on today's data produces `OPPORTUNITY_LAG` / `OPPORTUNITY_OVERSHOOT` labels with populated geometry fields, and that the signal generator does not emit any overshoot signals.

- [ ] **Step 1: Run the scanner in dry-run mode**

```bash
PYTHONPATH=. python pipeline/autoresearch/reverse_regime_breaks.py --dry-run
```

(If `--dry-run` doesn't exist, inspect the `main()` function and add a flag that skips `save_breaks`. Keep it small.)

- [ ] **Step 2: Inspect a sample output record**

The scan should print or log a sample break dict. Verify it contains:
- `event_geometry` ∈ {"LAG", "OVERSHOOT", "DEGENERATE"}
- `direction_intended` ∈ {"FOLLOW", "NEUTRAL"}
- `direction_tested` == "FADE"
- `direction_consistent` ∈ {true, false, null}
- `classification` starts with `OPPORTUNITY_LAG`, `OPPORTUNITY_OVERSHOOT`, or a non-opportunity label

- [ ] **Step 3: Run the signal generator and confirm no overshoots emit**

```bash
PYTHONPATH=. python -c "
import json
from pipeline.break_signal_generator import generate_signals_from_breaks
breaks = json.load(open('pipeline/data/correlation_breaks.json'))
signals = generate_signals_from_breaks(breaks.get('breaks', []), scan_date='2026-04-23', scan_time='2026-04-23T14:00:00+05:30')
classifs = {s['_break_metadata']['classification'] for s in signals}
print('Signal classifications:', classifs)
assert 'OPPORTUNITY_OVERSHOOT' not in classifs, 'BUG: overshoot signals leaked through'
print('OK — no overshoot signals in generator output')
"
```

Expected: prints `OK`. If it asserts, the routing guard in Task 6 has a bug — go back and fix.

- [ ] **Step 4: No commit needed if everything passes.** If you had to add `--dry-run` in Step 1, commit that:

```bash
git add pipeline/autoresearch/reverse_regime_breaks.py
git commit -m "test(phase-c): add --dry-run flag for scan smoke testing"
```

---

### Task 15: Documentation note — `docs/superpowers/phase_c_direction.md`

**Files:**
- Create: `docs/superpowers/phase_c_direction.md`

**Rationale:** Spec §7.4 requires a short doc explaining what's tested vs traded, and how mismatches are flagged.

- [ ] **Step 1: Write the doc**

Create `docs/superpowers/phase_c_direction.md`:

```markdown
# Phase C Direction — What's Tested vs What's Traded

**Scope:** Correlation-breaks strategy only. Phase A (ranker) and Phase B (spread
composer) use different direction logic and are not governed by this note.

## The two directions

| | Defined as | Set by |
|---|---|---|
| **Backtest direction (FADE)** | `-sign(residual)` where `residual = actual_return - expected_return` | `pipeline/autoresearch/overshoot_reversion_backtest.py` |
| **Live engine direction (FOLLOW)** | `sign(expected_return)` — LONG if peers predict up, SHORT if peers predict down | `pipeline/break_signal_generator.py` |

The two directions agree on **LAG** geometry (peers moved, stock lagged same-direction or went opposite) and disagree on **OVERSHOOT** geometry (peers moved, stock moved further on the same side).

## How mismatch is flagged

Every Phase C event carries four new fields (spec §3):

- `event_geometry`: `LAG` | `OVERSHOOT` | `DEGENERATE`
- `direction_intended`: the thesis the live engine is *running* (`FOLLOW` for LAG, `NEUTRAL` for OVERSHOOT)
- `direction_tested`: what the backtest *validated* (always `FADE` for correlation-breaks v1)
- `direction_consistent`: `true` iff `event_geometry == LAG` (FADE and FOLLOW agree on that slice)

## How trades are gated

`pipeline/break_signal_generator.py` routes only `classification == "OPPORTUNITY_LAG"` to actionable signals. `OPPORTUNITY_OVERSHOOT` becomes a research-only alert and does not reach the shadow ledger.

This is a hard routing rule — not a config flag — until `H-2026-04-23-003` (OVERSHOOT FADE hypothesis) passes compliance. See `docs/superpowers/hypothesis-registry.jsonl`.

## Where verdicts live

The `pipeline/autoresearch/overshoot_compliance/direction_suspect.py` module compares the LAG compliance run (H-2026-04-23-002) against the OVERSHOOT compliance run (H-2026-04-23-003) and writes per-cell verdicts to `pipeline/autoresearch/results/direction_suspect_verdicts_<date>.json`. Verdicts:

- `CLEAN` — LAG cleared Bonferroni; live FOLLOW is supported.
- `DIRECTION_SUSPECT` — OVERSHOOT FADE cleared but LAG FOLLOW did not; live engine is trading the wrong side.
- `PARAMETER_FRAGILE_DIRECTION` — Both slices cleared; edge exists under multiple theses.
- `INSUFFICIENT_POWER` — Not enough events in at least one slice.

## Promotion gate (spec §7)

Phase C stays `TIER_EXPLORING` until:

1. Every deployable cell is `CLEAN` (or carries an explicit waiver).
2. No `DIRECTION_SUSPECT` cell touches the deployable path.
3. Any "Phase C deployable" claim uses a Bonferroni-corrected bar — FDR-only survivors stay research-tier.

See `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` for the full gate ladder.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/phase_c_direction.md
git commit -m "docs(phase-c): direction audit — tested vs traded + mismatch gate"
```

---

### Task 16: Docs + memory sync

**Files:**
- Modify: `docs/SYSTEM_OPERATIONS_MANUAL.md`
- Modify: `memory/project_overshoot_reversion_backtest.md`
- Modify: `memory/project_phase_c_follow_vs_fade_audit.md`
- Modify: `.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md`

**Rationale:** CLAUDE.md doc-sync mandate — every code change updates all docs in the same commit. This is the final commit closing out #107.

- [ ] **Step 1: Update SYSTEM_OPERATIONS_MANUAL.md Phase C section**

Find the Phase C section and replace the classification vocabulary. Add:

```markdown
### Phase C labels (post-2026-04-23 direction audit)

- **OPPORTUNITY_LAG** — tested (FADE) and live (FOLLOW) directions agree on this
  slice by construction. Shadow ledger opens a 0.5-unit paper row. Governed by
  `H-2026-04-23-002`. Promotion to `TIER_SIGNAL` gated on compliance + §7.
- **OPPORTUNITY_OVERSHOOT** — tested (FADE) and live (FOLLOW) are opposite.
  Alert-only. No shadow row. Governed by `H-2026-04-23-003`. Live engine does
  not trade these until FADE hypothesis clears Bonferroni.
- **POSSIBLE_OPPORTUNITY / WARNING / CONFIRMED_WARNING / UNCERTAIN** —
  unchanged.

See `docs/superpowers/phase_c_direction.md` for the audit mechanics and
`docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` for
the full spec.
```

- [ ] **Step 2: Update `memory/project_overshoot_reversion_backtest.md`**

Add a trailing section:

```markdown

## 2026-04-23 direction audit (task #107) — outcome

Split into per-geometry sub-registrations:
- `H-2026-04-23-002` (LAG slice, FOLLOW thesis) — <PASS|FAIL>, <n> Bonferroni survivors
- `H-2026-04-23-003` (OVERSHOOT slice, FADE thesis) — <PASS|FAIL>, <n> Bonferroni survivors
- `direction_suspect_verdicts_20260423.json` — <count> CLEAN / <count> DIRECTION_SUSPECT / <count> PARAMETER_FRAGILE_DIRECTION / <count> INSUFFICIENT_POWER

Live engine now routes only `OPPORTUNITY_LAG` to signal emission; `OPPORTUNITY_OVERSHOOT` is alert-only.
```

Fill in the `<...>` placeholders with the actual numbers from Tasks 11-13.

- [ ] **Step 3: Supersede the pre-spec memory**

Replace the entire content of `memory/project_phase_c_follow_vs_fade_audit.md` with a brief pointer:

```markdown
---
name: Phase C FOLLOW vs FADE audit (task #107) — SUPERSEDED
description: Pre-spec sketch superseded by docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md (committed 3bc574d) and implementation plan docs/superpowers/plans/2026-04-23-phase-c-follow-vs-fade-audit.md. See those documents for the canonical design and plan.
type: project
---

This memory was the pre-spec sketch for task #107. It is superseded by the formal design doc and implementation plan. The design doc contains everything this sketch had plus the gap-fills from the 2026-04-23 markup pass (event_geometry field, classify_break code fix, sub-bucket null-test procedure, scope limit, pre-registration step).

Canonical references:
- Design: `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md`
- Plan: `docs/superpowers/plans/2026-04-23-phase-c-follow-vs-fade-audit.md`
- Direction doc note: `docs/superpowers/phase_c_direction.md`
- Verdict artifact: `pipeline/autoresearch/results/direction_suspect_verdicts_20260423.json`
```

- [ ] **Step 4: Update MEMORY.md index**

Find the existing MEMORY.md line:

```
- [Overshoot reversion backtest](project_overshoot_reversion_backtest.md) — 5-yr per-ticker fade scan across 211 F&O stocks; TORNTPOWER UP only STRONG live verdict 2026-04-23
```

Add a new line immediately below:

```
- [Phase C direction audit](project_phase_c_follow_vs_fade_audit.md) — #107 complete: OPPORTUNITY split into LAG/OVERSHOOT; live engine routes only LAG; DIRECTION_SUSPECT verdicts at pipeline/autoresearch/results/direction_suspect_verdicts_20260423.json
```

- [ ] **Step 5: Run the full test suite as a final guard**

```bash
PYTHONPATH=. pytest pipeline/tests/ -q 2>&1 | tail -20
```

Expected: no new failures compared to the pre-plan baseline. Note the pass count for the commit message.

- [ ] **Step 6: Final commit**

```bash
git add docs/SYSTEM_OPERATIONS_MANUAL.md memory/project_overshoot_reversion_backtest.md memory/project_phase_c_follow_vs_fade_audit.md
git add "C:/Users/Claude_Anka/.claude/projects/C--Users-Claude-Anka-askanka-com/memory/MEMORY.md"
git commit -m "docs(phase-c): #107 direction audit complete — ops manual + memory sync"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Plan task | Covered? |
|---|---|---|
| §3 data model (event_geometry + 3 direction fields) | Task 3, 5 | ✅ |
| §3.1 classify_break code fix | Task 4 | ✅ |
| §4.1 engine routing | Task 6 | ✅ |
| §4.2 backtest direction_consistent flag | Task 5 (enrich_break) + existing compliance runner | ✅ |
| §4.3 sub-bucket null tests | Task 9, 10, 11, 12 | ✅ |
| §5 DIRECTION-SUSPECT classifier | Task 13 | ✅ |
| §6.0 scope limit | Acknowledged in plan header; guardrails deferred | ✅ |
| §7.1 direction mapping | Task 5 | ✅ |
| §7.2 direction audit gate | Task 13 | ✅ |
| §7.3 multiplicity (Bonferroni) | Tasks 11, 12 (registry declares it; runner applies it) | ✅ |
| §7.4 docs note | Task 15 | ✅ |
| §7.5 pre-registration | Tasks 1, 2 — FIRST, before any slice p-values | ✅ |

**Placeholder scan:** Searched for TBD / TODO / "fill in" / "similar to" — only use is in the registry's `primary_family_size_estimate: "TBD_post_filter"` which is a legitimate marker (family size is an output, not an input). Acceptable.

**Type consistency:** `CellResult` fields match between `direction_suspect.py` and its test. `SliceSpec.slice_name` matches `filter_events_by_geometry`'s parameter name. `event_geometry` values `"LAG" | "OVERSHOOT" | "DEGENERATE"` consistent across classifier, enricher, filter, tests, UI. `OPPORTUNITY_LAG` / `OPPORTUNITY_OVERSHOOT` label strings consistent.

**One tension to flag for the implementer:** Task 9's `run_compliance` call signature is inferred — before implementing, read the real signature in `pipeline/autoresearch/overshoot_compliance/runner.py` and adapt. If the runner reads events from disk, Task 9's implementation writes `filtered` to a temp file first.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-phase-c-follow-vs-fade-audit.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good fit here: most tasks are isolated (pure function + tests), and the two long compliance runs (Tasks 11-12) naturally become one subagent dispatch each.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Viable but the context would grow significantly through 16 tasks.

**Which approach?**
