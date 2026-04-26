# v3 Evaluation — Phase 0: v2 Lessons Catalog

**Date:** 2026-04-26
**Spec:** [2026-04-26-v3-evaluation-design.md](../superpowers/specs/2026-04-26-v3-evaluation-design.md) §4
**Purpose:** Single constraint document referenced by every Phase 1–4 task. Re-read at the start of each phase.

## 1. v2 Discoveries — what we learned from running v2 in production

| # | Discovery | Evidence | Implication for v3 design | Test v3 must pass |
|---|---|---|---|---|
| D1 | regime_history.csv contamination — built with hindsight v2 weights, NOT a production audit trail | `memory/reference_regime_history_csv_contamination.md` | v3 must record zone-as-emitted, not zone-as-rebuilt | Phase 2 backtest reads only zone-as-emitted snapshots; Phase 3 shadow ledger writes zone at the moment of decision |
| D2 | PCR/OI multi-confirmation throttled trades historically | `memory/project_etf_v3_failed_2026_04_26.md` | v3 must not bolt PCR/OI back on as a second gate | Phase 2 marker decomposition does NOT include a PCR/OI marker; if added later requires its own holdout |
| D3 | OPPORTUNITY split into LAG/OVERSHOOT (#107 audit) — pooling masked failure | `memory/project_phase_c_follow_vs_fade_audit.md` | v3 gate must be tested separately on LAG vs OVERSHOOT slices | Phase 2 marker decomposition tables are stratified by LAG/OVERSHOOT; pooled-only verdicts are forbidden |
| D4 | σ bucket × regime coupling — buckets are NOT regime-independent | session 2026-04-26 conversation | v3 evaluation must condition σ buckets on regime | Phase 2 marker decomposition includes σ × regime cross-tab |
| D5 | POSSIBLE_OPPORTUNITY (+41.67pp/328) beat OPPORTUNITY_LAG (−3.30pp/60) — wrong slice was kept live | `memory/project_mechanical_60day_replay.md` | v3 gate granularity must match the actual P&L-bearing slice, not a category label | Phase 2 emits P&L per-slice; Phase 4 catalog flags any case where pooled verdict ≠ slice verdict |
| D6 | Single-touch holdout discipline (§13.1) burned 3 times in April | hypothesis-registry.jsonl entries for H-2026-04-25-001/002, H-2026-04-26-003 | v3 forward-test window must be pre-registered, single-use | Phase 3 pre-registration document SHA-256 hashed before window opens; rerun requires new hypothesis ID |
| D7 | SECTOR_FLIP exit reason is the leak (−69 bps mean, 9% hit, 83-min hold) | `pipeline/data/research/etf_v3/2026-04-26-exit-time-observations.md` | exit-rule changes interact with regime; v3 evaluation must hold exit rule fixed unless explicitly testing it | Phase 2 default exit = TIME_STOP 14:30 + ATR(14)×2 stop; alternative exits require their own marker entry |
| D8 | Z_CROSS in NEUTRAL = +41 bps refinement candidate | `pipeline/data/research/etf_v3/2026-04-26-neutral-tradability.md` | v3-NEUTRAL-day refinements have unexploited room | Phase 2 marker decomposition includes Z_CROSS-conditional sub-marker |
| D9 | Sector dynamics on NEUTRAL days are real — PSU BANK/BANK/PSE/ENERGY/INFRA SHORT-fades win (+200 to +390 bps); AUTO/IT/FMCG lose | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §3 | sector-conditional gating is a credible Phase 2 marker | Phase 2 includes sector-overlay marker with explicit per-sector P&L attribution |
| D10 | ETF coefficient rotation magnitude is a real "regime change marker" — 51.8 std units on 2025-12-30, 37.2 on 2026-04-16 align with v3 zone shifts | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §2 | coef-delta marker should be tested as a second-tier signal | Phase 2 includes coef-delta marker test |
| D11 | 5y vs 3y lookback is +6.3pp pooled OOS edge swing — v3 with longer history is materially better | `pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb1200_curated.json` | v3 evaluation tests 3y vs 5y vs full-panel | Phase 2 walk-forward includes lookback-variant sweep |
| D12 | v3 NEUTRAL gate misapplied to H-001 SHORT engine kills P&L (NEUTRAL gate captures 4.3% of available SHORT P&L) | `pipeline/data/research/etf_v3/2026-04-26-v3-only-60d-verdict.md` §3 | v3 forecasts next-day NIFTY direction; H-001 fades intraday extremes — different time scales | Phase 2 must test v3 zone gate AND v3-direction-prior separately, not assume gate is the right application |

## 2. Meta-lessons — gates v2 (and the spread engine) never had

These are gates that v2 systematically lacked. v3 evaluation treats them as table-stakes.

| # | Gate v2 lacked | Why it mattered | How v3 honors it |
|---|---|---|---|
| M1 | 5y training history | v2 trained on 3y → missed regime cycles; cycle-3 acc was 47% | Phase 2 walk-forward tests 3y / 5y / full-panel lookback variants; pooled OOS edge reported per variant |
| M2 | Data validation policy (§6 registration) | ETF panel was used without §6 audit; bit us when SectorMapper artifacts went missing on Contabo | Phase 1 dataset registration is a HARD gate; Phase 2 backtests refuse to read parquet without §17 Approved-for-Tier-2-research stamp |
| M3 | §13A run-manifest reproducibility | Spread engine results not reproducible — no commit hash, no requirements freeze, no seed disclosure | Every Phase 1+2+3 run produces a manifest with commit, pip_freeze, seed, config, file hashes |
| M4 | §14 hypothesis pre-registration with §14.5 family denominator | ~20 spread variants tested without declaring family — multiplicity denominator was retroactive | Phase 3 hypothesis pre-registered with family denominator declared at lock; Phase 2 family declared at start of marker decomposition |
| M5 | §11A implementation-risk simulation | v2 backtests assumed perfect execution; real Phase C had missed entries unmodeled | Phase 2 runs all 10 §11A.1 failure scenarios (missed entries, missed exits, delayed fills, halts, etc.) |
| M6 | §10.4 single-use OOS | H-001/H-002/H-003 re-tested against same 60d window — 3 holdout burns this month | Phase 3 window single-use; rerun requires new window + new hypothesis ID |
| M7 | §9A parameter fragility | Cadence-sweep verdict was on a single seed; never proved local stability | Phase 2 fragility test mandatory (3 stability conditions per §9A.2) |
| M8 | Cross-source reconciliation (§13) | Kite minute bars never sample-checked against EOD parquet | Phase 1 mandates 5-ticker sample reconciliation (max delta < 0.5%) before §17 acceptance |

## 3. How this catalog is used

- Each Phase 1–4 task references the discoveries (Dn) and meta-lessons (Mn) it honors
- At end of each phase: review this catalog; flag any unresolved discovery/lesson
- Phase 4 final go/no-go must include a per-Dn and per-Mn pass/fail verdict
