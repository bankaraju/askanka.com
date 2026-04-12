# askanka.com — Project Instructions

## Context Management
When context is getting heavy or you've been working for 2+ hours continuously, invoke /autowrap to checkpoint progress before continuing. This saves memories, commits tracked files, syncs to Obsidian, and writes a resume prompt. Safe to invoke multiple times. Do NOT invoke while a plan step is actively executing.

## Repository Structure
- `pipeline/` — Daily article generation, options monitoring, regime signals
- `opus/` — OPUS ANKA Trust Score engine (subtree-merged from opus-anka repo)
- `articles/` — Generated research articles
- `data/` — Static data files and indexes
- `docs/` — Design specs and documentation

## LLM Provider Policy
Gemini 2.5 Flash is the primary provider. Haiku 4.5 is the locked fallback. Do not switch providers without explicit user approval. See `memory/reference_llm_providers.md` for full rationale.
