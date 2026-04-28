# Gemma 4 Local-Inference Pilot — Design Doc

**Status:** SCOPING (pre-implementation)
**Owner:** Anka research
**Date:** 2026-04-28
**Pilot window:** 20 calendar days from install, target start 2026-04-29
**Cutover decision:** target 2026-05-19 (or +20 days from actual install)

---

## 1 — Why this exists

Three converging constraints make a local-inference path the right move:

1. **Cost predictability.** Memory `feedback_cost_discipline.md` records prior surprises ($90 Claude burn, $40 Gemini surprise charge). Provider-level caps help; eliminating per-token cost on the high-volume tier helps more.
2. **Commercial-product license certainty.** Gemma 4 ships under Apache 2.0 (verified 2026-04-28: Google Open Source Blog, VentureBeat). Previous Gemma versions used a custom Google license that legal teams flagged. Apache 2.0 is self-executing — no notification, no approval flow, no revenue threshold, no field-of-use carve-outs. You can fine-tune, keep weights proprietary, ship in a closed commercial product.
3. **Rate-limit pain in production.** Memory `feedback_gemini_rate_limit.md` documents Gemini free-tier silent failures on trust-score work. Local inference is unmetered.

What this is **not**: a speed play. CPU inference on the Contabo VPS is 5–10× slower than frontier cloud APIs end-to-end. The pilot validates the cost/quality tradeoff at fixed (slow) latency for asynchronous Tier 2 tasks. Tier 1 work stays on frontier APIs.

## 2 — Locked decisions (no parameter changes during pilot)

### 2.1 Tier separation

| Tier | Workload | Provider |
|---|---|---|
| **Tier 1 — Discipline / Architecting** | Hypothesis writing, statistical judgment, multi-step debugging, architecture decisions, brainstorming, plan writing, code review, gate enforcement | Claude Opus 4.7 / Gemini 2.5 Pro (frontier API) |
| **Tier 2 — Mundane / Volume** | Article drafts, EOD narratives, news classification, sentiment scoring, OCR, structured extraction, summarization, concall supplement | Gemma 4 26B-A4B local (Contabo) |

**Locked rule:** No Tier 1 work moves to local during the pilot. Tier 2 is the only thing being evaluated.

### 2.2 Hardware (Contabo VPS, verified 2026-04-28)

- 47 GB RAM (effectively 48 GB)
- 12 vCPU AMD EPYC (with IBPB; AVX-512 available)
- 4 GB swap
- 474 GB free disk
- Kernel 6.8

### 2.3 Model variant

**Gemma 4 26B-A4B (MoE) at Q4_K_M quantization, ~16 GB resident.**

- Total parameters: 26 B
- Active parameters per token: 3.8 B (128 experts, top-k routing)
- Context window: 256 K tokens
- Multimodal: image + text + audio inputs, text output only
- Multilingual: 140+ languages
- Source: Google AI for Developers, HuggingFace `google/gemma-4-26B-A4B-it`

Headroom: 47 GB total – 16 GB model – ~4 GB system + buffer cache = ~27 GB free for KV cache and concurrent smaller models. Comfortably fits.

