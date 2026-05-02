# Hermes System-FAQ Skill (Week 1) + Migration Framework — Design

**Date:** 2026-05-02
**Status:** DRAFT — awaiting user review
**Author:** Claude (auto mode) on Bharat's instruction
**Companion docs:**
- Install spec: `docs/superpowers/specs/2026-05-02-hermes-agent-install-design.md`
- Empirical baseline: `docs/research/hermes_baseline/2026-05-02-baseline.md`

## What

Build Hermes' first production-grade skill: a **system-FAQ knowledge agent** that answers in-depth questions about every part of the askanka.com pipeline (architecture, ML methods, operations, active hypotheses, governance standards) by reading the canonical source documents in this repo. The skill is the Week-1 deliverable of the broader Hermes migration program. The grading rubric, report-card format, and acceleration mechanic established here are reusable scaffolding for Weeks 2+.

## Why

Two tightly-coupled drivers (per `project_claude_hermes_split.md`):

1. **Internal:** Bharat asks "what is X" / "how does Y work" frequently. Today those questions cost a Claude turn. A working FAQ skill diverts the routine ones to Hermes (cost = local CPU = $0/token), reserving Claude for novel/architectural questions.
2. **Commercialization (Spec B prerequisite):** A third-party customer running this stack locally needs to understand what they're operating. The FAQ skill **is** the support layer they consume. We cannot ship Spec B (commercialization) until this skill works for our own questions.

