# Stage 1 Closeout Gate — Design Specification

| Field | Value |
|---|---|
| **Document** | Stage 1 Closeout Gate Design |
| **Status** | SPEC FROZEN (ready for implementation) |
| **Spec version** | 1.0 |
| **Schema version** | 1.0 |
| **Criteria version** | 1.0 |
| **Authored** | 2026-04-10 |
| **Repo** | `opus-anka` |
| **Code root** | `pipeline/stage1_gate/` |
| **Supersedes** | All prior brainstorm section drafts |

## Document status

- Consolidates 7 brainstorm design sections + 3 Section-6 addenda + 24 reconciled cross-section drifts (see Appendix B)
- **This document is canonical.** Any earlier section draft disagrees? This wins.
- Locked design decisions (Appendix A) cannot be changed without amending this document and bumping `criteria_version`.
- Implementation checklist (Appendix C) is the execution plan.

## Table of contents

1. [Architecture & Data Flow](#1-architecture--data-flow)
2. [DoD Criteria (blocking + warning taxonomy)](#2-dod-criteria-blocking--warning-taxonomy)
3. [Golden Set](#3-golden-set)
4. [Programmatic Sanity Rules](#4-programmatic-sanity-rules)
5. [Triage Tree](#5-triage-tree)
6. [Handoff Manifest Schema](#6-handoff-manifest-schema)
7. [Failure Handling & Operator Workflow](#7-failure-handling--operator-workflow)
- [Appendix A — Locked design decisions](#appendix-a--locked-design-decisions)
- [Appendix B — Drift reconciliation log](#appendix-b--drift-reconciliation-log)
- [Appendix C — Implementation checklist](#appendix-c--implementation-checklist)

---

## 1. Architecture & Data Flow

### 1.1 Purpose

The Stage 1 Closeout Gate is a **read-only validation barrier** between Stage 1 (automated scoring of the F&O universe) and Stage 2 (portfolio construction and deep analysis). It answers one question per invocation: *"Is Stage 1 output good enough for Stage 2 to ground on?"*

The gate emits a canonical two-tier **manifest** artifact, a `gate_state` verdict, and an exit code. Downstream tools read the manifest; they never re-derive Stage 1 quality independently.

### 1.2 Entry points

- **`python run_stage1_gate.py`** — CLI wrapper (~50 lines). Reads config, calls the orchestrator, writes the manifest, exits with a code from the 5-value set in §7.1.
- **`python run_stage1_gate.py --dry-run`** — runs all checks, prints a summary, writes to `artifacts/stage1_gate/preview_<timestamp>.json`, does not touch the canonical manifest.
- **`python run_stage1_gate.py --override-criterion B<N> --reason "<full sentence>"`** — applies an operator override to a blocking criterion. Reason validation rules in §7.3.
- **`python run_stage1_gate.py --notify-on-pass`** — opt-in Telegram notification on clean PASS (see §7.2).

### 1.3 Package layout

```
opus-anka/
├── run_stage1_gate.py                  ← CLI entry (canonical invocation)
├── pipeline/stage1_gate/
│   ├── __init__.py
│   ├── gate.py                         ← orchestrator: run_gate() → GateResult
│   ├── criteria.py                     ← B0–B8 + W1/W3–W7 registry; severity-tiered evaluation
│   ├── golden_set.py                   ← Phase 1 regression + manual spot-check
│   ├── sanity_rules.py                 ← S1–S9 programmatic rules
│   ├── triage.py                       ← triage-tree state machine; pre-triage filtering
│   ├── manifest.py                     ← two-tier manifest writer, atomic rename, content hash
│   ├── delta.py                        ← universe_delta and delta_vs_last_run computation
│   └── history.py                      ← history/ reader for YELLOW new-warning detection
├── scripts/
│   └── verify_manifest.py              ← hash verification tool (ships with v1)
├── golden_set/
│   ├── phase1_reference/               ← immutable per-stock Claude snapshots
│   └── manual_curated.json             ← 10-stock operator spot-check set
├── artifacts/stage1_gate/
│   ├── manifest.json                   ← canonical latest (atomic-written)
│   ├── history/                        ← manifest_<ISO8601>.json archive
│   ├── tech_debt.json                  ← persistent tech debt log (inlined at build time)
│   ├── sanity_failures_<timestamp>.csv ← per-run full failure dump (not inlined)
│   └── preview_<timestamp>.json        ← --dry-run output (non-canonical)
├── config/
│   ├── fno_stocks.json                 ← universe enumeration (pre-existing)
│   ├── vague_phrases.json              ← S3 rule blocklist (new, §4 Option A)
│   └── not_in_universe.json            ← delisted/removed/excluded stocks
├── docs/superpowers/specs/
│   └── 2026-04-10-stage1-closeout-gate-design.md   ← this document
└── tests/stage1_gate/
    ├── fixtures/                       ← synthetic 10-stock minimal artifacts
    ├── test_golden_set.py
    ├── test_sanity_rules.py
    ├── test_triage.py
    ├── test_criteria.py                ← covers B0–B8, W1/W3–W7
    ├── test_manifest.py
    ├── test_manifest_verifier.py       ← hash canonicalization + tamper detection
    ├── test_delta.py
    └── test_gate_integration.py        ← reaches all 5 exit codes
```

### 1.4 Dependencies (external to `pipeline/stage1_gate/`)

| Module | Status | Used for |
|---|---|---|
| `pipeline/notifications/telegram.py` | Pre-existing (AnkaTrustEOD) | §7.2 alerting |
| `config/fno_stocks.json` | Pre-existing | Universe enumeration |
| `config/vague_phrases.json` | **New, ships with v1** | S3 sanity rule (§4) |
| `config/not_in_universe.json` | **New, ships with v1** | Pre-triage exclusion (§5.1) |
| `scripts/verify_manifest.py` | **New, ships with v1** | Stage 2 manifest verification (§6.4, §7.4) |
| `artifacts/<SYMBOL>/trust_score.json` | Pre-existing (scorer output) | Source of current grades |
| `batch_progress.json` | Pre-existing | Scoring state snapshot |

### 1.5 Data flow

```
                    ┌─────────────────────────┐
                    │ config/fno_stocks.json  │
                    │ config/not_in_universe  │
                    └────────────┬────────────┘
                                 │ enumerate + filter (pre-triage §5.1)
                                 ▼
┌──────────────────────┐     ┌────────────────┐
│ batch_progress.json  │────▶│    gate.py     │
│ artifacts/<SYM>/*    │     │  (orchestrator)│
│ golden_set/*         │     └────────┬───────┘
│ artifacts/stage1_gate│              │
│   /history/*         │              │ fan-out
│ artifacts/stage1_gate│              ▼
│   /tech_debt.json    │     ┌────────────────────────────────────┐
└──────────┬───────────┘     │ golden_set │ sanity_rules │ triage │
           │                 │    .py     │     .py      │  .py   │
           │                 └────────┬───────────┬───────┬───────┘
           │ read-only                │           │       │
           │                          └──────┬────┴───────┘
           │                                 ▼
           │                         ┌──────────────┐
           │                         │ criteria.py  │
           │                         │ (B0–B8,      │
           │                         │  W1/W3–W7)   │
           │                         └──────┬───────┘
           │                                ▼
           │                         ┌──────────────┐
           │                         │  delta.py    │◀──┐
           │                         │  history.py  │───┘ reads history/
           │                         └──────┬───────┘
           │                                ▼
           │                         ┌──────────────┐
           └────────────────────────▶│ manifest.py  │
                                     │ (atomic write│
                                     │  + hash)     │
                                     └──────┬───────┘
                                            │
                                            ▼
                     ┌─────────────────────────────────────────┐
                     │  gate_state ∈ {PASS, PASS_WITH_WARNINGS,│
                     │    PASS_WITH_OVERRIDES, FAIL,           │
                     │    PRE_CONDITION_FAILED}                │
                     │           ↓                             │
                     │  exit code ∈ {0, 1, 2, 64, 70}          │
                     └─────────────────────────────────────────┘
```

### 1.6 Key invariants

1. **Read-only with respect to batch state.** The gate never mutates `batch_progress.json` or per-stock `artifacts/<SYMBOL>/*`. It writes exclusively to `artifacts/stage1_gate/`.
2. **Idempotent.** Running the gate twice on unchanged state produces byte-identical manifests except for the `generated_at` timestamp and `content_hash` derived from it. (Validation target for rollout cycle 2 — see §7.7.)
3. **Deterministic.** Zero LLM calls inside the gate. Golden-set regression uses cached reference JSON; sanity rules are pure Python over dict structures.
4. **History-aware but not history-mutating.** The gate *reads* `artifacts/stage1_gate/history/` for YELLOW new-warning detection (§7.2) and `delta_vs_last_run` computation. It *writes* a new archived copy on every run. It never edits prior archives.
5. **Fail-closed on internal errors.** Exceptions during evaluation exit 70 and do NOT overwrite the existing canonical manifest. Prior state survives.

### 1.7 Exit codes and gate_state enum

See §7.1 for the definitive 5-value exit-code set. See §6.2 for the 5-value `gate_state` enum. The two sets are not 1:1 — multiple gate_states map to exit 0.

---

## 2. DoD Criteria (blocking + warning taxonomy)

### 2.1 Evaluation model

Every criterion is evaluated on every non-dry-run invocation. A criterion has:

- **ID** — `B<N>` (blocking) or `W<N>` (warning)
- **Name** — machine-readable snake_case
- **Severity** — `blocking` | `warning`
- **Condition** — pure function over gate inputs, returns pass/fail
- **Threshold** — numeric or categorical constant
- **Prerequisite** (optional) — if not met, criterion is *deactivated* per §2.5

Blocking failures → exit 1 + `gate_state: FAIL` + RED Telegram alert.
Warning failures → logged in manifest, Stage 2 proceeds.

### 2.2 Blocking criteria (`B0–B8`)

| ID | Name | Condition | Threshold | Rationale |
|---|---|---|---|---|
| **B0** | `pre_condition_no_stocks_mid_flight` | Zero stocks in `NOT_YET_SCORED` terminal state | `== 0` | Gate cannot evaluate a mid-flight batch. Failure = exit 2 = `PRE_CONDITION_FAILED`, not exit 1. Unique among blockers in that it's not a quality failure, it's an "evaluate later" signal. |
| **B1** | `minimum_letter_graded_universe` | Count of stocks with a real letter grade (`A+`/`A`/`B`/`C`/`D`/`F`) | `>= 100` | Below 100 letter-graded stocks, there isn't enough signal to build a balanced portfolio. |
| **B2** | `long_bucket_viable` | Count of stocks in `A+`/`A`/`B` bucket | `>= 8` | Portfolio needs a viable long side. |
| **B3** | `short_bucket_viable` | Count of stocks in `D`/`F` bucket | `>= 8` | Portfolio needs a viable short side. |
| **B4** | `golden_set_regression` | 100% of Phase 1 reference stocks land within `band_distance <= 1` of their cached Claude grade | `100%` pass, prerequisite: `reference_set_size >= 5` | Catches silent tool regressions (prompt drift, provider changes, schema changes). **Deactivated** if reference set is too small (see §2.5 and §3.1). |
| **B5** | `scoring_failure_rate` | `stocks_scoring_failed / stocks_scored` | `< 0.15` | > 15% hard failures = pipeline is broken, not just noisy. Transient 429s tolerated. |
| **B6** | `sanity_rule_pass_rate` | `passing_items / total_items` across all S1–S9 rules | `>= 0.95` | Catches structural garbage across the batch: missing page citations, enum violations, math inconsistencies. |
| **B7** | `no_unrecoverable_scoring_failures` | Count of stocks with `retry_count >= 3` in `retry_queue` | `== 0` | Retry budget per §5.3 is 3. Exhausted retries mean the scorer cannot ever succeed on that stock with current code; requires manual investigation before Stage 2. |
| **B8** | `no_diagnosis_pending` | Count of stocks in `source_gap_list` with `diagnosis == "unknown"` | `== 0` | Every INSUFFICIENT_DATA stock must carry a non-sentinel diagnosis. Silent INSUFFICIENT_DATA is the real problem — it hides real failures. **Promoted from W2 (retired) to blocking:** the "just a warning" approach let too many stocks slip through without root-cause tagging. |

**Historical note.** Earlier drafts defined W2 as "undiagnosed INSUFFICIENT_DATA" at warning severity. Operator experience showed warnings were being ignored, so the criterion was promoted to blocking severity and renamed B8. W2 is **retired** and its slot is reserved — do not reuse.

### 2.3 Warning criteria (`W1`, `W3`–`W7`)

| ID | Name | Condition | Threshold | Rationale |
|---|---|---|---|---|
| **W1** | `early_warning_scoring_failures` | Absolute count of `stocks_scoring_failed` | `<= 8` | Early signal that fires before B5. B5 catches a broken pipeline; W1 catches *starting-to-go-wrong*. ~5 scoring failures out of ~200 is normal noise; 8+ starts looking systemic. |
| **W2** | *(retired — see B8)* | — | — | Reserved. Absent from new manifests, preserved in archived ones. |
| **W3** | `distribution_skew` | `max(grade_share)` where `grade_share[g] = count(g) / total_letter_graded` | `< 0.60` | Detects systemic Gemini bias. If 60%+ of letter-graded stocks land in one grade, the prompt or model is skewed. |
| **W4** | `manual_spot_check_signoff` | `freshness_days <= 7` AND `reviewer_verdict == "pass"` on `golden_set/manual_curated.json` | `<= 7 days` | Reviewer-in-the-loop layer. Perpetually mildly nagging — forces a weekly operator glance. Never blocks. |
| **W5** | `collection_failures` | Count of `stocks_failed_collection` in batch_progress | `<= 5` | Persistent data source issues are real debt but don't halt Stage 2. |
| **W6** | `golden_set_too_small` | `reference_set_size` of Phase 1 reference set | `>= 5` | Signals that B4 is deactivated and should be bootstrapped. Fires only when B4 is skipped per §2.5. |
| **W7** | `criteria_version_mismatch` | `golden_set/manual_curated.json::criteria_version == gate.criteria_version` | Exact match | Catches drift between the gate's criteria version and the spot-check's recorded version. Different concern from W4 (freshness). Diff the criteria config, decide whether the old pass verdict still applies. Independently toggleable. |

### 2.4 Threshold rationale (locked)

| Criterion | Threshold | Source | Locked? |
|---|---|---|---|
| B1 | `>= 100` | Operator (bharat) | Yes |
| B2 | `>= 8` | Operator (bharat) | Yes |
| B3 | `>= 8` | Operator (bharat) | Yes |
| B4 | `band_distance <= 1` | Design | Yes |
| B4 prerequisite | `>= 5` ref stocks | Design | Yes |
| B5 | `< 0.15` | Design (15% hard-fail ceiling) | Yes |
| B6 | `>= 0.95` | Design (95% sanity-rule pass rate) | Yes |
| B7 | `retry_count >= 3 count == 0` | §5.3 retry budget | Yes |
| B8 | `diagnosis == "unknown" count == 0` | Design (B8 promotion) | Yes |
| W1 | `<= 8` | Design (tighter than S2 draft's 15; see Appendix B D24) | Yes |
| W3 | `< 60%` | Operator (bharat) | Yes |
| W4 | `<= 7 days` freshness | Design | Yes |
| W5 | `<= 5` | Design | Yes |
| W6 | `>= 5` | Design | Yes |
| W7 | exact match | Design | Yes |

Threshold changes require a spec amendment and bump `criteria_version`. The gate refuses to run if the on-disk spec version doesn't match the compiled constants in `criteria.py` — a defense against drift between config and code.

### 2.5 Deactivated criteria contract (universal rule)

**Problem:** some criteria have prerequisites that can fail to be met (e.g., B4 needs `reference_set_size >= 5`). A naive implementation would mark such criteria `passed: false` when the prerequisite fails, causing false blocking failures.

**Solution:** when a criterion's prerequisite is not met, it is **deactivated** (not failed). Deactivated criteria produce this shape in the manifest:

```json
{
  "B4": {
    "name": "golden_set_regression",
    "passed": true,
    "skipped": true,
    "skip_reason": "prerequisite_not_met: len(reference_set)=3 < 5",
    "prerequisite_met": false,
    "reference_set_size": 3
  }
}
```

**Invariants:**

- `passed: true, skipped: true` = **vacuously true**, deactivated, informational. A deactivated check cannot fail.
- `passed: true, skipped: false` (or `skipped` absent) = **real success**. Active criterion evaluated and passed.
- `passed: false` = **real failure**. NEVER combined with `skipped: true`.
- Active criteria **omit** the `skipped` field entirely (JSON Schema default: absent = `false`).
- Downstream tools MUST filter on `skipped === true` before interpreting `passed`.

**Applicable criteria today:** B4 (needs `reference_set_size >= 5`). **Reserved for future:** any criterion with a prerequisite.

### 2.6 Severity promotion policy

Warnings that persist across runs are candidates for promotion to blocking severity. Informal rule: if a warning fires on 3+ consecutive runs without remediation, schedule a spec amendment discussion. Historical example: W2 → B8. Promotions bump `criteria_version`.

---

## 3. Golden Set

Two independent layers with different operational models. Layer 1 is automated regression (feeds B4). Layer 2 is advisory human review (feeds W4).

### 3.1 Layer 1 — Phase 1 Reference Set (automated, B4)

**Purpose.** Catch silent regressions in the extraction + scoring pipeline by comparing current output against frozen Claude Sonnet outputs from before the Gemini migration.

**Storage.** `golden_set/phase1_reference/<SYMBOL>.json` — one file per reference stock. **Immutable once committed** — treat as ground truth. New reference files require an explicit commit and spec note.

**Reference file schema.**

```json
{
  "symbol": "HDFCBANK",
  "letter_grade": "D",
  "numeric_score": 21,
  "scored_at": "2026-04-08T14:32:10+05:30",
  "provider": "claude-sonnet-4-20250514",
  "source_commit": "7fe7a3d",
  "scoreable_items_count": 24,
  "score_breakdown": {
    "_note": "full trust_score.json output at time of capture"
  },
  "frozen_reason": "Phase 1 Claude reference before Gemini migration (2026-04-10)"
}
```

**Bootstrap: discovery script.** `scripts/build_phase1_reference.py` — one-time run that scans git history for `artifacts/<STOCK>/trust_score.json` versions where `provider` contains `"claude"`, extracts them, writes to `golden_set/phase1_reference/`. Commits the result.

**Prerequisite evaluation:**

- If discovery finds **`reference_set_size >= 5`** → **B4 is active.** Regression runs on every gate invocation.
- If discovery finds **`reference_set_size < 5`** → **B4 is deactivated** per §2.5. **W6 fires** to signal bootstrap is needed. Operator manually rescores 5+ stocks against Claude (estimated ~$5 Anthropic credit) to bootstrap the set.

**Regression logic** (`pipeline/stage1_gate/golden_set.py::run_phase1_regression`):

```python
GRADE_ORDER = ["A+", "A", "B", "C", "D", "F"]

def band_distance(ref_grade: str, curr_grade: str) -> int:
    return abs(GRADE_ORDER.index(ref_grade) - GRADE_ORDER.index(curr_grade))

def run_phase1_regression(reference_set, artifacts_root):
    results = []
    for ref in reference_set:
        current = read_current_score(ref.symbol, artifacts_root)
        if current is None:
            results.append({
                "symbol": ref.symbol,
                "reference_grade": ref.letter_grade,
                "current_grade": None,
                "band_distance": None,
                "passed": False,
                "reason": "current_score_missing",
            })
            continue
        dist = band_distance(ref.letter_grade, current.letter_grade)
        results.append({
            "symbol": ref.symbol,
            "reference_grade": ref.letter_grade,
            "current_grade": current.letter_grade,
            "band_distance": dist,
            "passed": dist <= 1,
        })
    return {
        "all_passed": all(r["passed"] for r in results),
        "per_stock": results,
    }
```

**Key rules:**

- Missing current score for a reference stock → regression fail (loud). This catches the "reference stock silently dropped out of the universe" case.
- Band distance threshold is `<= 1`. A two-grade drift (e.g., B → D) is a regression; a one-grade drift (B → C) is acceptable noise.
- Reference set membership is version-controlled. Adding/removing reference stocks requires a commit.

### 3.2 Layer 2 — Manual Curated Spot-Check (advisory, W4)

**Purpose.** Human-in-the-loop quality check. Forces a weekly operator glance at representative stocks across sectors.

**Storage.** `golden_set/manual_curated.json` — single mutable file, edited by the operator.

**Schema.**

```json
{
  "criteria_version": "1.0",
  "last_reviewed_at": "2026-04-10T21:15:00+05:30",
  "reviewer": "bharat",
  "reviewer_verdict": "pass",
  "review_session_id": "2026-04-10-stage1-review-1",
  "notes": "Defence and IT sectors looked reasonable; flagged concerns about MARUTI extraction sparsity",
  "stocks": [
    {
      "symbol": "HDFCBANK",
      "sector": "banking",
      "expected_grade_band": "C|D",
      "expected_direction": "short",
      "reviewer_notes": "Merger integration stress, deposit growth targets quietly abandoned"
    }
  ]
}
```

**`criteria_version` field.** Must match the gate's compiled `CRITERIA_VERSION` constant. Mismatch fires **W7** — different concern from W4 (freshness). Rationale: if the gate's definition of "passing" changed, the operator's prior spot-check verdict may no longer apply.

**`reviewer_verdict` enum:** `"pass"` | `"fail"` | `"uncertain"`. Only `"pass"` clears W4.

**Recommended initial 10-stock set (2 per sector):**

| Sector | Symbols |
|---|---|
| Banking | HDFCBANK, ICICIBANK |
| Pharma | DRREDDY, CIPLA |
| IT | INFY, TCS |
| Defence | HAL, BEL |
| FMCG | HINDUNILVR, NESTLEIND |

**Spot-check logic** (`golden_set.py::run_manual_spot_check`):

```python
def run_manual_spot_check(manual_curated_path, artifacts_root, gate_criteria_version):
    data = json.loads(Path(manual_curated_path).read_text())
    freshness_days = (datetime.now(TZ) - isoparse(data["last_reviewed_at"])).days
    per_stock = []
    for entry in data["stocks"]:
        current = read_current_score(entry["symbol"], artifacts_root)
        in_band = current.letter_grade in entry["expected_grade_band"].split("|") if current else False
        per_stock.append({
            "symbol": entry["symbol"],
            "sector": entry["sector"],
            "expected_grade_band": entry["expected_grade_band"],
            "current_grade": current.letter_grade if current else None,
            "in_band": in_band,
            "reviewer_notes": entry["reviewer_notes"],
        })
    return {
        "curated_set_size": len(data["stocks"]),
        "criteria_version": data["criteria_version"],
        "criteria_version_matches": data["criteria_version"] == gate_criteria_version,
        "last_reviewed_at": data["last_reviewed_at"],
        "freshness_days": freshness_days,
        "reviewer": data["reviewer"],
        "reviewer_verdict": data["reviewer_verdict"],
        "review_session_id": data["review_session_id"],
        "notes": data["notes"],
        "stale": freshness_days > 7,
        "per_stock": per_stock,
    }
```

**Review workflow:**

1. Gate runs, manifest is written with current side-by-side of expected vs. actual grades for the 10 curated stocks.
2. Operator eyeballs the side-by-side in the next review session.
3. If it looks right: operator updates `last_reviewed_at`, sets `reviewer_verdict: "pass"`, commits. Next gate run sees fresh review, W4 clears.
4. If it looks wrong: operator investigates, fixes, re-runs gate, re-reviews.
5. W4 is **perpetually mildly nagging** — that's intentional.

---

## 4. Programmatic Sanity Rules

Pure-Python checks applied to every extracted guidance item after scoring. Zero LLM calls. Feed criterion B6 (`>= 95%` item-level pass rate).

### 4.1 Rule set (`S1`–`S9`)

Each rule is a pure function `(item: dict, stock_context: dict) → RuleResult` where `RuleResult = PASS | FAIL(rule_id, reason)`.

| Rule ID | Name | Check | Rationale |
|---|---|---|---|
| **S1** | `page_citation_exists` | `item.source_page` is an `int` AND `1 <= source_page <= pdf_total_pages` for the AR it came from | Gemini must cite a real page. No page 0, no page 9999, no null. |
| **S2** | `variance_math_consistent` | If `target_value`, `actual_value`, `variance_pct` all present: `abs(variance_pct - ((actual - target) / target * 100)) < 0.5` | Catches residual math-expression bugs and hallucinated variances. |
| **S3** | `target_not_vague` | `target_value` does not match any phrase in `config/vague_phrases.json` (case-insensitive regex) | Enforces existing `_filter_vague_guidance` logic at gate time. Catches items that slipped past the scorer. |
| **S4** | `target_has_magnitude` | `target_value` contains at least one digit OR is a recognized qualitative-but-bounded term (`"doubled"`, `"tripled"`, `"halved"`) | Every target should be measurable or at least bounded. |
| **S5** | `fy_label_valid` | `fiscal_year` matches `^FY2[0-9]$` AND `int(fiscal_year[2:]) <= current_fy + 2` | Catches "FY30" hallucinations, garbage labels, off-by-many typos. |
| **S6** | `status_in_enum` | `status ∈ {"delivered", "missed", "partial", "pending", "withdrawn", "unknown"}` | Prevents freeform status strings from breaking triage. |
| **S7** | `materiality_in_enum` | `materiality ∈ {"critical", "important", "routine"}` | Prevents freeform materiality from breaking weighted scoring. |
| **S8** | `no_null_in_required` | Required fields (`symbol`, `fiscal_year`, `target_value`, `status`, `source_page`) are non-null and non-empty strings/ints | Catches null-from-provider bugs. |
| **S9** | `symbol_matches_stock` | `item.symbol` (if present) equals the stock directory name | Catches cross-contamination between concurrent extractions. |

### 4.2 `config/vague_phrases.json` (S3 blocklist)

Extensible config file. Ships with an initial list derived from the scorer's existing `_filter_vague_guidance` blocklist. Operator appends without a code change.

```json
{
  "schema_version": "1.0",
  "phrases": [
    "\\bhigher\\b",
    "\\bcontinue to\\b",
    "\\bwe believe\\b",
    "\\bstrong growth\\b",
    "\\brobust\\b",
    "\\bgoing forward\\b",
    "\\bboard resolution\\b"
  ]
}
```

Phrases are regex patterns, applied case-insensitively. The gate compiles them once at startup.

### 4.3 Aggregation for B6

```python
def evaluate_b6(scored_stocks, rules, vague_phrases):
    total_items = 0
    passing_items = 0
    per_rule_fails = {r.id: 0 for r in rules}
    per_stock_stats = []
    for stock in scored_stocks:
        stock_total = len(stock.items)
        stock_passing = 0
        for item in stock.items:
            results = [rule(item, stock.context) for rule in rules]
            if all(r.passed for r in results):
                stock_passing += 1
            else:
                for r in results:
                    if not r.passed:
                        per_rule_fails[r.rule_id] += 1
        total_items += stock_total
        passing_items += stock_passing
        per_stock_stats.append({
            "symbol": stock.symbol,
            "total_items": stock_total,
            "passing_items": stock_passing,
            "pass_rate": stock_passing / stock_total if stock_total else 0.0,
        })
    pass_rate = passing_items / total_items if total_items else 0.0
    return {
        "overall_pass_rate": pass_rate,
        "total_items": total_items,
        "passing_items": passing_items,
        "failing_items": total_items - passing_items,
        "per_rule_fails": per_rule_fails,
        "per_stock_stats": per_stock_stats,
        "b6_passed": pass_rate >= 0.95,
    }
```

**Per-item granularity is the contract.** A 20-item stock with 1 bad item contributes 19 passes + 1 fail, not "the whole stock fails." This preserves signal from mostly-good stocks.

### 4.4 Manifest output for sanity rules

See §6.6. The manifest reports the overall pass rate, per-rule breakdown, top 10 offending stocks, and a sample of 5 failing items per failing rule. Full failure dump goes to `sanity_failures_<timestamp>.csv` (not inlined — can be large).

---

## 5. Triage Tree

### 5.1 Pre-triage filtering (NOT_IN_UNIVERSE exclusion)

**Before the triage tree runs,** the gate filters the universe:

```python
enumerated = read_fno_stocks()           # config/fno_stocks.json
not_in_universe = read_not_in_universe() # config/not_in_universe.json
active = [s for s in enumerated if s not in not_in_universe]
```

Stocks in `not_in_universe.json` (delisted, removed from F&O, or manually excluded) **never enter the triage tree**. They are counted in `summary.stocks_not_in_universe` for audit, surfaced in `universe_delta.removed_since_last_gate` when the delta is non-zero, and otherwise ignored.

**This is the DoD denominator contract:** all blocking-criteria denominators (B1 count, B2/B3 bucket sizes, B5 ratio, B6 ratio) use `universe_active`, never `universe_enumerated`.

### 5.2 Terminal state machine (for every stock in `universe_active`)

Every stock in `universe_active` must land in exactly one of these terminal states:

```
                    ┌────────────────────────┐
                    │ stock in universe_active│
                    └────────────┬────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────┐
                  │ Has current trust_score? │
                  └──────────┬───────────────┘
                             │
               ┌─────────────┴──────────────┐
               │ YES                        │ NO
               ▼                            ▼
     ┌──────────────────┐         ┌────────────────┐
     │ letter_grade     │         │ collection ok? │
     │ present?         │         └────────┬───────┘
     └────┬─────────────┘                  │
          │                       ┌────────┴────────┐
     ┌────┴─────┐                 │ YES             │ NO
     │ YES      │ NO              ▼                 ▼
     ▼          ▼        ┌────────────────┐  ┌────────────────┐
  (grade)   INSUFFICIENT │ scoring error  │  │ no PDFs OR     │
     │      _DATA        │ at runtime?    │  │ all corrupt    │
     │      → source_    └────────┬───────┘  └────────┬───────┘
     │       gap_list             │                   │
     │         │           ┌──────┴──────┐            │
     │         │           │ YES         │ NO         │
     │         │           ▼             ▼            │
     │         │     SCORING_FAILED   NOT_YET_       │
     │         │     → retry_queue    SCORED          │
     │         │                      (sentinel)      │
     │         │                                      │
     │         ▼                                      ▼
     │   source_gap_list                       RE_DOWNLOAD_QUEUE
     │   (diagnosis required)                  → bse_rescue_queue
     │
     ▼
Grade-based bucket routing (§5.4)
```

### 5.3 Terminal state definitions

| State | Entry condition | Bucket | Auto-retry? | Exit action |
|---|---|---|---|---|
| **(letter-graded)** | Scored successfully with `letter_grade in GRADE_ORDER` | Routed by grade → `longs` / `shorts` / `watchlist` (§5.4) | N/A | Enters portfolio consideration |
| **INSUFFICIENT_DATA** (→ `source_gap_list`) | Scored successfully but `scoreable_items < 5` | None | No (manual) | Operator sources alternative data; until then, out of portfolio. Every entry must carry a non-`unknown` `diagnosis` field (enum in §5.5). B8 fails if any entry has `diagnosis == "unknown"`. |
| **SCORING_FAILED** (→ `retry_queue`) | Scoring raised a runtime exception (JSON parse error, provider timeout, etc.) | None | Yes, 3× automated | `run_batch_loop.py` retries up to 3 times. `retry_count >= 3` → stock is stuck and B7 fails. |
| **RE_DOWNLOAD_QUEUE** (→ `bse_rescue_queue`) | No AR PDFs exist OR all existing PDFs have 0 extractable pages | None | Manual trigger | Future: `scripts/rescue_from_bse.py` re-attempts from BSE historical archive. Until then, stock is out. |
| **NOT_YET_SCORED** (sentinel) | Collected but scoring not yet attempted | None | N/A | **Not a valid terminal state for gate evaluation.** If the gate sees any stock in this state, it returns `PRE_CONDITION_FAILED` (B0 fails) and exits 2. The batch loop continues scoring and re-invokes the gate on the next cycle. |

### 5.4 Grade-based bucket routing

| Grade | Bucket | Stage 2 role |
|---|---|---|
| A+ | `longs` | Long candidate, weighted highest |
| A | `longs` | Long candidate |
| B | `longs` | Long candidate, weighted lowest in long bucket |
| C | `watchlist` | Not tradeable; monitored for upgrades |
| D | `shorts` | Short candidate |
| F | `shorts` | Short candidate, weighted highest in short bucket |

### 5.5 INSUFFICIENT_DATA diagnosis enum (feeds B8)

Every stock in `source_gap_list` must carry a `diagnosis` field populated by the scorer at the time `trust_score.json` is written. Enum:

| Diagnosis | Meaning | Possible remediation |
|---|---|---|
| `no_numeric_guidance` | AR text was read, but the company writes purely qualitative guidance (no numeric targets) | Check concall transcripts for numeric guidance; if none, company is not scoreable from ARs alone. |
| `corrupt_pdfs` | Some years' PDFs were corrupt but not all | `scripts/rescue_from_bse.py` fresh downloads |
| `sector_prompt_mismatch` | Extraction prompt doesn't fit the sector (financials, REITs, etc.) | Build sector-specific prompt — see `sector_libraries/` |
| `insufficient_years` | <3 years of AR data available | Wait for the company to mature; expand lookback window if historical data exists |
| `extraction_returned_empty` | Gemini produced an empty items array with no error | Investigate prompt; likely silent Gemini failure. Candidate for adversarial review. |
| `unknown` | Diagnosis not yet determined | **Triggers B8 failure.** Operator must resolve to one of the above before next gate run. |

**Diagnosis is written by `run_trust_score.py`, not by the gate.** The gate only *validates* that every INSUFFICIENT entry has a non-`unknown` diagnosis.

**Note on `no_ar_pdfs`:** An earlier draft listed `no_ar_pdfs` as a diagnosis. It is **not** — stocks with zero AR PDFs route to `RE_DOWNLOAD_QUEUE`, a different terminal state. They never reach INSUFFICIENT_DATA.

### 5.6 Minimum-bucket-size enforcement (B2 / B3)

```python
longs = [s for s in scored if s.grade in ("A+", "A", "B")]
shorts = [s for s in scored if s.grade in ("D", "F")]

blocking_failures = []
if len(longs) < 8:
    blocking_failures.append(("B2", f"Only {len(longs)} long candidates, need >= 8"))
if len(shorts) < 8:
    blocking_failures.append(("B3", f"Only {len(shorts)} short candidates, need >= 8"))
```

If the universe produces an unbalanced basket (e.g., 40 shorts and 3 longs), the gate blocks. Operator decides:

1. Expand `fno_stocks.json` with more candidates, OR
2. Loosen grading thresholds (requires spec amendment, bumps `criteria_version`), OR
3. Accept the imbalance and override B2/B3 with a full-sentence reason.

**No silent "partial portfolio" ships.**

### 5.7 Explicit non-goals

**Sector concentration is NOT enforced by the gate.** That belongs to Stage 2 portfolio construction (`run_model_portfolio.py`). The gate's job is to hand Stage 2 a **clean universe**, not to pre-shape the portfolio.

---

## 6. Handoff Manifest Schema

### 6.1 Purpose

The canonical two-tier manifest at `artifacts/stage1_gate/manifest.json` is the single authoritative snapshot of "Stage 1 is done (or not) and here's why." Stage 2 consumers (`/ultraplan`, `run_model_portfolio.py`) read this file to ground their work.

**Two-tier design:**

- **Tier 1 (in manifest):** verdict, criteria pass/fail, triage buckets, summary stats, delta vs. last run, sanity-rule aggregate, overrides, tech debt, golden-set results.
- **Tier 2 (outside manifest):** full per-stock artifacts, raw batch progress, sanity-failure CSV, historical archives. The manifest's `pointers` section provides paths.

### 6.2 Top-level shape

```json
{
  "schema_version": "1.0",
  "criteria_version": "1.0",
  "generated_at": "2026-04-10T22:15:30+05:30",
  "generated_by": "run_stage1_gate.py",
  "git_commit": "7fe7a3d",
  "git_branch": "master",
  "operator": "bharat",

  "gate_state": "PASS",

  "content_hash": "sha256:a3f5b9c7...",

  "summary": { "..." : "see §6.3" },
  "criteria": { "blocking": { "...": "..." }, "warning": { "...": "..." } },
  "triage": { "...": "see §6.5" },
  "bucket_counts": { "...": "see §6.5" },
  "universe_delta": { "...": "see §6.7" },
  "delta_vs_last_run": { "...": "see §6.8" },
  "golden_set": { "...": "see §6.6" },
  "sanity_rules": { "...": "see §6.6" },
  "overrides": [ "see §6.9" ],
  "tech_debt": [ "see §6.10" ],
  "pointers": { "...": "see §6.11" }
}
```

### 6.2.1 `gate_state` enum

One of exactly these 5 values:

- `"PASS"` — all blocking criteria passed cleanly, no warnings fired
- `"PASS_WITH_WARNINGS"` — all blocking criteria passed, ≥1 warning fired
- `"PASS_WITH_OVERRIDES"` — ≥1 blocking criterion failed but was overridden; Stage 2 unblocked, audit-logged
- `"FAIL"` — ≥1 blocking criterion failed without override; Stage 2 blocked
- `"PRE_CONDITION_FAILED"` — B0 tripped; evaluation not attempted (stocks still being scored)

**Exit codes 64 and 70 do not populate `gate_state`.** The `gate_state` enum covers completed evaluations only. When the gate crashes with 64 (CLI error) or 70 (internal error), no manifest is written, and the prior canonical manifest remains on disk untouched (atomic write guarantee, §6.13).

### 6.3 `summary` — quick-glance stats (three-way universe accounting)

```json
{
  "summary": {
    "universe_enumerated": 213,
    "universe_active": 211,
    "stocks_not_in_universe": 2,
    "stocks_removed_since_last_run": 0,

    "stocks_scored": 163,
    "stocks_letter_graded": 73,
    "stocks_insufficient_data": 87,
    "stocks_scoring_failed": 3,
    "stocks_unrecoverable": 0,
    "stocks_bse_rescue_queue": 1,
    "stocks_not_yet_scored": 0,

    "longs_count": 21,
    "shorts_count": 36,
    "watchlist_count": 16,

    "blocking_criteria_passed": "8/9",
    "warning_criteria_passed": "5/6",
    "overrides_applied": 1
  }
}
```

**Universe accounting contract (locked):**

- `universe_enumerated = len(fno_stocks.json)` — raw enumeration
- `universe_active = universe_enumerated - stocks_not_in_universe` — **the DoD denominator**
- `stocks_not_in_universe` — from `config/not_in_universe.json`
- `stocks_removed_since_last_run` — diff against the most recent prior manifest's `stocks_not_in_universe` set
- All blocking criteria denominators use `universe_active`, never `universe_enumerated`

### 6.4 `content_hash` and verification

**Field:** `"content_hash": "sha256:<hex>"` — top-level, mandatory, computed over every other field in canonical JSON form.

**Computation:**

```python
import hashlib, json

def compute_manifest_hash(manifest: dict) -> str:
    without_hash = {k: v for k, v in manifest.items() if k != "content_hash"}
    canonical = json.dumps(
        without_hash,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Determinism requirements:**

- `sort_keys=True` — stable key ordering
- `separators=(",", ":")` — no whitespace
- `ensure_ascii=False` — Unicode passes through unchanged

**Verification tool:** `scripts/verify_manifest.py <path>`. Recomputes the hash and compares. Exit 0 = valid, exit 1 = tampered or corrupt. Ships with v1.

**Contract for Stage 2 consumers:** `/ultraplan` and `run_model_portfolio.py` MUST invoke `scripts/verify_manifest.py` before reading manifest contents. On verification failure, they refuse to run and log `TAMPERING_DETECTED`. Documented in the operator runbook (§7.3).

### 6.5 `criteria` — per-criterion evidence

```json
{
  "criteria": {
    "blocking": {
      "B0": {
        "name": "pre_condition_no_stocks_mid_flight",
        "passed": true,
        "expected": "0 stocks in NOT_YET_SCORED",
        "actual": "0 stocks in NOT_YET_SCORED"
      },
      "B1": {
        "name": "minimum_letter_graded_universe",
        "passed": false,
        "expected": ">= 100",
        "actual": 73,
        "overridden": true,
        "override_reason": "initial gate run before full rescore completes; ship partial for Stage 2 smoke testing on 2026-04-10",
        "override_operator": "bharat"
      },
      "B2": {
        "name": "long_bucket_viable",
        "passed": true,
        "expected": ">= 8",
        "actual": 21
      },
      "B3": {
        "name": "short_bucket_viable",
        "passed": true,
        "expected": ">= 8",
        "actual": 36
      },
      "B4": {
        "name": "golden_set_regression",
        "passed": true,
        "reference_set_size": 6,
        "prerequisite_met": true,
        "per_stock": [
          {"symbol": "HDFCBANK", "reference_grade": "D", "current_grade": "D", "band_distance": 0, "passed": true},
          {"symbol": "HINDUNILVR", "reference_grade": "D", "current_grade": "C", "band_distance": 1, "passed": true}
        ]
      },
      "B5": {
        "name": "scoring_failure_rate",
        "passed": true,
        "expected": "< 0.15",
        "actual": 0.018
      },
      "B6": {
        "name": "sanity_rule_pass_rate",
        "passed": true,
        "expected": ">= 0.95",
        "actual": 0.972,
        "total_items": 1843,
        "passing_items": 1791
      },
      "B7": {
        "name": "no_unrecoverable_scoring_failures",
        "passed": true,
        "expected": "retry_count >= 3 count == 0",
        "actual": 0
      },
      "B8": {
        "name": "no_diagnosis_pending",
        "passed": true,
        "expected": "diagnosis == 'unknown' count == 0",
        "actual": 0
      }
    },
    "warning": {
      "W1": {"name": "early_warning_scoring_failures", "passed": true, "expected": "<= 8", "actual": 3},
      "W3": {"name": "distribution_skew", "passed": true, "expected": "max_grade_share < 0.60", "actual": 0.23, "dominant_grade": "F"},
      "W4": {
        "name": "manual_spot_check_signoff",
        "passed": false,
        "reason": "last_reviewed_at is 9 days old",
        "expected": "freshness_days <= 7 AND reviewer_verdict == 'pass'",
        "last_reviewed_at": "2026-04-01T14:22:00+05:30",
        "freshness_days": 9,
        "reviewer_verdict": "pass"
      },
      "W5": {"name": "collection_failures", "passed": true, "expected": "<= 5", "actual": 1},
      "W6": {"name": "golden_set_too_small", "passed": true, "expected": ">= 5", "actual": 6},
      "W7": {
        "name": "criteria_version_mismatch",
        "passed": true,
        "expected": "manual_curated.criteria_version == gate.criteria_version",
        "gate_criteria_version": "1.0",
        "manual_curated_criteria_version": "1.0"
      }
    }
  }
}
```

**Criterion entry contract:**

- Every entry has `name: str` and `passed: bool`.
- Every entry SHOULD have human-readable `expected` and typed `actual`. Exceptions (B4, which uses `per_stock`) document their own shape.
- Deactivated criteria add `skipped: true`, `skip_reason: str`, and criterion-specific prerequisite fields (see §2.5).
- Overridden criteria add `overridden: true`, `override_reason: str`, `override_operator: str`. Active criteria omit these fields.
- W2 is retired — its slot is reserved. New manifests omit it. Archived manifests may contain it.

### 6.6 `golden_set` and `sanity_rules` detail

```json
{
  "golden_set": {
    "phase1_reference": {
      "reference_set_size": 6,
      "reference_set_stocks": ["HDFCBANK", "HINDUNILVR", "HAL", "ITC", "DRREDDY", "DABUR"],
      "all_passed": true,
      "per_stock": [
        {"symbol": "HDFCBANK", "reference_grade": "D", "current_grade": "D", "band_distance": 0, "passed": true}
      ]
    },
    "manual_spot_check": {
      "curated_set_size": 10,
      "criteria_version": "1.0",
      "criteria_version_matches": true,
      "last_reviewed_at": "2026-04-01T14:22:00+05:30",
      "freshness_days": 9,
      "reviewer": "bharat",
      "reviewer_verdict": "pass",
      "review_session_id": "2026-04-01-stage1-review-1",
      "notes": "Defence and IT sectors looked reasonable; flagged concerns about MARUTI extraction sparsity",
      "stale": true,
      "per_stock": [
        {
          "symbol": "HDFCBANK",
          "sector": "banking",
          "expected_grade_band": "C|D",
          "current_grade": "D",
          "in_band": true,
          "reviewer_notes": "Merger integration stress, deposit growth targets quietly abandoned"
        }
      ]
    }
  },
  "sanity_rules": {
    "overall_pass_rate": 0.972,
    "total_items": 1843,
    "passing_items": 1791,
    "failing_items": 52,
    "per_rule_fails": {
      "S1": 0, "S2": 4, "S3": 18, "S4": 7, "S5": 0, "S6": 2, "S7": 0, "S8": 21, "S9": 0
    },
    "per_stock_stats_worst": [
      {"symbol": "DIXON", "total_items": 14, "passing_items": 10, "pass_rate": 0.714},
      {"symbol": "PAYTM", "total_items": 9, "passing_items": 7, "pass_rate": 0.778}
    ],
    "sample_failures_per_rule": {
      "S3": [
        {"symbol": "DIXON", "item_id": "fy24_revenue_growth", "target_value": "continue to focus on scaling", "reason": "matched vague phrase: 'continue to'"}
      ]
    },
    "full_failure_csv": "artifacts/stage1_gate/sanity_failures_2026-04-10T22-15-30.csv"
  }
}
```

The `manual_spot_check` block includes `review_session_id` and `notes` verbatim — the audit trail survives the manifest without requiring a lookup to the source file.

### 6.5.2 `triage` and `bucket_counts`

```json
{
  "triage": {
    "longs": [
      {"symbol": "PGEL", "grade": "A+", "score": 92, "sector": "electronics_mfg"}
    ],
    "shorts": [
      {"symbol": "ADANIENT", "grade": "F", "score": 19, "sector": "conglomerate"}
    ],
    "watchlist": [
      {"symbol": "HAL", "grade": "C", "score": 49, "sector": "defence"}
    ],
    "source_gap_list": [
      {
        "symbol": "IDEA",
        "diagnosis": "no_numeric_guidance",
        "remediation": "Check concalls for numeric guidance; otherwise company is not scoreable from ARs alone.",
        "last_attempted": "2026-04-10T15:40:11+05:30"
      }
    ],
    "retry_queue": [
      {"symbol": "ABCCORP", "retry_count": 1, "last_error": "Gemini 429 rate limit", "last_attempted": "2026-04-10T16:12:03+05:30"}
    ],
    "bse_rescue_queue": [
      {"symbol": "XYZLTD", "reason": "all_pdfs_corrupt", "ar_years_attempted": ["FY23", "FY24", "FY25"]}
    ]
  },
  "bucket_counts": {
    "longs": 21,
    "shorts": 36,
    "watchlist": 16,
    "source_gap_list": 87,
    "retry_queue": 2,
    "bse_rescue_queue": 1
  }
}
```

**Remediation text** is joined from a `DIAGNOSIS_REMEDIATIONS` lookup at manifest-build time; the scorer writes only the enum code. This keeps remediation text editable without touching every stock's `trust_score.json`.

### 6.7 `universe_delta` — universe membership changes

```json
{
  "universe_delta": {
    "added_since_last_gate": ["NEWCOXYZ"],
    "removed_since_last_gate": ["OLDCOABC"],
    "newly_not_in_universe": ["DELISTED1"],
    "previous_manifest_ref": "history/manifest_2026-04-10T18-00-00.json",
    "previous_universe_active": 210,
    "current_universe_active": 211
  }
}
```

**Fields:**

- `added_since_last_gate` — stocks that joined `fno_stocks.json` since the previous manifest
- `removed_since_last_gate` — stocks that left `fno_stocks.json` since the previous manifest
- `newly_not_in_universe` — stocks added to `not_in_universe.json` since the previous manifest (subset of "still enumerated but excluded")
- `previous_manifest_ref` — relative path under `artifacts/stage1_gate/` to the prior manifest used for diff
- `previous_universe_active` and `current_universe_active` — denominator audit

On first-ever gate run (no prior manifest exists), all four list fields are empty arrays and `previous_manifest_ref` is `null`.

### 6.8 `delta_vs_last_run` — state changes since previous gate

```json
{
  "delta_vs_last_run": {
    "previous_manifest_ref": "history/manifest_2026-04-10T18-00-00.json",
    "previous_gate_state": "PASS_WITH_WARNINGS",
    "current_gate_state": "PASS_WITH_OVERRIDES",
    "grade_changes": [
      {"symbol": "HDFCBANK", "prev": "C", "curr": "D", "direction": "down"},
      {"symbol": "INFY", "prev": "C", "curr": "B", "direction": "up"}
    ],
    "criteria_flips": [
      {"id": "B1", "prev": "passed", "curr": "failed"},
      {"id": "W4", "prev": "passed", "curr": "failed"}
    ],
    "warnings_added": ["W4"],
    "warnings_cleared": ["W5"],
    "overrides_added": ["B1"],
    "overrides_cleared": []
  }
}
```

**Fields:**

- `previous_manifest_ref` — same ref as `universe_delta`
- `previous_gate_state` and `current_gate_state` — before/after verdict
- `grade_changes` — only stocks whose letter grade moved; `direction` ∈ `"up"` | `"down"` | `"lateral"` (lateral = skipped grades like F→A is unusual but possible)
- `criteria_flips` — criteria whose pass/fail changed
- `warnings_added` and `warnings_cleared` — set-diff of warning IDs
- `overrides_added` and `overrides_cleared` — set-diff of overridden blocking IDs

On first-ever gate run, all fields are empty except the `previous_*` fields which are `null`.

`delta_vs_last_run` feeds:

- The YELLOW Telegram alert's new-warning detection (§7.2)
- The operator's weekly trend review
- The 3-consecutive-run override detection (§7.3 PASS_WITH_OVERRIDES runbook)

### 6.9 `overrides` — operator override audit

```json
{
  "overrides": [
    {
      "criterion_id": "B1",
      "operator": "bharat",
      "reason": "initial gate run before full rescore completes; ship partial for Stage 2 smoke testing on 2026-04-10",
      "reason_hash": "sha256:9c2e1d...",
      "applied_at": "2026-04-10T22:14:53+05:30",
      "original_failure": {
        "expected": ">= 100",
        "actual": 73
      }
    }
  ]
}
```

**Fields:**

- `criterion_id` — must be a blocking criterion (`B0`–`B8`); overrides on B0 are refused (B0 is a runtime state, not a quality judgment)
- `operator` — defaults to `os.environ["GATE_OPERATOR"]` or `"unknown"`; logged as-is
- `reason` — full sentence, validation rules in §7.3
- `reason_hash` — sha256 of the raw reason string; logged to `logs/stage1_gate.log` so operators can prove later which reason was applied
- `applied_at` — ISO8601 with timezone
- `original_failure` — copied from the criterion's evidence at evaluation time; preserves the failing values even though the criterion's top-level entry shows `passed: true` due to override

**Contract:** overrides do NOT persist across runs. The next gate invocation requires re-specifying. This is intentional friction to prevent normalization of bad overrides.

### 6.10 `tech_debt` — persistent debt log

```json
{
  "tech_debt": [
    {
      "id": "TD1",
      "description": "source_page is soft-enforced in S1/S8; promote to required once extraction prompt reliably produces page cites",
      "created_at": "2026-04-10",
      "blocks": null,
      "owner": "bharat"
    }
  ]
}
```

**Storage pattern:** tech debt entries survive across runs by living in `artifacts/stage1_gate/tech_debt.json` (separate file). The manifest writer reads this file at build time and inlines its contents. To add a debt item, operator edits the JSON file directly; the next gate run picks it up.

**Fields:**

- `id` — unique identifier (`TD<N>`)
- `description` — free text
- `created_at` — ISO date
- `blocks` — criterion ID that this debt blocks, or `null` if informational
- `owner` — responsible operator

No criterion currently evaluates tech_debt contents. It is audit metadata only.

### 6.11 `pointers` — Tier 2 lookup table

```json
{
  "pointers": {
    "batch_progress_snapshot": "artifacts/stage1_gate/history/batch_progress_2026-04-10T22-15-30.json",
    "per_stock_artifacts_root": "artifacts/",
    "golden_set_reference_root": "golden_set/phase1_reference/",
    "manual_curated_path": "golden_set/manual_curated.json",
    "config_root": "config/",
    "fno_stocks_path": "config/fno_stocks.json",
    "not_in_universe_path": "config/not_in_universe.json",
    "vague_phrases_path": "config/vague_phrases.json",
    "tech_debt_path": "artifacts/stage1_gate/tech_debt.json",
    "full_sanity_failure_csv": "artifacts/stage1_gate/sanity_failures_2026-04-10T22-15-30.csv"
  }
}
```

**Contract:** Stage 2 consumers resolve all secondary lookups through `pointers`. They never re-implement path resolution. If a file moves in future versions, only the `pointers` keys change and Stage 2 continues to work without code edits.

All paths are **relative to the opus-anka repo root**, not to the manifest location. This keeps them portable across run environments.

### 6.12 Manifest file locations

| Path | Purpose |
|---|---|
| `artifacts/stage1_gate/manifest.json` | Canonical latest manifest. Stage 2 reads this. |
| `artifacts/stage1_gate/history/manifest_<ISO8601>.json` | Archived on every run. Used by `universe_delta`, `delta_vs_last_run`, YELLOW new-warning detection, and audit. |
| `artifacts/stage1_gate/history/batch_progress_<ISO8601>.json` | Snapshot of `batch_progress.json` at gate invocation time. Cheap to store, critical for reproducing a gate run. |
| `artifacts/stage1_gate/tech_debt.json` | Persistent tech debt; inlined into manifest at build time. |
| `artifacts/stage1_gate/sanity_failures_<ISO8601>.csv` | Full sanity-rule failure dump per run. Not inlined — can be large. |
| `artifacts/stage1_gate/preview_<ISO8601>.json` | `--dry-run` output; non-canonical; never used by Stage 2. |

Filename timestamp format: ISO8601 with `:` replaced by `-` for filesystem safety (`2026-04-10T22-15-30`).

### 6.13 Atomicity guarantee

Manifest writes are **atomic via temp-file rename:**

```python
def write_manifest_atomic(manifest: dict, path: Path) -> None:
    manifest["content_hash"] = compute_manifest_hash(manifest)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic on both POSIX and Windows
```

**Properties:**

1. Readers never see a half-written manifest.
2. If the write fails at any step, the old manifest is untouched.
3. `content_hash` is computed *after* the manifest dict is finalized but *before* serialization to the temp file; the file on disk always contains a valid hash.
4. Exceptions during evaluation (exit 70) never reach this function — the prior canonical manifest stays intact.

The same pattern applies to `history/manifest_<ISO8601>.json` writes.

---

## 7. Failure Handling & Operator Workflow

### 7.1 Exit codes — the closed set

| Code | Meaning | `run_batch_loop.py` reaction |
|---|---|---|
| **0** | `PASS`, `PASS_WITH_WARNINGS`, or `PASS_WITH_OVERRIDES` — Stage 2 unblocked | Stop scoring, signal "Stage 1 done", trigger Stage 2 |
| **1** | `FAIL` — ≥1 blocking criterion failed without override | Halt, send RED Telegram alert, wait for operator |
| **2** | `PRE_CONDITION_FAILED` (B0) — scoring still in progress | Keep scoring, re-invoke gate on next cycle. Not an error. |
| **64** | CLI usage error (missing `--reason`, bad flag, unknown criterion ID, etc.) | Halt, alert — script bug or operator typo |
| **70** | Internal gate error (exception during evaluation) | Halt, alert with stack trace — gate logic bug |

**Invariants:**

- No other exit codes are permitted. Adding a new exit code requires a spec amendment.
- **Exit 64 and 70 do not write a manifest.** The prior canonical manifest remains on disk untouched (§6.13 atomic write guarantee).
- `gate_state` enum (§6.2.1) covers completed evaluations only — exit 64/70 have no associated `gate_state`.

### 7.2 Telegram alerting — 4 tiers

Alerts route through the existing `pipeline/notifications/telegram.py` (same channel as `AnkaTrustEOD`). No new infrastructure.

| Tier | Trigger | Message shape |
|---|---|---|
| **🔴 RED** | `gate_state == "FAIL"` OR exit code ∈ {1, 64, 70} | `Stage 1 gate FAILED. Blocking: [B1, B4]. Manifest: artifacts/stage1_gate/manifest.json. Stage 2 blocked.` |
| **🟠 ORANGE** | `gate_state == "PASS_WITH_OVERRIDES"` | `Stage 1 passed with overrides by @{operator}. Overridden: [B1]. Reason: "{first 120 chars}...". Stage 2 unblocked.` |
| **🟡 YELLOW** | `gate_state == "PASS_WITH_WARNINGS"` AND `len(delta_vs_last_run.warnings_added) >= 1` | `Stage 1 passed, new warnings: [W4 stale spot-check]. Stage 2 unblocked.` |
| **🟢 GREEN** | `gate_state == "PASS"` (clean) | **Not sent by default.** Opt in with `--notify-on-pass`. Avoids alert fatigue. |

**Rules:**

- `PRE_CONDITION_FAILED` (exit 2) is **not** alerted. It's the normal runtime state of the batch loop mid-scoring — alerting would spam. Logged only to `logs/stage1_gate.log`.
- YELLOW fires only on *new* warnings (diff vs. previous PASS manifest), not on repeat warnings. This relies on `delta_vs_last_run.warnings_added`. If the current manifest is the first run, every warning is "new" and YELLOW fires.
- RED on exit 64 or 70 includes a stack trace or CLI error line (whichever is available), truncated to Telegram message limits.

**New-warning detection:** uses `delta_vs_last_run.warnings_added` directly. No independent `history/` walk needed — the computation happens in `delta.py` during manifest build.

### 7.3 Runbook — operator response per state

#### FAIL (exit 1)

1. Read `artifacts/stage1_gate/manifest.json` → `criteria.blocking` → identify `passed: false` entries.
2. For each failing criterion, follow its diagnostic trail:

| Criterion | Diagnostic trail | Typical fix |
|---|---|---|
| **B0** | `triage.not_yet_scored` + `logs/batch_trust*.log` | Wait; batch loop re-invokes gate. If stuck >6h, check loop health. |
| **B1** | `triage.source_gap_list` → INSUFFICIENT_DATA stocks with diagnoses | Source concall transcripts; re-run `run_research.py <SYM>`; re-score; or override B1. |
| **B2 / B3** | `triage.longs` / `triage.shorts` + sector breakdown | Expand `config/fno_stocks.json`; loosen grading (spec amendment); or override B2/B3. |
| **B4** | `golden_set.phase1_reference.per_stock` → find the drifted reference stocks | Investigate extraction regression; diff against prior manifest's B4 block; **never override without root cause.** |
| **B5** | `triage.retry_queue` + `logs/batch_trust*.log` common error pattern | Likely Gemini API outage or prompt break. Fix upstream, re-run. |
| **B6** | `sanity_failures_<timestamp>.csv` + `sanity_rules.per_rule_fails` | If one rule dominates, fix that rule's upstream cause (prompt or scorer enum). |
| **B7** | `triage.retry_queue` entries with `retry_count >= 3` | Manually rescore the stocks listed, OR mark them `NOT_IN_UNIVERSE` if legitimately broken. |
| **B8** | `triage.source_gap_list` entries with `diagnosis == "unknown"` | Classify each into a valid diagnosis from §5.5 manually; update `trust_score.json`; re-run gate. |

3. Choose: **fix and re-run** OR **override** via `--override-criterion B<N> --reason "<full sentence>"`.

**Override discipline — reason validation (CLI layer, exit 64 on failure):**

- Minimum length: 40 characters
- Must be a complete sentence (contains at least one `[.!?]`)
- Must NOT match known cop-out regexes: `^(ok|fine|temporary|for now|bharat said|approved|confirmed)$`, `^.{0,15}$`
- Must contain either a date (matches `\d{4}-\d{2}-\d{2}` or `FY2\d`) OR a ticket/issue reference (matches `#\d+` or `TD\d+`)

**Override audit loop:** within 24 hours of any PASS_WITH_OVERRIDES run, operator must append to `docs/stage1_gate/overrides_log.md` describing whether the override was *vindicated* (did the ignored failure actually matter?). This is the closed-loop check.

**3-consecutive-run rule:** if `delta_vs_last_run.overrides_added` contains the same criterion ID on 3+ consecutive runs, escalate to "threshold needs adjustment" spec discussion. Don't normalize overrides.

#### PASS_WITH_OVERRIDES (exit 0, ORANGE alert)

1. Stage 2 is unblocked and starts automatically.
2. Operator receives ORANGE alert — purely for audit.
3. Within 24h: file the 24h audit note (see above).
4. Watch for the 3-consecutive-run escalation trigger.

#### PASS_WITH_WARNINGS (exit 0, YELLOW alert if new)

1. Stage 2 unblocked.
2. If YELLOW fired, skim the new warnings. They're informational but trend-watched.
3. No required action, but `delta_vs_last_run.warnings_added` should be reviewed weekly.

#### PASS (exit 0, silent)

No action. This is the steady state.

#### PRE_CONDITION_FAILED (exit 2)

No operator action. `run_batch_loop.py` keeps scoring and re-invokes the gate on the next cycle (default 30 min). If this state persists >6 hours, a separate watchdog alert fires on the batch loop itself (not a gate alert). If the persistence is due to a single stuck stock, investigate via `logs/batch_trust*.log`.

#### Internal gate error (exit 70)

1. Read the Telegram alert's stack trace.
2. Fix the gate bug, re-run manually.
3. If the bug left `artifacts/stage1_gate/manifest.json` corrupt: the atomic write guarantee means the corrupt file was never committed, so the previous canonical manifest is intact. If somehow corruption did occur, copy `artifacts/stage1_gate/history/<most-recent-valid>.json` back to `manifest.json` and re-run.
4. Add a regression test to `tests/stage1_gate/test_gate_integration.py` reproducing the failure.

#### CLI usage error (exit 64)

1. Read the Telegram alert's error line.
2. Fix the invocation (usually a missing `--reason` or unknown criterion ID).
3. Re-run.

### 7.4 Integration with `run_batch_loop.py`

The gate slots into `run_batch_loop.py` as a new sentinel between scoring and portfolio construction:

```python
# Pseudocode — reality is a few more lines for logging and telegram calls.
import os, subprocess

GATE_ENABLED = os.environ.get("STAGE1_GATE_ENABLED") == "1"

while True:
    run_batch_scoring_pass()

    if not GATE_ENABLED:
        # Pre-gate rollout: proceed directly to portfolio construction.
        log("Stage1 gate disabled via STAGE1_GATE_ENABLED flag; running portfolio build.")
        run_model_portfolio()
        break

    gate_result = subprocess.run(
        ["python", "run_stage1_gate.py"],
        capture_output=True, text=True,
    )
    exit_code = gate_result.returncode

    if exit_code == 0:
        log("Stage 1 gate PASSED; triggering Stage 2.")
        run_ultraplan()            # drafts portfolio plan from manifest
        run_model_portfolio()      # executes construction
        break
    elif exit_code == 1:
        send_telegram_alert("RED", gate_result.stdout[:3500])
        log("Stage 1 gate FAILED; halting batch loop for operator.")
        break
    elif exit_code == 2:
        log("Gate reports pre-condition not met; continuing scoring.")
        continue
    elif exit_code in (64, 70):
        send_telegram_alert("RED", f"Gate script error (exit {exit_code})\n{gate_result.stderr[:3000]}")
        log(f"Gate script error exit={exit_code}; halting.")
        break
    else:
        log(f"Unexpected gate exit code {exit_code}; halting.")
        send_telegram_alert("RED", f"Unexpected gate exit code {exit_code}")
        break
```

**Key properties:**

- Batch loop never silently ignores a gate result.
- Pre-condition failure is the **only** "keep going" case.
- All other non-zero codes halt and alert.
- Stage 2 is two consumers in order: `/ultraplan` drafts, `run_model_portfolio.py` executes. Both call `scripts/verify_manifest.py` before reading. The gate is agnostic to their internal ordering.

### 7.5 Rollout plan — `STAGE1_GATE_ENABLED` feature flag

The gate is net-new code touching the batch loop. To protect the existing pipeline during first-run exposure, the gate ships behind a feature flag.

**Default:** `STAGE1_GATE_ENABLED` unset → flag is off → batch loop proceeds directly to portfolio construction (pre-gate behavior).

**Rollout is a 3-cycle validation sequence.** Each cycle has a specific purpose; the operator must manually complete all three before flipping the default to on.

| Cycle | Purpose | Operator actions | Success criteria |
|---|---|---|---|
| **Cycle 1** | First-run validation | Manually invoke `python run_stage1_gate.py`; read the manifest end-to-end; verify every field matches §6 schema; verify `gate_state` is sensible; verify exit code is 0/1/2 as expected | Manifest looks right; operator can interpret every field without asking |
| **Cycle 2** | Idempotency + determinism | Re-run the gate immediately (within the same batch-progress snapshot); `diff manifest.json history/manifest_<prev>.json` | Diff is empty except for `generated_at` and `content_hash` (which depends on `generated_at`). This validates Section 1 invariant #2. |
| **Cycle 3** | Delta sanity | Let one full batch cycle run, then invoke the gate twice with known-good grades between invocations; inspect `delta_vs_last_run` | `delta_vs_last_run` reports the expected grade changes; `universe_delta` is empty; `warnings_added` / `warnings_cleared` match operator expectation |

**After all 3 cycles pass:** flip the default to `STAGE1_GATE_ENABLED=1` in `run_batch_loop.py` (or set it in the environment file). Document the flip date in `docs/stage1_gate/rollout_log.md`.

**Rollback:** if any cycle reveals a problem, leave the flag unset, fix the issue, restart the cycle sequence from Cycle 1.

**Rationale (slow-and-correct mandate):** the gate is a measurement tool. Measurement tools must themselves be validated before they become authoritative. The 3-cycle sequence validates: (1) correctness under a single run, (2) determinism across runs, (3) correctness of state transitions between runs. A single bad commit to the gate cannot take down the whole morning pipeline while the flag is off.

### 7.6 Logging — `logs/stage1_gate.log`

Single append-only JSON-lines log. One line per gate invocation:

```json
{
  "ts": "2026-04-10T22:15:03+05:30",
  "run_id": "20260410T221503",
  "gate_state": "PASS_WITH_OVERRIDES",
  "exit_code": 0,
  "blocking_failed": ["B1"],
  "overrides_applied": [
    {"id": "B1", "operator": "bharat", "reason_hash": "sha256:9c2e1d..."}
  ],
  "warning_ids": ["W4"],
  "manifest_path": "artifacts/stage1_gate/manifest.json",
  "manifest_hash": "sha256:a3f5b9c7...",
  "duration_ms": 842
}
```

**Not written to the log:**

- The full manifest (already on disk)
- Raw override reason text (only `reason_hash` — full reason lives in the manifest + `overrides_log.md`)

The log is the audit stream; the manifest is the artifact.

### 7.7 Testing strategy

Unit + integration tests live in `tests/stage1_gate/`. Fixtures in `tests/stage1_gate/fixtures/` are synthetic minimal artifacts for 10 fake stocks covering every terminal state from §5.3.

| Test file | Covers |
|---|---|
| `test_golden_set.py` | Phase 1 regression fixtures (passing, drifting, missing reference); `reference_set_size < 5` deactivation path (W6); manual spot-check freshness + verdict; criteria_version mismatch (W7) |
| `test_sanity_rules.py` | Each S1–S9 rule with passing + failing fixture items; per-stock aggregation; vague-phrases config reload |
| `test_triage.py` | State machine routing; diagnosis enum validation; `DIAGNOSIS_REMEDIATIONS` lookup; pre-triage NOT_IN_UNIVERSE filtering |
| `test_criteria.py` | B0–B8, W1, W3–W7; severity-tiered evaluation; override acceptance; deactivated-criteria contract (§2.5); reason validator |
| `test_manifest.py` | Schema round-trip; atomic temp-rename write; summary three-way universe accounting; pointer resolution |
| `test_manifest_verifier.py` | Hash canonicalization (key ordering, separators, Unicode); tamper detection round-trip; exit codes 0/1 |
| `test_delta.py` | `universe_delta` first-run case; `delta_vs_last_run` grade / criteria / warning / override diffs; empty-history case |
| `test_gate_integration.py` | End-to-end with synthetic fixtures reaching all 5 exit codes (0/1/2/64/70); Telegram mock; batch_loop integration pseudocode smoke test |

**Minimum acceptance for v1 ship:**

- 100% of tests above green on CI
- `test_gate_integration.py` reaches all 5 exit codes (not just 0)
- `test_manifest_verifier.py` round-trips at least 3 different manifests and detects at least 3 different tamper modes (field add, field modify, field remove)

### 7.8 Documentation artifacts

| File | Purpose |
|---|---|
| `docs/superpowers/specs/2026-04-10-stage1-closeout-gate-design.md` | **This document.** Canonical spec. |
| `docs/stage1_gate/runbook.md` | One-page operator reference: exit codes, alert tiers, diagnostic quick-reference. Linked from CLAUDE.md. |
| `docs/stage1_gate/overrides_log.md` | Append-only audit log of override reasons + 24h vindication notes. Edited by operator. |
| `docs/stage1_gate/rollout_log.md` | Rollout cycle completion log (§7.5). Edited by operator. |

### 7.9 Scope fence — what the gate does NOT do

Explicitly out of scope for this design. These belong to other Stage 2 components or future work.

1. **Building the portfolio.** That's `run_model_portfolio.py`.
2. **Running the LLM.** The gate is pure-Python validation over cached artifacts.
3. **Deciding when to rescore.** That's `run_batch_loop.py` and the scheduler.
4. **Sourcing new data.** Diagnosis codes point to remediation paths; the gate never fetches.
5. **Drafting Stage 2 plans.** That's `/ultraplan`, which consumes the manifest.
6. **Modifying batch state.** Read-only invariant (§1.6).
7. **Sector concentration enforcement.** Belongs to `run_model_portfolio.py` (§5.7).
8. **Displaying a dashboard.** Manifest + Telegram + runbook are the operator surface. No HTML, no Grafana, no email.

---

## Appendix A — Locked design decisions

These decisions are baked into the spec and cannot change without a spec amendment and `criteria_version` bump.

### A.1 Architecture invariants

1. Gate is read-only with respect to batch state (§1.6)
2. Gate is idempotent (§1.6, validated in rollout Cycle 2)
3. Gate is deterministic — zero LLM calls inside the gate (§1.6)
4. Gate fails closed on internal errors — prior manifest survives exit 70 (§6.13)
5. Manifest writes are atomic via temp-rename (§6.13)

### A.2 Criterion definitions and thresholds

6. B1 = `>= 100` letter-graded stocks (operator locked)
7. B2 = B3 = `>= 8` per bucket (operator locked)
8. B4 = `band_distance <= 1` across 100% of reference set; prerequisite `reference_set_size >= 5`
9. B5 = `< 0.15` scoring failure rate
10. B6 = `>= 0.95` sanity-rule pass rate (per-item granularity)
11. B7 = `retry_count >= 3 count == 0`
12. B8 = `diagnosis == "unknown" count == 0` (replaces retired W2)
13. W1 = `<= 8` early-warning scoring failures (fires before B5)
14. W3 = max grade share `< 60%` (operator locked)
15. W4 = `<= 7 days` freshness + `reviewer_verdict == "pass"`
16. W5 = `<= 5` collection failures
17. W6 = reference set `>= 5` informational (fires when B4 is deactivated)
18. W7 = exact match on `criteria_version` between gate and manual_curated.json

### A.3 Data model

19. 5-value `gate_state` enum: `PASS`, `PASS_WITH_WARNINGS`, `PASS_WITH_OVERRIDES`, `FAIL`, `PRE_CONDITION_FAILED`
20. 5-value exit code set: `0`, `1`, `2`, `64`, `70` — no others permitted
21. Three-way universe accounting: `universe_enumerated`, `universe_active`, `stocks_not_in_universe`; **all denominators use `universe_active`**
22. NOT_IN_UNIVERSE stocks are filtered **before** the triage tree runs (§5.1)
23. Deactivated criteria shape: `passed: true, skipped: true, skip_reason, prerequisite_met: false` (§2.5)
24. 6-value INSUFFICIENT_DATA diagnosis enum (§5.5); `unknown` is a sentinel that fails B8
25. Overrides do NOT persist across runs — re-specification required
26. Override reasons must pass the 4-rule validator (length, sentence, no cop-outs, date/ticket reference)
27. W2 is **retired** — slot reserved, do not reuse
28. `criteria_version` mismatch between compiled constants and spec version → gate refuses to run
29. `criteria_version` mismatch between gate and `manual_curated.json` → W7 fires

### A.4 Manifest shape

30. Two-tier design: verdict and aggregates inline; Tier 2 reached via `pointers`
31. Canonical latest at `artifacts/stage1_gate/manifest.json`; archived at `artifacts/stage1_gate/history/manifest_<ISO8601>.json`
32. `tech_debt.json` is a separate file, inlined at build time
33. `sanity_failures_<timestamp>.csv` is NOT inlined (size concerns)
34. `content_hash` is mandatory, top-level, sha256 over canonical JSON of all other fields
35. Stage 2 consumers MUST call `scripts/verify_manifest.py` before reading the manifest
36. Every criterion entry has `name`, `passed`, typically `expected` + `actual`
37. `universe_delta` and `delta_vs_last_run` are **distinct** top-level fields with different semantics (§6.7 vs §6.8)
38. `manual_spot_check` block inlines `review_session_id` and `notes` for audit

### A.5 Operator workflow

39. Override CLI flag is `--override-criterion B<N> --reason "<sentence>"` (canonical)
40. Invocation is `python run_stage1_gate.py` (canonical, not `-m` form)
41. `STAGE1_GATE_ENABLED` feature flag gates the `run_batch_loop.py` integration
42. Rollout is a 3-cycle manual validation before default-on flip (§7.5)
43. ORANGE alerts require a 24h vindication note in `docs/stage1_gate/overrides_log.md`
44. 3 consecutive runs overriding the same criterion → spec amendment discussion
45. Telegram alerts use existing `pipeline/notifications/telegram.py` (no new infra)
46. `PRE_CONDITION_FAILED` (exit 2) is NOT Telegram-alerted — batch-log only
47. YELLOW alert fires only on *new* warnings via `delta_vs_last_run.warnings_added`
48. GREEN alert is opt-in (`--notify-on-pass`)

---

## Appendix B — Drift reconciliation log

Every drift caught in the §(section-wide consistency review) pass is recorded here with its canonical resolution. This is the audit trail between the 7 brainstorm sections and this consolidated spec.

| # | Severity | Drift | Canonical resolution (applied in spec) |
|---|---|---|---|
| D1 | BLOCKING | S2 only defined B1–B6, W1–W5; S6 silently used B0–B8 + W1/W3–W6 with W2 retired | Spec §2 lists full B0–B8, W1/W3–W7 (W7 added per D9); W2 slot reserved and marked retired |
| D2 | BLOCKING | In-session new S7.3 runbook mislabeled B5 as sanity, B6 as tech_debt (no tech_debt criterion exists) | Spec §7.3 uses correct labels: B5=scoring_failure_rate, B6=sanity_rule_pass_rate; tech_debt is a manifest field only |
| D3 | BLOCKING | S2 W2 enum (`no_ar_pdfs`, `corrupt_pdfs`, `no_numeric_guidance`, `sector_prompt_mismatch`, `insufficient_years`) mismatched S5 enum (6 values, no `no_ar_pdfs`, adds `extraction_returned_empty`, `unknown`) | Spec §5.5 uses the 6-value S5 enum, scoped to B8 not W2; `no_ar_pdfs` correctly routes to RE_DOWNLOAD_QUEUE (different terminal state) |
| D4 | BLOCKING | S1 said `"exit 2 = warning only"` which contradicts S7 (exit 2 = PRE_CONDITION_FAILED) | Spec §1.7 defers to §7.1 for the full 5-value exit code set; S1 corrected |
| D5 | BLOCKING | `gate_state` enum introduced in S6 but never mentioned in §1–§5 | Spec §1.5 data-flow diagram now names the 5 gate_states as the terminal node; §1.7 cross-references §6.2.1 |
| D6 | UNDEFINED | `universe_delta` subfields never specified in any section | Spec §6.7 defines 6-field shape: `added_since_last_gate`, `removed_since_last_gate`, `newly_not_in_universe`, `previous_manifest_ref`, `previous_universe_active`, `current_universe_active` |
| D7 | UNDEFINED | `delta_vs_last_run` also undefined, and distinct from `universe_delta` | Spec §6.8 defines 8-field shape: previous/current gate_state, grade_changes, criteria_flips, warnings_added/cleared, overrides_added/cleared |
| D8 | UNDEFINED | `overrides` array shape not shown | Spec §6.9 defines 6-field shape: criterion_id, operator, reason, reason_hash, applied_at, original_failure |
| D9 | UNDEFINED | `criteria_version` mismatch between gate and manual_curated.json had no detector | Spec adds **W7** `criteria_version_mismatch` as a new warning (independently toggleable, different concern from W4 freshness) |
| D10 | CLEANUP | S1 package layout missing external dep `pipeline/notifications/telegram.py` | Spec §1.4 adds "Dependencies (external)" table listing telegram.py, verify_manifest.py, config files |
| D11 | — | Folded into D4 | — |
| D12 | CLEANUP | Override flag name drift (`--override-criterion` vs `--override`) | Spec locks on `--override-criterion B<N> --reason "..."` (explicit; allows future `--override-warning`) |
| D13 | CLEANUP | Gate invocation path drift (`python -m pipeline.stage1_gate.run` vs `python run_stage1_gate.py`) | Spec locks on `python run_stage1_gate.py` everywhere |
| D14 | CLEANUP | S6 summary example used `active_universe_size: 213` (superseded by Addendum C) | Spec §6.3 writes the three-way accounting shape directly; no Addendum reference needed |
| D15 | CLEANUP | Addendum A note: *"Added to the tech_debt.json list NOT needed since the feature lands immediately"* (word salad) | Spec §6.4 rewords: verify_manifest.py ships with v1, no tech_debt entry needed |
| D16 | CLEANUP | Exit 64/70 manifest-write status was implied but never stated | Spec §6.2.1 and §7.1 explicitly state: exit 64/70 do NOT write a manifest; prior canonical manifest remains untouched |
| D17 | CLEANUP | Stage 2 consumer ambiguity (`/ultraplan` vs `run_model_portfolio.py`) | Spec §7.4 locks: `/ultraplan` drafts, `run_model_portfolio.py` executes; both verify hash before reading |
| D18 | NEW DECISION | `STAGE1_GATE_ENABLED` env flag proposed in in-session S7, not in prior sections | Spec §7.5 keeps the flag with a 3-cycle rollout plan |
| D19 | CLEANUP | `history/` read for YELLOW new-warning detection was not in §1 data flow | Spec §1.5 data flow adds an arrow from `history/` into `delta.py`; §7.2 references `delta_vs_last_run.warnings_added` directly |
| D20 | BLOCKING | `NOT_IN_UNIVERSE` used in Addendum C but not a triage state in S5 | Spec §5.1 adds "Pre-triage filtering" subsection; NOT_IN_UNIVERSE stocks never enter the triage tree |
| D21 | CLEANUP | Deactivated-criterion contract was only in Addendum B; S2 criteria didn't reference it | Spec §2.5 incorporates the contract as a universal rule for any criterion with a prerequisite |
| D22 | CLEANUP | Test layout missed `test_manifest_verifier.py` for verify_manifest.py | Spec §7.7 adds the test file with minimum acceptance criteria |
| D23 | CLEANUP | S3 `manual_curated.json` fields `review_session_id` and `notes` were dropped from S6 `manual_spot_check` block | Spec §6.6 inlines both fields in the manifest block |
| D24 | CLEANUP | W1 threshold drifted between S2 (`<= 15`) and S6 example (`<= 8`) | Spec §2.3 locks W1 at `<= 8` as an early warning that fires *before* B5; rationale: ~5 is noise, 8+ is systemic |

---

## Appendix C — Implementation checklist

Build order. Each step has verification criteria. Do not advance until the previous step is green.

### C.1 Foundation

- [ ] **C.1.1** Create `pipeline/stage1_gate/` package with empty modules (`__init__.py`, `gate.py`, `criteria.py`, `golden_set.py`, `sanity_rules.py`, `triage.py`, `manifest.py`, `delta.py`, `history.py`)
- [ ] **C.1.2** Create `scripts/verify_manifest.py` (hash computation + verification CLI)
- [ ] **C.1.3** Create `tests/stage1_gate/` with empty test files and `fixtures/` directory
- [ ] **C.1.4** Create `config/not_in_universe.json` (initially empty list)
- [ ] **C.1.5** Create `config/vague_phrases.json` with the initial phrase list from §4.2
- [ ] **C.1.6** Create `artifacts/stage1_gate/` directory; create empty `tech_debt.json` as `[]`
- [ ] **C.1.7** Create `docs/stage1_gate/` with empty `runbook.md`, `overrides_log.md`, `rollout_log.md`

**Verification:** `python -c "import pipeline.stage1_gate"` succeeds; directory tree matches §1.3.

### C.2 Criterion registry and deactivated-criterion contract

- [ ] **C.2.1** Implement `criteria.py` with `Criterion` dataclass: `id, name, severity, threshold, prerequisite, evaluate_fn`
- [ ] **C.2.2** Implement severity enum (`BLOCKING`, `WARNING`) and deactivated-criterion serialization from §2.5
- [ ] **C.2.3** Register B0–B8, W1, W3–W7 with threshold constants per §2.4
- [ ] **C.2.4** Implement `CRITERIA_VERSION = "1.0"` constant; add refusal check if spec version mismatches
- [ ] **C.2.5** Write `test_criteria.py` — unit tests for each criterion (passing + failing + deactivated where applicable)

**Verification:** `pytest tests/stage1_gate/test_criteria.py` green; fixtures exercise every criterion's pass/fail/skip paths.

### C.3 Sanity rules

- [ ] **C.3.1** Implement S1–S9 in `sanity_rules.py` as pure functions
- [ ] **C.3.2** Load `config/vague_phrases.json` at startup; compile regexes once
- [ ] **C.3.3** Implement B6 aggregation function (per-item granularity)
- [ ] **C.3.4** Write `test_sanity_rules.py` — passing + failing fixture items for each rule

**Verification:** `pytest tests/stage1_gate/test_sanity_rules.py` green; vague-phrases config can be reloaded without code change.

### C.4 Triage tree

- [ ] **C.4.1** Implement `triage.py` state machine per §5.2
- [ ] **C.4.2** Implement pre-triage NOT_IN_UNIVERSE filtering per §5.1
- [ ] **C.4.3** Implement `DIAGNOSIS_REMEDIATIONS` lookup; validate enum per §5.5
- [ ] **C.4.4** Implement B2/B3 minimum-bucket enforcement
- [ ] **C.4.5** Write `test_triage.py` — every terminal state + diagnosis enum + NOT_IN_UNIVERSE filtering

**Verification:** `pytest tests/stage1_gate/test_triage.py` green; 10-stock synthetic fixture exercises every terminal state.

### C.5 Golden set

- [ ] **C.5.1** Implement `golden_set.py::run_phase1_regression`
- [ ] **C.5.2** Implement `golden_set.py::run_manual_spot_check` (including W7 criteria_version check)
- [ ] **C.5.3** Write `scripts/build_phase1_reference.py` discovery script
- [ ] **C.5.4** Run discovery against opus-anka git history; commit `golden_set/phase1_reference/*.json`
- [ ] **C.5.5** Create initial `golden_set/manual_curated.json` with the 10-stock set from §3.2
- [ ] **C.5.6** Write `test_golden_set.py` — regression, deactivation, spot-check freshness, W7

**Verification:** Discovery finds `>= 5` reference stocks (or W6 is acknowledged); `pytest tests/stage1_gate/test_golden_set.py` green.

### C.6 Manifest schema and delta

- [ ] **C.6.1** Implement `manifest.py::compute_manifest_hash` per §6.4 (deterministic canonical JSON)
- [ ] **C.6.2** Implement `manifest.py::write_manifest_atomic` per §6.13
- [ ] **C.6.3** Implement `delta.py::compute_universe_delta` per §6.7 (handles first-run empty case)
- [ ] **C.6.4** Implement `delta.py::compute_delta_vs_last_run` per §6.8
- [ ] **C.6.5** Implement `history.py::find_most_recent_manifest` and `find_most_recent_pass_manifest` (the latter for YELLOW detection)
- [ ] **C.6.6** Implement `scripts/verify_manifest.py` — recomputes hash, exit 0/1
- [ ] **C.6.7** Write `test_manifest.py`, `test_manifest_verifier.py`, `test_delta.py`

**Verification:** Hash is deterministic under reordered input dicts; tamper detection catches field add/modify/remove; empty-history case handled in delta.

### C.7 Orchestrator

- [ ] **C.7.1** Implement `gate.py::run_gate` that wires together: enumerate → filter → triage → evaluate criteria → build manifest → write atomically
- [ ] **C.7.2** Implement exit-code mapping from `gate_state` to exit code per §7.1
- [ ] **C.7.3** Implement `run_stage1_gate.py` CLI wrapper; handle `--dry-run`, `--override-criterion`, `--reason`, `--notify-on-pass`
- [ ] **C.7.4** Implement override reason validator (4 rules per §7.3); exit 64 on failure
- [ ] **C.7.5** Wrap `run_gate` in a top-level exception handler; exit 70 on uncaught exceptions; write stack trace to `logs/stage1_gate.log` but NOT to manifest
- [ ] **C.7.6** Write `test_gate_integration.py` — fixtures reach all 5 exit codes

**Verification:** All 5 exit codes reachable; `--dry-run` does not touch canonical manifest; override validator rejects all 4 cop-out patterns.

### C.8 Alerting and logging

- [ ] **C.8.1** Implement alert dispatch in `gate.py`: gate_state → Telegram tier mapping per §7.2
- [ ] **C.8.2** Implement new-warning detection via `delta_vs_last_run.warnings_added`
- [ ] **C.8.3** Implement `logs/stage1_gate.log` JSON-lines append per §7.6
- [ ] **C.8.4** Mock Telegram in tests; verify every alert tier is reachable

**Verification:** Telegram mock receives exactly one alert per non-silent state; PRE_CONDITION_FAILED does not alert; GREEN not alerted unless `--notify-on-pass`.

### C.9 Integration with batch loop

- [ ] **C.9.1** Add `STAGE1_GATE_ENABLED` env check to `run_batch_loop.py`
- [ ] **C.9.2** Add gate invocation + exit-code handling per §7.4
- [ ] **C.9.3** Smoke test: flag off → existing behavior; flag on → gate is invoked
- [ ] **C.9.4** Document the flag in CLAUDE.md

**Verification:** Flag off matches pre-gate behavior byte-for-byte; flag on invokes gate and routes by exit code.

### C.10 Rollout (§7.5)

- [ ] **C.10.1** **Rollout Cycle 1** — manual invocation, field-by-field manifest review; log outcome in `rollout_log.md`
- [ ] **C.10.2** **Rollout Cycle 2** — immediate re-run; diff against Cycle 1 manifest; confirm only `generated_at`/`content_hash` differ
- [ ] **C.10.3** **Rollout Cycle 3** — full batch cycle + two gate invocations with known-good grade changes; inspect `delta_vs_last_run`
- [ ] **C.10.4** Flip `STAGE1_GATE_ENABLED` default to `"1"`; log flip date in `rollout_log.md`

**Verification:** All 3 cycles complete with operator sign-off; default flipped; subsequent batch runs invoke the gate by default.

### C.11 Documentation

- [ ] **C.11.1** Write `docs/stage1_gate/runbook.md` — one-page quick reference (exit codes, alert tiers, diagnostic trail)
- [ ] **C.11.2** Link runbook from `CLAUDE.md`
- [ ] **C.11.3** Confirm this spec document is committed and linked from `CLAUDE.md`

**Verification:** `CLAUDE.md` has a "Stage 1 Gate" section with links to spec + runbook.

---

**End of spec.**

Implementation can begin at C.1 once this document is approved.
