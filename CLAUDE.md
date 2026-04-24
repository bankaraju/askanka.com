# askanka.com — Project Instructions

## CRITICAL: Single Source of Truth
**ONE repo. ONE path. No exceptions.**
- Canonical path: `C:/Users/Claude_Anka/askanka.com/`
- ALL code lives here. ALL scheduled tasks run from here. ALL commits go here.
- There is NO second copy. `C:/Users/Claude_Anka/Documents/askanka.com/` does NOT exist.
- If you find code running from a different path, STOP and fix the path — do not create a second copy.
- Before writing ANY code, verify: `git -C C:/Users/Claude_Anka/askanka.com status` — you must be in this repo.

## Superpowers: Mandatory Workflow
Every task follows: brainstorm → plan → build → verify → review. No exceptions.
- Before ANY implementation: invoke the brainstorming skill
- Before ANY code: invoke the writing-plans skill
- Before claiming DONE: invoke verification-before-completion
- After major work: invoke requesting-code-review
- See `memory/feedback_always_use_superpowers.md` for rationale

## Kill Switch: No Un-Registered Trading Rules
Any NEW file matching `*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, or `*_engine.py` MUST ship with a matching entry in `docs/superpowers/hypothesis-registry.jsonl` in the SAME commit. Enforced by `pipeline/scripts/hooks/pre-commit-strategy-gate.sh` (local pre-commit) AND `.github/workflows/strategy-gate.yml` on pull_request. Renaming or refactoring an existing file matching the pattern is not "new" per the `diff-filter=A` test — the gate only triggers on additions. Install the local hook once per clone:
```
cp pipeline/scripts/hooks/pre-commit-strategy-gate.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```
If the hook fails, investigate — do NOT bypass with `--no-verify`. This exists to keep every new trading rule traceable to a registered hypothesis (Station 11, regime-aware autoresearch engine).

## Context Management
When context is getting heavy or you've been working for 2+ hours continuously, invoke /autowrap to checkpoint progress before continuing. This saves memories, commits tracked files, syncs to Obsidian, and writes a resume prompt. Safe to invoke multiple times. Do NOT invoke while a plan step is actively executing.

## Repository Structure
- `pipeline/` — Daily article generation, options monitoring, regime signals, spread intelligence
- `pipeline/terminal/` — Anka Terminal: local web UI (FastAPI + vanilla JS + Lightweight Charts)
- `pipeline/autoresearch/` — Reverse regime engine, overnight research, backtesting
- `pipeline/scripts/` — Scheduled task .bat files (all point to `C:\Users\Claude_Anka\askanka.com\pipeline\`)
- `pipeline/data/` — Runtime data: signals, daily prices, regime state, OI positioning
- `pipeline/tests/` — pytest test suite
- `opus/` — OPUS ANKA Trust Score engine (subtree-merged from opus-anka repo)
- `articles/` — Generated research articles
- `data/` — Website JSON data files (live_status, articles_index, fno_news, etc.)
- `docs/` — Design specs and documentation

## Clockwork Schedule (IST)
The system runs automatically via Windows Scheduled Tasks:

**Overnight Batch:**
- 04:30 — AnkaDailyDump: fetch global prices, fundamentals, FII flows (CRITICAL)
- 04:45 — AnkaETFSignal: compute daily regime zone from stored ETF weights (CRITICAL)
- 04:45 — AnkaReverseRegimeProfile: regime transition patterns, Phase A (CRITICAL)
- 04:45 — AnkaDailyArticles: generate research articles (warn)
- 04:45 — AnkaWatchdogGate: watchdog gate run, check everything (warn)

**Pre-Market:**
- 07:15 — AnkaCorrelationScan: Asian market correlation check (info)
- 07:30 — AnkaMorningBrief0730: morning briefing → Telegram (warn)
- 08:30 — AnkaGapPredictor: overnight gap risk analysis (info)
- 09:00 — AnkaRefreshKite: refresh Zerodha broker session (CRITICAL)
- 09:16 — AnkaOpenCapture: capture today's opening prices (CRITICAL)
- 09:25 — AnkaMorningScan: regime + technicals + OI + news + spread intelligence + Phase B ranker (CRITICAL)
- 09:25 — AnkaPhaseCShadowOpen: F3 live shadow ledger — OPEN rows for today's Phase C OPPORTUNITY signals (info)

**Market Hours (09:30-15:30, every 15 min):**
- AnkaIntraday####: re-scan technicals, OI, news, spreads, correlation breaks
- AnkaSignal####: score signals, apply trust gates, send Telegram alerts
- AnkaCorrelationBreaks: Phase C regime-stock divergence detection
- AnkaWatchdogIntraday: critical task freshness check
- AnkaTrustIntra####: OPUS ANKA model portfolio intraday monitor
- 14:30 — AnkaPhaseCShadowClose: F3 live shadow ledger — mechanical TIME_STOP close at live LTP (info)

**F3 Phase C live shadow:** purpose is forward-test the H1 OPPORTUNITY hypothesis from `docs/research/phase-c-validation/`. Records paper trades at Kite LTP, flattens at 14:30. After ~100 forward trades (≈3–5 months) the binomial test becomes statistically decisive.

**Post-Close:**
- 16:00 — AnkaEODReview: P&L dashboard → Telegram (CRITICAL); also runs `oi_scanner --archive-only` and `website_exporter.py`
- 16:00 — AnkaTAScorerScore: TA Coincidence Scorer daily apply — writes `ta_attractiveness_scores.json` (warn)
- 16:15 — AnkaEODTrackRecord: write official track record + run `website_exporter.py` (warn)
- 16:20 — AnkaEODNews: backtest news predictions (warn)
- 16:35 — AnkaTrustEOD: OPUS ANKA EOD review + next-day outlook (warn)
- 16:45 — AnkaWatchdogGate: watchdog gate run, check everything (warn)

Note: website_exporter.py is invoked from morning_scan (09:25), every intraday cycle (09:30–15:30), eod_review (16:00), eod_track_record (16:15), and daily_dump (04:30) — it is NOT a standalone scheduled task. It auto-deploys data/*.json to the GitHub Pages branch.

**Autoresearch v2 (new 2026-04-25):**
- 20:00 — AnkaAutoresearchMode2: per-regime Mode 2 proposer + in-sample runner, 5 parallel workers (info)
- 05:00 — AnkaAutoresearchBHFDR: per-regime BH-FDR batch trigger (info)
- 05:30 — AnkaAutoresearchHoldout: single-touch holdout runner (info)

**Weekly:**
- Saturday 22:00 — AnkaETFReoptimize: reoptimize ETF weights with Indian data (CRITICAL)
- Sunday 00:00 — AnkaUnifiedBacktest: 777-day historical replay backtest (CRITICAL)
- Sunday 01:00 — AnkaFeatureScorerFit: weekly run of quarterly walk-forward Feature Coincidence Scorer fit (warn)
- Sunday 01:30 — AnkaTAScorerFit: RELIANCE TA model walk-forward fit — writes `ta_feature_models.json` (warn)
- Sunday 22:00 — AnkaWeeklyAgg + AnkaWeeklyStats: weekly spread statistics (warn)
- Friday 16:00 — AnkaWeeklyReport: weekly performance report → Telegram (warn)

Total: 77+ scheduled tasks (see `pipeline/config/anka_inventory.json` for canonical list)

## Scheduler Inventory (Canonical)

Every `Anka*` scheduled task MUST appear in `pipeline/config/anka_inventory.json` with its tier (critical/warn/info), cadence_class (intraday/daily/weekly), expected output files, and grace_multiplier. The data-freshness watchdog (`pipeline/watchdog.py`) uses this inventory as the source-of-truth for what should exist in the scheduler and what their output-file freshness contracts are. Adding a new scheduled task without updating the inventory will trigger an `ORPHAN_TASK` alert on the next watchdog run — this is by design.

## Obsidian Vault — Deep Context
The Obsidian vault at `C:/Users/Claude_Anka/ObsidianVault/` is the project's knowledge base. Read `_claude_context/VAULT_MAP.md` for what's where. Key rules:
- When memory files don't have the answer, check the vault (chat exports, project state docs, trust scores)
- When the user says "we discussed this before", search `chat-YYYY-MM-DD-*.md` files in the relevant pillar folder
- When writing articles, read the relevant pillar folder (epstein/, geopolitics/, markets/) for source material
- During /autowrap or /wrapup, write a session summary to `_claude_sessions/` with what was built, decisions made, and open threads
- Update `_claude_context/VAULT_MAP.md` if new high-value content was created during the session

## System Operations Manual
The canonical reference for how the entire system works is `docs/SYSTEM_OPERATIONS_MANUAL.md`. It covers:
- Complete data flow: close → overnight → morning → intraday → EOD
- Every scheduled task with time, inputs, outputs
- The watchdog and how it monitors freshness
- Known gaps and target architecture
- Glossary of all terms

**READ THIS FIRST** at the start of every session. It prevents the #1 recurring problem: rebuilding understanding from scratch each session.

## Documentation Sync Rule (CRITICAL)
Any change to the system — new task, new script, new data flow, changed schedule — MUST update ALL of these in the SAME commit:
1. The code itself
2. `docs/SYSTEM_OPERATIONS_MANUAL.md` — update the relevant section
3. `pipeline/config/anka_inventory.json` — if a scheduled task was added/changed
4. `CLAUDE.md` — if the clockwork schedule or architecture changed
5. Memory files — if a design decision was made

**Never ship code without updating docs. Never update docs without updating inventory.**

This rule exists because the system breaks between sessions when one document says one thing and the code does another.

## Architecture: The Golden Goose Pipeline
The system is an 8-layer pipeline where each layer feeds the next:
1. **ETF Regime Engine** — 28 global ETFs + Indian data → market regime (weekly reopt, daily signal)
2. **Trust Scores** — OPUS ANKA management credibility grades (174/215 scored)
3. **Spread Intelligence** — Regime-gated pair trades with per-spread sizing
4. **Reverse Regime** — Phase A (playbook), Phase B (daily ranker), Phase C (intraday breaks)
5. **Technicals + OI/PCR** — Confirmation/accentuation of conviction
6. **Signal Generation** — Conviction scoring with trust score gates
7. **Shadow P&L** — Paper trading with full stop/target tracking
8. **Track Record** — Visual proof strip, realized P&L, forward test scorecard

The ETF regime is the BRAIN — if it's stale, everything downstream is wrong.
See `docs/SYSTEM_OPERATIONS_MANUAL.md` for the complete data flow diagram.

## LLM Provider Policy
Gemini 2.5 Flash is the primary provider. Haiku 4.5 is the locked fallback. Do not switch providers without explicit user approval. See `memory/reference_llm_providers.md` for full rationale.