The FAQ surface is also the safest possible Week-1 task: internal-only, free-form text generation (Gemma's strongest mode per the baseline), zero subscriber exposure, fully gradeable against source documents. Failure here is a learning moment, not a regression.

## Scope (5 coverage tiers, 30 baseline questions)

The FAQ must answer questions across five tiers. Each tier gets 6 baseline questions (30 total) used for grading. The user's specific emphasis ("every single thing in depth, especially Karpathy and Neural networks") makes Tier 1 the highest-stakes — a hallucinated Karpathy detail given to a customer destroys trust. Tier 1 therefore enforces strict-quote citation (see Grading).

| Tier | Topics | Source documents |
|---|---|---|
| **1 — ML Methods** | Karpathy random search, Lasso L1 regularization, walk-forward CV, BH-FDR multiple-testing correction, Deflated Sharpe, permutation null, qualifier-gate composition | `docs/superpowers/specs/backtesting-specs.txt`, hypothesis specs (`2026-04-29-ta-karpathy-v1-design.md`, `2026-05-01-phase-c-mr-karpathy-v1-design.md`, `2026-04-29-data-driven-intraday-framework-design.md`) |
| **2 — Architecture** | 8-layer Golden Goose pipeline, ETF regime engine (28 ETFs, v3-CURATED-30), OPUS ANKA Trust Scores, Spread Intelligence (5-layer decision engine), Reverse Regime Phase A/B/C, Theme Detector v1 | `CLAUDE.md`, `docs/SYSTEM_OPERATIONS_MANUAL.md`, `memory/project_*` files |
| **3 — Operations** | 80+ scheduled tasks, data-freshness watchdog, 14:30 IST cutoff, kill-switch (strategy_patterns.txt), `anka_inventory.json`, VPS systemd architecture | `CLAUDE.md`, `pipeline/config/anka_inventory.json`, `pipeline/scripts/hooks/strategy_patterns.txt`, `docs/SYSTEM_OPERATIONS_MANUAL.md` |
| **4 — Active Hypotheses** | Every H-2026-* hypothesis — status, holdout window, verdict bar, current ledger size, FAILED reasons | `docs/superpowers/hypothesis-registry.jsonl`, individual H-spec docs in `docs/superpowers/specs/`, `memory/project_*_h_2026_*.md` |
| **5 — Standards** | `backtesting-specs.txt` 16 sections, `anka_data_validation_policy_global_standard.md` 26 sections, `feedback_*` rules, doc-sync mandate | `docs/superpowers/specs/backtesting-specs.txt`, `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`, `memory/feedback_*.md` |

## Architecture (Option A — read-from-repo + curated INDEX)

```
Contabo VPS (anka@185.182.8.107)
├── ~/askanka.com/                  ← NEW (read-only mirror)
│   ├── .git → github.com/<user>/askanka.com
│   ├── CLAUDE.md, docs/, pipeline/, memory/
│   └── docs/faq/INDEX.md           ← NEW (curated topic→source map)
│
├── ~/.hermes/skills/system-faq/    ← NEW (Hermes skill)
│   ├── SKILL.md                    (instructs Hermes how to answer)
│   └── examples/                   (5 worked examples, one per tier)
│
└── ~/hermes-agent/scripts/         ← NEW (runner + grader)
    ├── run_faq_baseline.sh          (runs 30 questions, captures Q+A+citation+latency)
    └── grade_faq_answers.py         (Gemini 2.5 Flash auto-grader)

Repo sync: systemd timer Sunday 04:00 IST → `git -C ~/askanka.com pull --ff-only`
INDEX validation: same timer also runs INDEX-link checker; if any path 404s, alert via Telegram
Report cards: docs/research/hermes_pilot/report_cards/<YYYY-MM-DD>.md (committed to repo)
```

### Question-handling flow

1. Bharat (or runner script) sends question to Hermes via `~/.local/bin/hermes -z '<question>' --skills system-faq`.
2. Hermes loads `system-faq` skill → reads `~/askanka.com/docs/faq/INDEX.md`.
3. Skill rules instruct Hermes to (a) match question keywords against INDEX topic table, (b) read 1–3 source files for the matched topic, (c) compose answer **with required verbatim quote(s) from source**, (d) cite source path:line where each quote begins, (e) end with one-line "Outside FAQ?" disclaimer if no INDEX match.
4. Output is plain text answer; runner script captures it + the cited files + latency to `~/.hermes/data/faq_runs/<YYYY-MM-DD>/<question_id>.json`.
5. Grader script reads the JSONs → calls Gemini 2.5 Flash for each → writes report card MD.

### `INDEX.md` format

```markdown
# askanka.com FAQ Index

For each topic: short description, 1–3 canonical source files, optional section anchor.

## Tier 1 — ML Methods

### Karpathy random search
- One-line: Cell-level pooled random search over hyperparameter grid; pick cell whose
  walk-forward CV Sharpe survives BH-FDR.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md  (definition + qualifier gates)
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md  (failure mode at n=70)
  - docs/superpowers/specs/backtesting-specs.txt  §10.4  (no parameter retries on same registration)

### Lasso L1 regularization
- One-line: L1-penalized logistic regression — sparsity-inducing, picks ~5–10 features
  out of ~60 TA features per stock.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md  (Lasso config + feature list)

### BH-FDR multiple-testing correction
- One-line: Benjamini-Hochberg false-discovery-rate adjustment applied to per-cell p-values.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt  §6  (statistical rigor section)
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md  (concrete failure: 0/448 cells passed)

[... and so on for every topic across all 5 tiers ...]
```

INDEX is hand-authored once for Week 1, then maintained per the existing doc-sync mandate (`feedback_doc_sync_mandate.md`): every code/doc change in the same commit must update INDEX if a new spec/research/hypothesis is added.

### `SKILL.md` format (Hermes skill instructions)

```markdown
---
name: system-faq
description: Answer questions about the askanka.com pipeline — architecture, ML methods,
  operations, active hypotheses, governance — using ONLY content from the local repo
  at ~/askanka.com. Cite source files. Refuse to answer outside indexed scope.
---

# System FAQ

You are the system-FAQ agent for askanka.com. Your job is to answer questions about
the pipeline using ONLY content from `~/askanka.com/`.

## Procedure (must follow exactly)

1. Read `~/askanka.com/docs/faq/INDEX.md`.
2. Match the user's question against INDEX topics. Use keyword and semantic matching.
3. If matched: read 1–3 source files listed for that topic.
4. Compose your answer with these requirements:
   - Begin with a one-sentence direct answer.
   - Then provide depth using **at least one verbatim quote** from a cited source. Format
     each quote as `> "..."` followed by `— <source path>` on the next line.
   - Tier 1 (ML methods) requires AT LEAST TWO verbatim quotes from different sources.
   - End with a "Sources:" section listing every file you read.
5. If no INDEX match: respond with one sentence — "This is outside the current FAQ
   index — escalate to Claude. Suggest adding it to docs/faq/INDEX.md." Do not attempt
   to answer from general knowledge.

## Hard rules

- NEVER state a fact about the system that you cannot back with a verbatim quote from
  a source file in `~/askanka.com/`.
- NEVER use general training-data knowledge to fill gaps. If the source doesn't say it,
  you don't know it.
- NEVER show your reasoning, planning, or self-correction in the final output.
- ALWAYS cite the source path. A relative path like `docs/superpowers/specs/foo.md`
  is acceptable; an absolute path is fine too.
- If multiple source files contradict each other, surface the contradiction explicitly
  and cite both.

## Style

- Direct, technical, no preamble like "Great question!".
- Match the depth of the source. ML-method answers should be detailed; operations
  answers can be one paragraph.
- Plain English over jargon when both work equally well (per
  `feedback_subscriber_language.md`).
```

## Grading rubric (per question)

Each of the 30 baseline questions is graded automatically by **Gemini 2.5 Flash** (the existing primary LLM provider per `reference_llm_providers.md` — same provider used by the Gemma 4 Pilot's pairwise grader, so we reuse infrastructure).

| Dimension | Score | Definition |
|---|---|---|
| **(a) Citation** | 0–1 | Cited at least one source file from INDEX. 0 = no citation. 1 = at least one valid path. |
| **(b) Faithfulness** | 0–2 | 0 = answer contradicts source. 1 = mostly aligned but one wrong claim. 2 = every factual claim traceable to cited source. |
| **(c) Completeness** | 0–2 | 0 = doesn't address the question. 1 = partial. 2 = addresses fully and at appropriate depth. |
| **(d) No hallucination** | 0–1 | 0 = invented at least one fact not in source. 1 = clean (only source-grounded claims). |

Per-question max: 6. Total max for 30 questions: 180.

Tier 1 (ML methods) additionally requires `≥ 2 verbatim quotes` per answer; failure to quote = automatic 0 on (a) for that question.

### Auto-grader prompt (Gemini)

For each question, the grader receives: `(question, source_files_content, hermes_answer)` and is asked to score on the 4 dimensions above with 1-line justifications. Output is JSON. Gemini-grader output is the official record; Bharat spot-checks ≥ 5 random questions per batch.

## Pass criteria for Week-1 promotion

The FAQ skill **passes Week 1** if all four hold on the 30-question batch:

1. **Overall ≥ 85% (≥ 153/180)** — system-wide quality bar.
2. **(d) = 100%** — zero tolerance for hallucination. Per `feedback_no_hallucination_mandate.md`. Even one fabricated Karpathy / Lasso / BH-FDR detail = batch fails.
3. **(a) ≥ 80%** — citation hygiene.
4. **Average latency ≤ 5 minutes/question** — operationally usable.

Anything else = **DWELL** (not promote, not retire). Re-run after applying the failure-mode fix.

## Acceleration mechanic ("if doing well, move quicker")

The "report card" the user asked for governs Week-N → Week-(N+1) scope:

| Outcome on Week-N batch | Week-(N+1) action |
|---|---|
| **PASS all 4 criteria** | Migrate next 1 free-form skill from the migration master plan (e.g., daily Gemma 4 Pilot report card narrative). Standard pace. |
| **PASS + (b) is 100%** | Migrate next 2 skills AND begin the strict-JSON scaffold (Week 0 prerequisite per baseline doc) so Week-3 structured-output skills are unblocked. **Accelerated.** |
| **DWELL — fail on (a) only** | Patch SKILL.md to enforce stricter citation language. No scope change, re-run. |
| **DWELL — fail on (b) or (c)** | Likely INDEX gap — expand INDEX with missing topic pointers. No scope change, re-run. |
| **FAIL on (d) (any hallucination)** | **Immediate stop.** Re-author SKILL.md with stricter "do not generate beyond source" prompts; if a third (d) fail, escalate the entire FAQ approach (i.e., reconsider Option B/C). |

This mechanic encodes the user's principle: **earned pace, not preset pace.** No Week-2 scope until Week-1 passes the rubric.

## Report card format

`docs/research/hermes_pilot/report_cards/2026-05-XX-week-N.md`:

```markdown
# Hermes Pilot — Week N Report Card

**Date run:** YYYY-MM-DD
**Skills under test:** system-faq (and any others added by acceleration mechanic)
**Total questions:** N
**Aggregate score:** X / Y (Z%)
**Per-tier breakdown:** Tier 1 X/Y, Tier 2 X/Y, ...

**Per-criterion:**
- Citation (a): X%
- Faithfulness (b): X/X*2 (Y%)
- Completeness (c): X/X*2 (Y%)
- Hallucination (d): X/X (Y%) — **must be 100%**

**Verdict:** PASS / DWELL / FAIL
**Triggered action:** [next-week scope per acceleration table]
**Failure modes (if any):** Q07 fabricated Lasso L1 details (Tier 1 hallucination — kills batch);
  Q14 cited deleted spec (INDEX drift); ...
**Claude's notes (≤ 200 words):** [Bharat's spot-check + Claude's review of grader's calls]
```

Report card is committed to the repo so progress is auditable across weeks.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Gemma's reasoning channel leaks into FAQ output (per baseline) | SKILL.md "do not show reasoning" rule + post-processor strips any `<think>` / `Wait, ` / `Actually,` self-correction blocks before saving the answer. |
| INDEX drift — points to deleted/renamed file | Sunday 04:00 IST sync also runs INDEX link-checker; broken links → Telegram alert + auto-create issue. |
| Tier 1 hallucination — Gemma invents a Karpathy detail not in source | Strict 2-quote requirement on Tier 1 + (d) zero-tolerance gate. If Gemma can't quote, it can't claim. |
| Repo size on Contabo (~few hundred MB inc git history) | Negligible — Contabo has 450 GB free. |
| Repo contains secrets we don't want on VPS | Audit `.env`, `.envrc`, `pipeline/config/*` before first sync; add a `.gitattributes` / sparse-checkout to exclude any sensitive paths. |
| Grader (Gemini) is itself fallible — might rate hallucinated answer as correct | Bharat spot-checks ≥ 5 random questions per batch as a sanity layer. If spot-check disagrees with grader on > 1 question, re-grade entire batch with stricter prompt. |
| Auto-grader cost (30 questions × Gemini calls × weekly) | Trivial — Gemini 2.5 Flash is ~$0.0003 per question. Weekly grading run < $0.10. |

## Out of scope (deliberate)

- Subscriber-facing chat UI (this is internal-only for Week 1; Spec B will revisit when packaging for third parties)
- Voice / TTS interfaces
- Multi-turn conversations (one-shot Q&A only — multi-turn waits for Week 3 chained-skills work)
- Web search to fill INDEX gaps (the FAQ refuses out-of-INDEX; gap-filling is a Bharat task, not Hermes')
- Auto-INDEX-update from new commits (manual for Week 1; consider for Week 2 if INDEX maintenance is painful)
- Migrating any other Week-N task. This spec is Week-1 only. The migration framework (rubric, report-card, acceleration) is reusable but each week's task gets its own spec.

## Verification checklist

- [ ] `~/askanka.com/` cloned on Contabo, weekly sync timer registered
- [ ] `docs/faq/INDEX.md` authored with all 5 tiers (≥ 30 topics)
- [ ] `~/.hermes/skills/system-faq/SKILL.md` written, registered (`hermes skills list` shows it)
- [ ] 30 baseline questions authored (6 per tier), saved as `~/hermes-agent/scripts/faq_baseline_questions.json`
- [ ] `run_faq_baseline.sh` runs end-to-end, captures all 30 Q+A+citations+latencies
- [ ] `grade_faq_answers.py` runs, outputs Gemini-graded report card MD
- [ ] First report card committed to `docs/research/hermes_pilot/report_cards/2026-05-XX-week-1.md`
- [ ] Bharat spot-check of 5 random questions completed
- [ ] PASS / DWELL / FAIL verdict recorded; next-week scope decided per acceleration table

## Open questions (none blocking — proceed with stated defaults; flag if you disagree)

1. **Repo clone source on Contabo.** Default: `git clone https://github.com/<user>/askanka.com.git ~/askanka.com` then read-only. Alternative: rsync from laptop on every change (heavier sync but no public mirror). Default unless flagged.
2. **Baseline-question authorship.** Default: Claude drafts all 30 questions; Bharat reviews in this spec before runner script is built. Alternative: Bharat drafts; slower start.
3. **Report card cadence.** Default: weekly Saturday 12:00 IST batch run. Alternative: on-demand.
4. **Gemini-grader credentials.** Default: reuse the existing `pipeline/config/llm_routing.json` Gemini key. Alternative: separate grader-only key for cost tracking. Default unless cost tracking matters at < $0.50/week.
5. **Sensitivity audit before first repo sync to Contabo.** Default: audit `.gitignore`, `pipeline/config/*.example` paths, and `pipeline/data/*` before clone — exclude any path that contains real keys. Alternative: full clone (faster, mildly riskier). Default — security trumps speed.
