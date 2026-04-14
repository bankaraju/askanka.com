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

## Context Management
When context is getting heavy or you've been working for 2+ hours continuously, invoke /autowrap to checkpoint progress before continuing. This saves memories, commits tracked files, syncs to Obsidian, and writes a resume prompt. Safe to invoke multiple times. Do NOT invoke while a plan step is actively executing.

## Repository Structure
- `pipeline/` — Daily article generation, options monitoring, regime signals, spread intelligence
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
- 04:30 — Overnight global data dump + regime computation
- 04:45 — Daily article generation (war + epstein)
- 09:00 — Kite session refresh
- 09:15 — Pre-market briefing → Telegram
- 09:25 — Morning scan: regime + technicals + OI + news + spread intelligence + Phase B ranker
- 09:30-15:30 (every 15 min) — Intraday scan + signal generation + Phase C breaks
- 15:30 — Closing price capture
- 16:00 — EOD P&L + track record
- 16:30 — Website data export + news refresh
- Sunday 22:00 — Weekly spread statistics

## Obsidian Vault — Deep Context
The Obsidian vault at `C:/Users/Claude_Anka/ObsidianVault/` is the project's knowledge base. Read `_claude_context/VAULT_MAP.md` for what's where. Key rules:
- When memory files don't have the answer, check the vault (chat exports, project state docs, trust scores)
- When the user says "we discussed this before", search `chat-YYYY-MM-DD-*.md` files in the relevant pillar folder
- When writing articles, read the relevant pillar folder (epstein/, geopolitics/, markets/) for source material
- During /autowrap or /wrapup, write a session summary to `_claude_sessions/` with what was built, decisions made, and open threads
- Update `_claude_context/VAULT_MAP.md` if new high-value content was created during the session

## LLM Provider Policy
Gemini 2.5 Flash is the primary provider. Haiku 4.5 is the locked fallback. Do not switch providers without explicit user approval. See `memory/reference_llm_providers.md` for full rationale.
