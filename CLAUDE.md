# askanka.com — Project Instructions

## Context Management
When context is getting heavy or you've been working for 2+ hours continuously, invoke /autowrap to checkpoint progress before continuing. This saves memories, commits tracked files, syncs to Obsidian, and writes a resume prompt. Safe to invoke multiple times. Do NOT invoke while a plan step is actively executing.

## Repository Structure
- `pipeline/` — Daily article generation, options monitoring, regime signals
- `opus/` — OPUS ANKA Trust Score engine (subtree-merged from opus-anka repo)
- `articles/` — Generated research articles
- `data/` — Static data files and indexes
- `docs/` — Design specs and documentation

## Obsidian Vault — Deep Context
The Obsidian vault at `C:/Users/Claude_Anka/ObsidianVault/` is the project's knowledge base. Read `_claude_context/VAULT_MAP.md` for what's where. Key rules:
- When memory files don't have the answer, check the vault (chat exports, project state docs, trust scores)
- When the user says "we discussed this before", search `chat-YYYY-MM-DD-*.md` files in the relevant pillar folder
- When writing articles, read the relevant pillar folder (epstein/, geopolitics/, markets/) for source material
- During /autowrap or /wrapup, write a session summary to `_claude_sessions/` with what was built, decisions made, and open threads
- Update `_claude_context/VAULT_MAP.md` if new high-value content was created during the session

## LLM Provider Policy
Gemini 2.5 Flash is the primary provider. Haiku 4.5 is the locked fallback. Do not switch providers without explicit user approval. See `memory/reference_llm_providers.md` for full rationale.
