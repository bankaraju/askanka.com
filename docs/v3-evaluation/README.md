# v3 Standalone Evaluation Project — Documentation Index

Spec: [docs/superpowers/specs/2026-04-26-v3-evaluation-design.md](../superpowers/specs/2026-04-26-v3-evaluation-design.md)

## Phase 0 — v2 Lessons Catalog ✅ DONE
- [phase-0-v2-lessons-catalog.md](phase-0-v2-lessons-catalog.md) — single constraint document for all subsequent phases

## Phase 1 — Universe Extension (data engineering) ✅ DONE
- Data audit: [../superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md](../superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md) — §17 = Approved-for-Tier-2-research-with-caveats
- v0.2 minute-bar parquet: 143/147 tickers (97.3%) × 36 trading days × 1.93M rows; written to `pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet`
- Run manifest (§13A.1): `pipeline/data/research/etf_v3_evaluation/phase_1_universe/manifest.json`
- §13 reconciliation: `reconciliation_report.json` — population pass, strict fail (6/178 rows from §10 adjustment mismatch)
- §14 contamination map: `contamination_map.json` — insider channel (95 hits / 19 tickers / 36 days); bulk/news/earnings empty (Phase 2 follow-up)

## Phase 2 — Comprehensive Backtest
- Plan written after Phase 1 completes.

## Phase 3 — Forward Shadow
- Plan written after Phase 2 completes.

## Phase 4 — Attribution Catalog & Go/No-Go
- Plan written after Phase 3 window closes.
