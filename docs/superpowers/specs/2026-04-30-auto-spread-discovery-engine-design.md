# Auto Spread Discovery Engine (ASDE) — design (2026-04-30)

**Status:** DESIGN. v0 enumeration + decay monitor ship in this commit; v1 backtest-driven proposer ships in a follow-up after the news-source decision.
**Author:** Bharat Ankaraju + Claude
**Trigger:** user directive 2026-04-30 — *"hard-coded spread engine is stale, alpha decays, Defence vs IT is today's king and won't be next quarter's. Build a continuous discovery loop."*
**Predecessor:** `INDIA_SPREAD_PAIRS_DEPRECATED` (13 hand-curated baskets, 4 killed by Task #24, 9 still live in paper).

## Why this exists

Task #24 ran a formal 5y backtest on the 13 hand-curated `INDIA_SPREAD_PAIRS_DEPRECATED` baskets and produced exactly **1 PASS cell** (Reliance vs OMCs / EUPHORIA / 5d) plus a handful of borderline cells. Hand-curating spread ideas and waiting 5y to validate them is not a sustainable alpha pipeline. Two structural problems:

1. **Coverage gap.** ~25 sectors × ~25 sectors = ~300 directional pairs. We tested ~13 of them — 4% coverage of the obvious spread space. The other 96% may contain higher-Sharpe edges that nobody has hand-picked yet.
2. **Decay blindness.** Once a basket goes live, we have no automated guardrail that says "your live Sharpe is now 30% of in-sample, the trade has decayed, archive it." We discover decay the slow way — by losing money for months.

**ASDE addresses both.** Weekly proposer enumerates the full sector-pair × regime × hold space, runs the same Task #24 5-gate validator, ranks promotable cells, and feeds them into the existing pre-registration → forward-shadow → live ladder. Daily decay monitor on every live basket triggers a kill-switch when forward Sharpe falls below threshold.

## What ASDE is NOT

- **Not** an autotrader. It cannot promote a basket to live without explicit Bharat-side review at the pre-registration step. The user is the gate.
- **Not** an IS-cherry-picker. The 5-gate validator (mean / t / hit / MaxDD / bootstrap + BH-FDR multiplicity correction across the full enumerated family) is the only path to PASS. The grammar — and therefore the family size — is frozen at design time per backtesting-specs §10.4.
- **Not** a replacement for the autoresearch v2 single-feature proposer (`pipeline/autoresearch/regime_autoresearch/`). That one proposes single-feature long/short cells. ASDE proposes structured **sector-pair baskets**. They share the BH-FDR machinery but operate in disjoint hypothesis spaces.

## The two halves

### Half A — Discovery (weekly Sunday)

```
canonical_fno_research_v3.json  →  sector_a × sector_b enumeration  →  liquidity filter
                                                       │
                                                       ▼
                                              (regime × hold × side) cell
                                                       │
                                                       ▼
                              5y panel backtest (PIT regime tape, 20bp costs)
                                                       │
                                                       ▼
                          5-gate validator + BH-FDR(q=0.10) across full family
                                                       │
                                                       ▼
                  ranked candidate report  →  Bharat reviews top-K  →  pre-register
```

### Half B — Decay (daily 16:00 IST)

```
for each LIVE basket (4 pre-registered + 9 deprecated active):
    rolling_30d_sharpe   = compute from forward shadow ledger
    in_sample_sharpe     = frozen at pre-registration time
    decay_ratio          = rolling / in_sample
    verdict              = HEALTHY  if ratio >= 0.7
                           WATCH    if 0.3 <= ratio < 0.7
                           DECAYING if 0.0 <= ratio < 0.3
                           KILL     if ratio < 0.0  (forward Sharpe negative)
    if KILL:
        emit Telegram alert + flag basket for archive review
```

## Pre-locked design — Half A (Discovery)

| Lock | Value | Reason |
|---|---|---|
| Pair universe | sector_a × sector_b from `pipeline/config/canonical_fno_research_v3.json` sector taxonomy | data-side single source of truth |
| Per-side leg count | top-3 by 60d ADV (close × volume mean) | avoid illiquid legs that backtest well but can't trade |
| Construction | LONG sector_a top-3 vs SHORT sector_b top-3, equal-weight, dollar-neutral | matches existing INDIA_SPREAD_PAIRS shape |
| Window | 5y (2021-04-23 → 2026-04-22), trading-day-aligned | matches Task #24 |
| Regime tape | PIT V3 CURATED-30 (reconstructed for hindsight years using only point-in-time data) | per data-validation policy §11 |
| Cell family | (pair × regime × hold × direction) — 300 pairs × 5 regimes × 3 holds × 2 directions = 9,000 cells before liquidity filter, ~1,500-2,000 after | enumerated and FROZEN at code commit |
| Hold horizons | 1d, 3d, 5d | matches Task #24 |
| Costs | 5bp per leg per turn = 30bp round-trip on a 6-leg basket | matches Task #24 |
| Stops | mechanical max-loss -3% per basket | matches live engine |
| Multiplicity | BH-FDR @ q=0.10 across the full enumerated family | per autoresearch v2 standard |
| Bootstrap | 200 random 252-day windows per cell | per backtesting-specs §11 |
| Verdict bar | mean post-cost > 0 AND t > 2 AND BH-FDR survives AND bootstrap >= 60% AND hit-rate >= 55% AND MaxDD/notional <= 8% | strict, mirrors Task #24 |
| Anti-data-snooping | sector taxonomy + leg-count + hold grid + verdict bar are FROZEN at this commit; no post-look refinement | binding |
| Promotion path | candidate cell that passes 5/5 gates → human review → optional pre-register entry into `hypothesis-registry.jsonl` → standard single-touch holdout | per backtesting-specs §10.4 |
| Cadence | weekly Sunday 02:00 IST (after AnkaPatternScannerFit) | offline batch, GPU-light, ~30-60min |

### Why pair-aggregate, not stock-level

The autoresearch v2 single-feature proposer covers stock-level long/short edges via `top_k(feature)` constructions. ASDE is intentionally narrower — it tests the **sector-vs-sector spread thesis** specifically, because that's what Bharat's domain mental model has been built around (PSU vs Private Banks, EV vs ICE Auto, Defence vs IT, …). Sector-pair baskets are also more robust to single-stock idiosyncratic news — the 6-leg construction averages it out. ASDE and the v2 single-feature proposer are complementary, not redundant.

## Pre-locked design — Half B (Decay monitor)

| Lock | Value | Reason |
|---|---|---|
| Live basket inventory | 4 pre-registered (RELOMC, DEFIT-NEUTRAL, DEFAU-RISKON, PDR-BNK-NBFC) + 9 deprecated-but-active (post-kill-switch survivors of INDIA_SPREAD_PAIRS) | union of `hypothesis-registry.jsonl` PRE_REGISTERED + `_india_spread_pairs()` runtime output |
| In-sample Sharpe | frozen at pre-registration time, written into registry entry | binding — never recomputed |
| Forward window | rolling 30 trading days from forward shadow ledger | short enough to detect decay, long enough to filter noise |
| Verdict thresholds | HEALTHY ratio>=0.7, WATCH 0.3-0.7, DECAYING 0-0.3, KILL <0 | matches industry decay-monitor practice |
| Min n for verdict | 10 closed trades in rolling window | underpowered cells return INSUFFICIENT_N (no verdict) |
| Cadence | daily 16:00 IST after AnkaEODTrackRecord | reads closed trades from forward shadow ledgers |
| Output | `pipeline/data/research/alpha_decay/decay_<date>.json` + Telegram alert on any KILL transition | watchdog-grade |
| Action on KILL | flag for archive review; engine continues to record forward shadow until Bharat archives | no auto-disable — user is the gate |

## Why now (and not "wait until v2 single-feature proposer is mature")

Three reasons stack:

1. **Decay monitor is independent of proposer.** It just reads existing forward shadow ledgers. Building it now buys us early warning on the 4 brand-new pre-registered baskets that started today.
2. **Discovery half is the natural extension of Task #24.** We just ran the 5-gate validator on 234 cells and produced 1 PASS. Generalizing to ~1,500-2,000 cells is a matter of widening the enumeration loop, reusing the same backtester. The cost is compute, not new design.
3. **The hand-curated era is provably exhausted.** 1 PASS in 234 cells = 0.4% hit rate. Random would be ~10% under BH-FDR(q=0.10). We are below random — the hand-curated set is *anti-selected* for survivors. Time to widen the search.

## Roadmap

- **v0** (this commit): Decay monitor + sector-pair enumeration + cardinality bookkeeping. No backtest call yet — the candidate enumeration is what we lock first, because it determines the BH-FDR denominator.
- **v1** (next 2 weeks): Wire enumeration to a batch backtest runner reusing `pipeline/research/india_spread_pairs_backtest/` machinery. Output ranked candidate report. Manual review.
- **v2** (post-news-source decision): Add news-conditional Mode A in addition to trigger-agnostic Mode B. Requires resolved news provenance (Tasks #23/#35/#36/#39).
- **v3** (post-pilot): If v1+v2 produce 3+ PASS cells beyond the hand-curated set, promote ASDE to weekly clockwork (`AnkaASDEFit Sun 02:30 IST`). Until then, manual.

## Anti-pitfalls

- **No regime peeking at proposal time.** The proposer enumerates the FULL pair × regime × hold space. Selection by "this regime looks easy" is forbidden — that's exactly what hand-curation did wrong.
- **No look-ahead in PIT regime tape.** `etf_v3_curated_signal.py` outputs are computed using only data available at end-of-day d for trading on day d+1. The PIT tape file is a separate artifact, never the runtime regime CSV (`regime_history.csv`) which contains hindsight v2 weights — see `reference_regime_history_csv_contamination.md`.
- **No basket re-runs after holdout starts.** Once pre-registered, the cell is single-touch per backtesting-specs §10.4. ASDE does not re-test cells already in registry.
- **No fudging cost model.** 30bp round-trip is the floor. If a candidate only PASSes at 5bp/turn, it doesn't pass.

## Acceptance gates (this commit)

1. Design doc committed (this file).
2. Decay monitor module + tests committed; runs cleanly against today's forward shadow ledgers.
3. Sector-pair proposer enumeration module + tests committed; emits frozen candidate list with cardinality count.
4. Strategy gate kill-switch passes — no `*_engine.py` / `*_backtest.py` / `*_signal_generator.py` filenames added without registry entries (use `monitor.py` / `proposer.py` / `discovery.py` filenames).
5. CLAUDE.md schedule section unchanged — no new clockwork tasks until v3.

## What this commit does NOT ship

- v1 backtest call — needs the proposer enumeration to be locked first.
- AutoPromotion to live — explicit user gate at pre-registration step.
- Telegram alert plumbing — scaffolding only; live wire-up after Bharat sees the first decay report.
- News-conditional Mode A — pending news source decision (EODHD probe vs Moneycontrol vs incumbent scrapers).
