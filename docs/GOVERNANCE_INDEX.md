# Anka Governance Index

> **Purpose:** single map of every policy, standard, gate, and enforcement mechanism in the Anka research system. Read this before LIVE cutover to know what's protecting you and where the gaps are.

**Last updated:** 2026-04-30

---

## How to read this

For each governance domain:
- **Policy** — the written rule (where it lives)
- **Enforcement** — the mechanism that actually stops violations (pre-commit hook, CI, runtime gate, manual review)
- **Status** — does enforcement exist or is the policy aspirational?
- **Gap** — what's missing before LIVE cutover

A policy without enforcement is decoration. A policy with enforcement is governance.

---

## 1. Data governance

**Policy:** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` (26 sections)

**What it covers:** dataset registration, schema contracts, cleanliness gates, adjustment-mode declarations, point-in-time correctness, contamination maps. §21 binds dataset acceptance to the model approval ladder.

**Enforcement:**
- ✅ `CLAUDE.md` Data Validation Gate clause — every backtest must cite a registered dataset
- ✅ `docs/DATA_INVENTORY.md` — single registry of accepted datasets
- ✅ Dataset audit docs at `docs/superpowers/specs/<date>-<dataset>-data-source-audit.md`
- ⚠️ No automated check that a backtest's input dataset is in the inventory — relies on author honesty

**Gap to close before LIVE:** add a runtime assertion in the backtest harness that asserts every input dataset path appears in `DATA_INVENTORY.md`.

---

## 2. Backtesting standards

**Policy:** `docs/superpowers/specs/anka_backtesting_policy_global_standard.md` (a.k.a. `backtesting-specs.txt`, 16 sections + deployment gate ladder)

**What it covers:** §0 prerequisites, §9 pass criteria, §9A Fragility, §9B Margin, §10.1 MaxDD, §10.4 Single-touch holdout, §11 contamination tests, deployment gate ladder.

**Enforcement:**
- ✅ Hypothesis registry at `docs/superpowers/hypothesis-registry.jsonl` — every named strategy registered
- ✅ Pre-commit hook `pipeline/scripts/hooks/pre-commit-strategy-gate.sh` blocks new `*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py` without a registry entry
- ✅ CI: `.github/workflows/strategy-gate.yml` enforces the same regex on PRs
- ✅ Pattern file `pipeline/scripts/hooks/strategy_patterns.txt` — single source of truth for the regex
- ⚠️ §10.4 single-touch holdout enforced by *human* discipline (no parameter changes mid-window) — no machine check
- ⚠️ §9A Fragility / §9B Margin enforced by manual verdict reading — no automated kill-switch on FAIL

**Gap to close before LIVE:** verdict files (`<hypothesis>_verdict.json`) should programmatically flip a `production: false` flag on §9A/§9B FAIL; the live engine should refuse to load any hypothesis whose verdict file says `production: false`.

---

## 3. Code governance

**Policy:** **NONE WRITTEN.** No `anka_code_governance_policy_global_standard.md` exists.

**What is missing:**
- Standards for retesting code when refactored (full test rerun? changed-files only?)
- Definition of "production" code path vs research/exploratory
- Required documentation level per file type
- Code review policy — who must review what, before what milestones
- Sign-off requirement before a research script gets promoted to scheduled task

**Current ad-hoc enforcement:**
- ✅ `pipeline/tests/` exists with ~280 tests, run on demand
- ✅ Pre-commit strategy gate (above) catches new strategy files
- ⚠️ No CI enforces full test pass on PR
- ⚠️ No "promotion gate" between research code and scheduled-task code

**Gap to close before LIVE:** write `anka_code_governance_policy_global_standard.md` covering the items above. Add CI workflow that runs `pytest pipeline/tests/` on every PR. Add a "promotion-to-production" checklist that gates moving a script into `pipeline/config/anka_inventory.json`.

---

## 4. Model governance

**Policy:** Implicit in `anka_backtesting_policy_global_standard.md` §21 + the deployment gate ladder, but no standalone document.

**What partial enforcement exists:**
- ✅ Hypothesis registry tracks each model spec
- ✅ Verdict files `*_verdict.json` capture pass/fail per gate
- ⚠️ Model versioning has no policy — when does v1 → v2 require a new spec? No rule.
- ⚠️ Frozen-weights policy implicit per backtesting-specs §10.4 but not documented as a standalone "models, frozen, are immutable post-registration" rule
- ⚠️ Deprecation discipline (when to retire a passed model) not specified

**Gap to close before LIVE:** write `anka_model_governance_policy_global_standard.md`. Define versioning, retirement criteria, audit trail of weight changes, and what triggers re-validation.

---

## 5. Anti-hallucination guardrails

**Policy:** **PARTIAL.** `CLAUDE.md` says "no hallucination mandate, slow and correct beats fast and wrong" and references `feedback_no_hallucination_mandate.md`.

**What enforcement exists:**
- ✅ Pre-commit strategy gate forces hypothesis registration (catches "new strategy file invented out of thin air")
- ✅ `feedback_data_validation_mandate.md` — every number must pass through `data_validator` before publication
- ✅ Verdict-reading discipline catches fabricated wins (any reported win rate must come from a verdict.json, not narrative)
- ⚠️ No automated check that a number cited in an article / Telegram message originates from a registered ledger
- ⚠️ No automated check that LLM-generated text doesn't claim numbers absent from source
- ⚠️ Trust-score-from-LLM hallucinated content depends on the LLM's prompt-following — no post-hoc grounding check

**Gap to close before LIVE:** add a "number-grounding" pre-publication check: any % cited in subscriber-facing output must be traced to a specific row in a registered ledger. The Gemma 4 pilot's `eod_narrative` rubric already includes a number-grounding heuristic — generalize that into a system-wide policy.

---

## 6. Calendar / market-day correctness

**Policy:** **NONE WRITTEN.** This bit us 2026-04-29 — the mechanical replay engine fired Phase C signals on 5 NSE holidays (Holi, Eid, Mahavir Jayanti, Ambedkar Jayanti) because `pd.bdate_range()` excludes weekends but not holidays.

**What partial enforcement exists:**
- ✅ `pipeline/data/trading_calendar.json` exists
- ✅ Live engines (run_signals, break_signal_generator, arcbe_signal_generator) have 14:30 cutoff guards
- ⚠️ `pipeline/autoresearch/mechanical_replay/phase_c.py:77` does NOT consult the calendar — uses `pd.bdate_range()` blindly
- ⚠️ No test asserts "no engine fires signals on holidays"

**Gap to close before LIVE:** write a "trading-calendar correctness" policy. Patch `phase_c.py:77` and any other replay engine to consult `trading_calendar.json`. Add a test that replays a known holiday (2026-03-03 Holi) and asserts zero signals fire.

---

## 7. Research-report governance

**Policy:** **PARTIAL.** Hypothesis specs land at `docs/superpowers/specs/<date>-<topic>-design.md` per the brainstorming skill; verdicts land at `<topic>-verdict.json`. Memory files capture state. But there's no policy on:
- Required content of a research report
- Peer-review requirement before claiming a result
- Snapshot of input data alongside the report (reproducibility)

**Gap to close before LIVE:** write `anka_research_report_policy_global_standard.md`. Each major hypothesis verdict must have:
1. Spec doc (registered at hypothesis time)
2. Frozen input-data snapshot (e.g., parquet hash + commit SHA)
3. Verdict JSON (auto-generated)
4. Peer-review sign-off — currently no second pair of eyes; add a "reviewed-by" field that requires manual entry before the verdict can be cited as evidence

---

## 8. Live-trading kill-switches

**Policy:** Implicit in CLAUDE.md "14:30 IST signal cutoff" and `feedback_website_trade_publish_blocked.md`.

**What enforcement exists:**
- ✅ 14:30 cutoff at source in `run_signals.py`, `break_signal_generator.py`, `arcbe_signal_generator.py`
- ✅ Public site shows no trades / positions / track record (manual block since 2026-04-26)
- ⚠️ No documented "stop all live engines" emergency procedure
- ⚠️ No automatic circuit-breaker on aggregate daily loss

**Gap to close before LIVE:** write a `runbooks/emergency-kill-switch.md`. Document: how to flip `data/live_status.json` to `disabled`, how to disable all `Anka*` schedule tasks in one shell command, who to call.

---

## Summary table — readiness before LIVE cutover

| Domain | Policy doc? | Enforcement? | Verdict |
|---|---|---|---|
| Data governance | ✅ | ⚠️ partial (no auto inv-check) | **needs work** |
| Backtesting standards | ✅ | ✅ pre-commit + CI + registry | **strong** |
| Code governance | ❌ MISSING | ⚠️ ad-hoc | **gap** |
| Model governance | ❌ MISSING | ⚠️ implicit only | **gap** |
| Anti-hallucination | ⚠️ partial | ⚠️ partial | **gap** |
| Calendar correctness | ❌ MISSING | ❌ replay bug live | **gap** |
| Research reports | ⚠️ partial | ❌ no peer-review | **gap** |
| Live kill-switches | ⚠️ implicit | ✅ 14:30 cutoff | **needs runbook** |

**Three policy docs to write before LIVE:**
1. `anka_code_governance_policy_global_standard.md`
2. `anka_model_governance_policy_global_standard.md`
3. `anka_research_report_policy_global_standard.md`

**Three enforcement gaps to close before LIVE:**
1. CI runs full `pytest pipeline/tests/` on PR
2. Replay engine consults `trading_calendar.json`
3. Number-grounding check before subscriber-facing publication

---

## How this document evolves

- Updated when a new policy is written, or a gap is closed.
- Bumped at the top with the new "Last updated" date.
- The summary table is the at-a-glance check — keep it current.
