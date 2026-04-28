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

## Data Validation Gate (CRITICAL)
**No backtest, no validation run, no live signal consumption may proceed against a dataset that has not been accepted under** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`. This is the data-side companion to the model governance policy. Specifically:
- Every dataset cited as evidence must be **registered** (Section 6), have a **schema contract** (Section 8), have passed **cleanliness gates** (Section 9), declare its **adjustment mode** (Section 10), be **point-in-time correct** (Section 11), and have a **contamination map** (Section 14) where event-noise channels are credible.
- A backtest that runs on data that has not satisfied this policy is research evidence of nothing and shall not be cited.
- For new datasets, write a registration + audit document under `docs/superpowers/specs/<date>-<dataset>-data-source-audit.md` (template: `2026-04-25-earnings-data-source-audit.md`) BEFORE writing the hypothesis spec that consumes it.
- Section 21 of the data policy binds this gate to the model governance ladder: a model cannot reach Approved status if any data dependency is below Approved-for-deployment at the corresponding tier.

## Kill Switch: No Un-Registered Trading Rules
Any NEW file matching the regex in `pipeline/scripts/hooks/strategy_patterns.txt` (currently: `*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py`) MUST ship with a matching entry in `docs/superpowers/hypothesis-registry.jsonl` in the SAME commit. Both the local pre-commit hook (`pipeline/scripts/hooks/pre-commit-strategy-gate.sh`) and the CI workflow (`.github/workflows/strategy-gate.yml`) read the regex from the same patterns file — when adding a new suffix, edit `strategy_patterns.txt` ONLY. Renaming or refactoring an existing file matching the pattern is not "new" per the `diff-filter=A` test — the gate only triggers on additions. Install the local hook once per clone:
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
- 04:30 — AnkaTAKarpathyPredict: H-2026-04-29-ta-karpathy-v1 daily forward prediction; emits today_predictions.json from frozen Lasso models (info, VPS systemd)
- 05:30 — AnkaGemma4HealthCheck: ollama + Gemma 4 26B-A4B daily PONG ping (warn, pilot 2026-04-29 → 2026-05-19)
- 04:45 — AnkaETFSignal: compute daily regime zone from stored ETF weights (CRITICAL)
- 04:45 — AnkaReverseRegimeProfile: regime transition patterns, Phase A (CRITICAL)
- 04:45 — AnkaDailyArticles: generate research articles (warn)
- 04:45 — AnkaWatchdogGate: watchdog gate run, check everything (warn)

**Pre-Market:**
- 07:15 — AnkaCorrelationScan: Asian market correlation check (info)
- 07:30 — AnkaMorningBrief0730: morning briefing → Telegram (warn)
- 08:00 — AnkaEarningsCalendarFetch: IndianAPI corporate_actions sweep + parquet history. Feeds H-2026-04-25-001 (warn)
- 08:30 — AnkaGapPredictor: overnight gap risk analysis (info)
- 09:00 — AnkaRefreshKite: refresh Zerodha broker session (CRITICAL)
- 09:16 — AnkaOpenCapture: capture today's opening prices (CRITICAL)
- 09:16 — AnkaSecrsiCaptureOpens: capture full F&O universe LTP for SECRSI 11:00 snapshot. Holdout 2026-04-28 → 2026-07-31 (info)
- 09:15 — AnkaTAKarpathyOpen: H-2026-04-29-ta-karpathy-v1 holdout OPEN — opens trades for cells passing all 5 qualifier gates at Kite LTP. Holdout 2026-04-29 → 2026-05-28 (info, VPS systemd)
- 09:25 — AnkaMorningScan: regime + technicals + OI + news + spread intelligence + Phase B ranker (CRITICAL)
- 09:25 — AnkaPhaseCShadowOpen: F3 live shadow ledger — OPEN rows for today's Phase C OPPORTUNITY signals (info)
- 09:25 — AnkaScannerPairedOpen: Scanner Top-10 paired-shadow open (futures + ATM options) for yesterday's scan; paper engine, exempt from 14:30 cutoff (info)
- 09:30 — AnkaH20260426001PaperOpen: H-2026-04-26-001 + H-2026-04-26-002 forward paper test, OPEN leg, single-touch holdout 2026-04-27 → 2026-05-26 (info)
- 11:00 — AnkaSecrsiBasketOpen: H-2026-04-27-003 SECRSI basket open — 8-leg market-neutral sector RS pair (info)

**Market Hours (09:30-15:30, every 15 min):**
- AnkaIntraday####: re-scan technicals, OI, news, spreads, correlation breaks
- AnkaSignal####: score signals, apply trust gates, send Telegram alerts
- AnkaCorrelationBreaks: Phase C regime-stock divergence detection
- AnkaWatchdogIntraday: critical task freshness check
- AnkaTrustIntra####: OPUS ANKA model portfolio intraday monitor
- 14:30 — AnkaPhaseCShadowClose: F3 live shadow ledger — mechanical TIME_STOP close at live LTP (info)
- 14:30 — AnkaH20260426001PaperClose: H-2026-04-26-001 + H-2026-04-26-002 forward paper test, CLOSE leg, mechanical TIME_STOP at Kite LTP (info)
- 14:30 — AnkaSecrsiBasketClose: H-2026-04-27-003 SECRSI mechanical TIME_STOP close at Kite LTP (info)
- 15:25 — AnkaTAKarpathyClose: H-2026-04-29-ta-karpathy-v1 holdout TIME_STOP close at Kite LTP. Holdout 2026-04-29 → 2026-05-28 (info, VPS systemd)
- 15:30 — AnkaScannerPairedClose: Scanner Top-10 paired-shadow mechanical close at Kite LTP (info)
- Hourly 09:00–22:00 — AnkaGemma4AutoDisable: pilot guardrail check; trips a task to disabled if 24h shadow rubric <90% (n>=5), flags manual review if 7d pairwise <40% (n>=10) (info, pilot)

## 14:30 IST New-Signal Cutoff (CRITICAL)
No engine may OPEN a new live shadow position after **14:30 IST**. The mechanical TIME_STOPs run at 14:30, so anything opened later has under 60 min of execution window before forced close — not a tradeable trade. The cutoff is enforced at the source in three engines:
- `pipeline/run_signals.py` — gates news-event-triggered spreads (`_run_once_inner`, lines ~213-238) and the Phase C break candidate path (`generate_break_candidates` call at lines ~466-487)
- `pipeline/break_signal_generator.py` — defensive guard inside `generate_break_candidates` itself (`_now_ist_time()` indirection lets tests bypass)
- `pipeline/arcbe_signal_generator.py` — defensive guard inside `generate_arcbe_signals` (ARCBE normally fires from 07:15 IST pre-market, so the gate is belt-and-braces)

Existing OPEN positions are still monitored, P&L still updates, stops still fire — only NEW OPENs are blocked. Holdout-test paper engines (H-2026-04-26-001, SECRSI) have their own pre-registered open windows and are unaffected.

**F3 Phase C live shadow:** purpose is forward-test the H1 OPPORTUNITY hypothesis from `docs/research/phase-c-validation/`. Records paper trades at Kite LTP, flattens at 14:30. After ~100 forward trades (≈3–5 months) the binomial test becomes statistically decisive.

**F3 Phase C paired-options sidecar (2026-04-27):** every Phase C live shadow OPEN/CLOSE now also writes a paired ATM-options leg to `pipeline/data/research/phase_c/live_paper_options_ledger.json`. Forward-only OOS measurement layer for whether Phase C edge survives in non-linear payoff space. Spec: `docs/superpowers/specs/2026-04-27-phase-c-options-paired-shadow-design.md`. Forensic-only — no edge claim. Verdict cadence: descriptive at N>=30, bootstrap-inference at N>=100.

**H-2026-04-26-001 / H-2026-04-26-002 forward paper test:** new pre-registered hypothesis pair started 2026-04-27. Same signal stream (|z|≥2.0 mechanical correlation breaks, fade direction, ATR(14)×2 stop, TIME_STOP 14:30); H-001 unconditional, H-002 reads only `regime_gate_pass=True` rows (regime ≠ NEUTRAL). Single-touch holdout window: 2026-04-27 → 2026-05-26. Spec: `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md`. Ledger: `pipeline/data/research/h_2026_04_26_001/recommendations.csv`. **No parameter changes during the holdout window per backtesting-specs.txt §10.4 strict.**

**H-2026-04-27-003 SECRSI (Sector RS Intraday Pair):** trend-continuation, regime-agnostic, market-neutral. 11:00 IST sector snapshot ranks ~25 sectors by median per-stock %chg-from-open; LONG top-2 stocks of top-2 sectors + SHORT bottom-2 stocks of bottom-2 sectors (8 legs, equal-weight). ATR(14)×2 per-leg stop, mechanical TIME_STOP at 14:30 IST. Single-touch holdout 2026-04-28 → 2026-07-31 (auto-extends if n < 40). Spec: `docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md`. Ledger: `pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv`. **No parameter changes during the holdout window per backtesting-specs.txt §10.4 strict.** Distinct from H-001 (fade direction) — designed as portfolio diversifier.

**H-2026-04-29-ta-karpathy-v1 (per-stock TA Lasso, top-10 NIFTY pilot):** per-stock Lasso L1 logistic regression on ~60 daily TA features, 4-fold walk-forward + BH-FDR permutation null + qualifier gate. Frozen universe: RELIANCE/HDFCBANK/ICICIBANK/INFY/TCS/BHARTIARTL/KOTAKBANK/LT/AXISBANK/SBIN. T+1 09:15→15:25 IST intraday only (no overnight). Per-cell ATR(14)×2 stop. Single-touch holdout 2026-04-29 → 2026-05-28 (≈21 trading days). Spec: `docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md` (v1.1 — Deflated Sharpe metric report-only at v1, gate-blocking at v2 when N≥100 days). Honest expectation: 0–3 stocks qualify. Predecessor H-2026-04-24-001 FAILED on RELIANCE — distinct family widening. **No parameter changes during the holdout window per backtesting-specs.txt §10.4 strict.** Runs on VPS systemd (predict 04:30 / open 09:15 / close 15:25). Ledger: `pipeline/data/research/h_2026_04_29_ta_karpathy_v1/recommendations.csv`.

**Gemma 4 Pilot (2026-04-29 → 2026-05-19):** 20-day forward-only Tier 2 evaluation of Gemma 4 26B-A4B local inference (Contabo VPS, Ollama at `127.0.0.1:11434/v1` via SSH tunnel from laptop) as the LLM provider for four mundane/volume tasks: trust-score concall supplement, news classification, EOD Telegram narrative, and the **markets** daily article (Epstein + war stay on the current Gemini stack). Routing per-task in `pipeline/config/llm_routing.json` (modes: `live` / `shadow` / `disabled`). All 4 tasks start in `shadow` (primary=Gemini, shadow=Gemma) so production output is unchanged while we accumulate audit data. Day-8 promotion to `live` requires rubric ≥95% + pairwise ≥60%; day-20 cutover requires rubric ≥90% AND pairwise ≥50% AND ≥80% cost reduction. Audit: `pipeline/data/research/gemma4_pilot/audit/<task>/<YYYY-MM-DD>.jsonl`. Report cards (daily 22:00 IST): `pipeline/data/research/gemma4_pilot/report_cards/<date>.{json,md}`. Auto-disable guardrail (hourly 09–22 IST): rubric <90% (24h, n≥5) flips a task to `disabled`; pairwise <40% (7d, n≥10) writes `manual_review/<task>.flag`. Spec: `docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md`. Plan: `docs/superpowers/plans/2026-04-28-gemma4-pilot.md`. **Tier 1 (architecting / discipline) stays on frontier APIs — do not migrate.** Apache 2.0 license certainty + zero per-token cost are the two reasons; speed is NOT — local CPU is 5–10× slower.

**Post-Close:**
- 16:00 — AnkaEODReview: P&L dashboard → Telegram (CRITICAL); also runs `oi_scanner --archive-only` and `website_exporter.py`
- 16:00 — AnkaTAScorerScore: TA Coincidence Scorer daily apply — writes `ta_attractiveness_scores.json` (warn)
- 16:15 — AnkaEODTrackRecord: write official track record + run `website_exporter.py` (warn)
- 16:20 — AnkaEODNews: backtest news predictions (warn)
- 16:30 — AnkaBulkDeals: NSE bulk + block deals daily CSV pull → `bulk_deals/<date>.parquet` (info)
- 16:30 — AnkaPatternScannerScan: daily F&O 12-pattern scan + Top-10 ranking, writes pattern_signals_today.json (info)
- 16:35 — AnkaTrustEOD: OPUS ANKA EOD review + next-day outlook (warn)
- 16:45 — AnkaWatchdogGate: watchdog gate run, check everything (warn)
- 18:30 — AnkaInsiderTrades: NSE PIT insider disclosures, last 7 days rolling → `insider_trades/<YYYY-MM>.parquet` (info)
- 22:00 — AnkaGemma4DailyReport: pilot rubric + pairwise aggregation, writes `report_cards/<today>.{json,md}` + Telegram one-liner (warn, pilot)

Note: website_exporter.py is invoked from morning_scan (09:25), every intraday cycle (09:30–15:30), eod_review (16:00), eod_track_record (16:15), and daily_dump (04:30) — it is NOT a standalone scheduled task. It auto-deploys data/*.json to the GitHub Pages branch.

**Autoresearch v2 (new 2026-04-25):**
- 20:00 — AnkaAutoresearchMode2: per-regime Mode 2 proposer + in-sample runner, 5 parallel workers (info)
- 05:00 — AnkaAutoresearchBHFDR: per-regime BH-FDR batch trigger (info)
- 05:30 — AnkaAutoresearchHoldout: single-touch holdout runner (info)

**Weekly:**
- Sunday 02:00 — AnkaPatternScannerFit: weekly 5y F&O pattern fit, writes pattern_stats.parquet (warn)
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