**Not chosen, with reasons:**
- 31B Dense Q4 (~19 GB resident, 3–5 tok/s on this CPU): generation too slow for batch SLAs.
- E4B (4 B): capability ceiling too low for prose tasks (Tier 2 task #4).
- E2B (2 B): only useful for trivial classification; doesn't span the difficulty range we want to evaluate.

### 2.4 Inference server: Ollama

- One-line install on Contabo
- Runs as systemd service (`ollama serve`)
- OpenAI-compatible endpoint at `:11434/v1/chat/completions`
- Pull model with `ollama pull gemma4:26b`

**Not chosen:**
- vLLM: faster paged-attention but heavier setup; bandwidth-limited on CPU anyway, so the gain is small. Reserve for Phase 3 if a perf bottleneck emerges.
- llama.cpp directly: most control but more glue code; Ollama wraps llama.cpp under the hood and gives the API for free.

### 2.5 License: Apache 2.0

Verified at Google Open Source Blog (March 2026 announcement) and Google AI for Developers Gemma 4 docs. No carve-outs. Self-executing for commercial use. Pilot output and any future fine-tuned weights are unencumbered.

## 3 — The four pilot tasks

| # | Task | Difficulty | Cadence | Why this one |
|---|---|---|---|---|
| 1 | Trust-score concall supplement | Easy | Per-ticker, weekly batches | Currently rate-limited on Gemini free tier (memory `feedback_gemini_rate_limit.md`); silent fails. Local is unmetered — straight pain relief. |
| 2 | News classification + sentiment | Easy | Intraday + EOD batches, ~50–200 calls/day | Short input, structured output. Cleanest test of "Gemma at scale on structured extraction." |
| 3 | EOD Telegram trade narrative | Medium | Daily 16:35 IST, single call | Short prose with embedded numbers. Templated. Goes to private channel — quality regression is recoverable. |
| 4 | Daily article draft (single topic — markets) | Hard | Daily 04:45–04:50 IST window, single call | Longer prose. Public-facing. Finds the quality ceiling. **One topic only** to bound the blast radius. |

**Out of scope for pilot:** earnings-call audio OCR (multimodal capability stretch — opens new product surface, not part of the cost-cutting goal). Bulk-deals narrative, article market-data grounding, daily trade narrative — held back to constrain pilot scope.

### 3.1 Task-specific success criteria (per task, locked at pilot start)

For each task we lock the rubric pass criteria below. The aggregate report card aggregates across tasks; per-task auto-disablement uses the per-task criteria.

**Task 1 — Concall supplement:**
- Output is valid JSON matching trust-score supplement schema
- Includes 3+ concall-derived signal points
- No hallucinated tickers (cross-check against universe)
- Latency < 90 s per ticker

**Task 2 — News classification + sentiment:**
- Returns one of: BULLISH / BEARISH / NEUTRAL / NOT_RELEVANT
- Confidence ∈ [0, 1]
- Sector tag from canonical sector list
- Latency < 30 s per item

**Task 3 — EOD Telegram trade narrative:**
- Length 200–600 chars (Telegram-friendly)
- Mentions today's regime
- Mentions at least one specific position from the day's ledger
- No factually wrong numbers (cross-check against `live_paper_ledger.json`)
- Latency < 90 s

**Task 4 — Daily article draft:**
- Length 800–2500 words
- All cited market numbers verifiable against `data/global_regime.json` (memory `feedback_stale_data_disqualifies_article.md` rule)
- No hallucinated tickers, names, dates
- Coherent narrative arc (human pairwise audit)
- Latency < 4 minutes

## 4 — Report card framework

### 4.1 Hybrid scoring (decision (d) from brainstorm)

**Automated rubric (every call, real-time):**
Per-task scoring function returns pass/fail + score ∈ [0, 1]. Run on both stacks (current API + Gemma) for every shadow-mode call. Logged to JSONL. Pass criteria are the per-task rules in §3.1 above.

**Daily 10-sample human pairwise audit (your time, ~5 min/day):**
Each task contributes 10 random samples per day. UI shows current-stack output and Gemma output side-by-side, blind-ordered. You click which is better (or "tie"). Saves to `audit/pairwise/<YYYY-MM-DD>.jsonl`. Lives in a new terminal tab "Gemma Pilot".

**Pairwise win rate definition (locked):**
`win_rate = (gemma_wins + 0.5 * ties) / total_ratings`. A 50% rate means Gemma is statistically tied with the current stack — that's the cutover floor. Below 40% means Gemma is meaningfully worse. Above 60% means Gemma is meaningfully better.

### 4.2 Auto-disablement guardrails

- **Rubric pass rate < 90% over rolling 24h** → automatic rollback (Gemma traffic for that task drops to 0%, current stack resumes 100%) + Telegram alert.
- **Pairwise win rate < 40% over rolling 7 days** → manual review required (no auto-rollback because human eval is slower-cadence; an honest 40%-pairwise model may still be good enough for cost reasons).
- Both guardrails apply per-task. A failure on task #4 does not affect tasks #1–3.

### 4.3 Activation pattern

**Days 1–7 (shadow):**
Both stacks run on every call. Current stack output goes to production. Gemma output is logged only. Rubric scoring runs on both. Pairwise audit runs on Gemma vs current.

**Day 8 onward (live):**
For each task that hit rubric ≥ 95% + pairwise wins ≥ 60% during shadow week, flip to LIVE — Gemma serves production traffic. Current stack drops to shadow (logged for ongoing comparison). Tasks that miss the threshold stay shadow.

**Day 20 (cutover decision):**
For each task currently LIVE: if rubric ≥ 90% AND pairwise ≥ 50% over the full 20 days → recommend permanent cutover. Below either floor → revert to current stack permanently or extend pilot.

## 5 — File / module inventory (planned)

```
pipeline/llm_router.py                                # central routing layer
pipeline/llm_providers/
  __init__.py
  base.py                                             # Provider protocol
  openai_compat.py                                    # Ollama / OpenAI-compat client
  anthropic.py                                        # Claude wrapper
  gemini.py                                           # Gemini wrapper
pipeline/data/research/gemma4_pilot/
  audit/
    <task_name>/<YYYY-MM-DD>.jsonl                    # per-call logs
    pairwise/<YYYY-MM-DD>.jsonl                       # pairwise ratings
  rubrics/
    concall_supplement.py
    news_classification.py
    eod_narrative.py
    article_draft.py
  daily_report.py                                     # EOD report card aggregator
pipeline/scripts/
  install_gemma4_contabo.sh                           # one-shot Contabo bootstrap
  gemma4_health_check.py                              # daily 05:30 IST cron
pipeline/terminal/api/gemma_pilot.py                  # endpoint serving the LIVE-tab data
pipeline/terminal/static/js/pages/gemma-pilot.js      # pairwise rating UI
pipeline/terminal/templates/gemma_pilot.html
docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md  # this file
docs/SYSTEM_OPERATIONS_MANUAL.md                       # update with new tab + tasks
pipeline/config/anka_inventory.json                    # add health-check + report-card tasks
memory/reference_llm_providers.md                      # update with Gemma 4 entry
```

## 6 — Cutover decision criteria (day 20)

A task moves permanently to local Gemma if and only if:

1. **Rubric pass rate ≥ 90%** over the full 20 days (auto-disablement floor was 90% — clearing it for the full window is the standard).
2. **Pairwise win rate ≥ 50%** over the full 20 days (Gemma is at least as good as the current stack on human-eval).
3. **No silent regression** — the per-task domain-specific check (e.g., for task #4, no hallucinated market numbers across 20 articles).
4. **Cost reduction ≥ 80%** of the prior task's API spend, measured against same-volume baseline (sanity check that the cost case actually pencils).

A task that clears 1 + 2 but misses 4 (rare — local is $0/token, so the only way 4 fails is if Gemma needed massive retries) goes to manual review. A task that clears 1 + 4 but misses 2 stays on current stack — human eval beats cost on quality-sensitive Tier 2.

A task that misses 1 ANY day during the pilot triggers auto-disablement; cutover is then off the table for that task pending root-cause and re-pilot under a new spec.

## 7 — What this pilot is NOT

- **Not a fine-tune.** RAG-only against existing specs/code/memory via pgvector or LanceDB. Decision on fine-tune happens AFTER the report card, NEVER during. Per memory: data drifts daily; fine-tune freezes on a snapshot. Catastrophic-forgetting risk is real and we don't have an eval harness for it.
- **Not a Tier 1 cutover.** Architecture decisions, hypothesis writing, multi-step agentic debugging, and statistical judgment stay on frontier APIs. The pilot does not test Gemma on these tasks. Don't move them.
- **Not a speed play.** Local CPU inference is 5–10× slower than cloud. The win is cost + license + privacy. Speed-sensitive intraday tasks stay on frontier APIs.
- **Not five tasks.** Four. Adding a fifth during the pilot dilutes the eval and breaks the rubric calibration.
- **Not retroactive.** Calls made before pilot start are not in the eval. The 20-day window is forward-only.

## 8 — Failure modes + risk

**Most likely failure:** Task #4 (article drafts) regresses on prose quality. Pairwise rate drops below 50%, articles look stiff or factually drift even with RAG. Mitigation: revert task #4 to current stack at day 8 if shadow week shows pairwise < 50%; tasks #1–3 may still cutover.

**Second most likely:** Task #1 (concall supplement) hallucinates tickers. Local model has weaker IP recall than Gemini for less-common Indian small-caps. Mitigation: rubric includes ticker-cross-check; auto-disable if hallucination rate > 5%.

**Third:** Latency on task #2 (news classification at scale) blows past the 30s budget when news volume spikes (e.g., earnings season). Mitigation: budget headroom is 3× normal volume; if exceeded, news work falls back to current stack automatically.

**Catastrophic but unlikely:** Contabo VPS goes down during pilot. Tier 2 traffic falls back to frontier APIs (which still have rate-limit risk). Health check at 05:30 IST flags any degraded state.

**Slow drift (the one we're vigilant about):** RAG retrieval embeddings stale as code/docs evolve. Daily incremental re-embed of changed files (job scheduled in Phase 1). Without this, accuracy degrades silently over the pilot window.

## 9 — Cross-references

- Memory: `feedback_cost_discipline.md` — provider-level caps lesson
- Memory: `feedback_gemini_rate_limit.md` — current trust-score pain
- Memory: `reference_llm_providers.md` — current LLM stack reference
- Memory: `project_vps_phase1.md` — Contabo workflow
- Memory: `reference_contabo_vps.md` — VPS connection details
- Memory: `feedback_no_hallucination_mandate.md` — discipline rule the pilot must respect
- Memory: `feedback_stale_data_disqualifies_article.md` — task #4 grounding rule
- Memory: `feedback_explain_simply.md` — task #4 narrative rule
- Backtesting policy: `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` — pilot output is research evidence, not deployed data
- Sources verified 2026-04-28: Google Open Source Blog, VentureBeat, HuggingFace `google/gemma-4-26B-A4B-it`, Google AI for Developers Gemma 4 docs

## 10 — Open questions deferred to plan stage

These don't need to be resolved before the spec is written but must be answered in the implementation plan:

- Vector DB choice for RAG: pgvector (heavier, postgres-based) vs LanceDB (lighter, file-based). Defaulting to LanceDB unless there's a reason to want pg.
- Embedding model choice: Gemma 4's own embedding output vs `bge-large-en-v1.5` vs `all-mpnet-base-v2`. Defaulting to `bge-large-en-v1.5` for English+code corpus performance.
- How exactly the routing layer hands off prompt + retrieved context. Wrapper pattern or middleware pattern.
- Concrete EOD report-card aggregator format — Markdown to memory file, or HTML on terminal, or both.
- Exact pairwise-UI sample-selection algorithm: pure random, stratified by hour, or stratified by rubric-score bucket.
