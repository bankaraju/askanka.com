# Sector × regime behavior table (Phase A-Sector) — design (2026-04-30)

**Status:** PRE_REGISTERED design. Implementation pending.
**Author:** Bharat Ankaraju + Claude
**Predecessor:** `pipeline/autoresearch/reverse_regime_analysis.py` (stock-level Phase A) + `pipeline/research/sector_panel/` (canonical sector panel built today).

## Motivation

The architecture is exogenous-regime → endogenous-sector-response:

```
INPUTS                          STATE                    OUTCOMES
─────────                       ──────                   ─────────
28 global ETFs       →     5 regimes        →     ?  ← MISSING
+ macro features          (NEUTRAL ~80%)
```

Phase A reverse_regime_analysis maps F&O **stocks** against regime transitions. The corresponding **sector** mapping does not exist. Per user observation 2026-04-30: *"if we use the regime through ETF and within the regime if we can find out what sectoral indices do what at what times — that is what we were doing"*. Half right. The architecture supports it. The table doesn't yet exist.

## What this study does NOT do

- **Does not** modify the regime classifier — sectors stay out of the input vector.
- **Does not** generate trade signals — discovery-only, descriptive matrix.
- **Does not** require new data — reads canonical sector_panel + reconstructed regime_history.

## What it DOES produce

A 22-sector × 5-regime × 8-time-bucket × 5-metric **descriptive matrix**:

```
For each (sector, regime, time_bucket):
  - mean daily log return
  - hit rate (% of days positive)
  - return volatility (annualized)
  - max drawdown
  - Sharpe (risk-adjusted)
```

Time buckets:
1. Open (09:15-09:30) — opening drift
2. Morning (09:30-11:00) — RTH momentum window
3. Late morning (11:00-12:30)
4. Lunch (12:30-13:30)
5. Afternoon (13:30-14:30) — pre-cutoff
6. Close (14:30-15:30) — final hour
7. Overnight (15:30 → next day 09:15)
8. Full day (09:15 → 15:30)

For the 5y daily panel, all 8 are computable. Intraday buckets need minute-bar reconstruction (already available for the 60-day Kite cache; 5y intraday needs piecemeal via the 1-min cache rolling forward).

## Hypothesis under test (per cell)

**Not a hypothesis — descriptive only.** This is the missing brain layer, not a trade-promotion test. Cells that look interesting feed into NEW hypotheses (e.g., "Pharma in RISK-OFF regime at the open is positively asymmetric") which then go through the full single-touch holdout pipeline.

## Pre-locked design

| Lock | Value | Reason |
|---|---|---|
| Sector universe | 22 sectors from canonical panel | already audited |
| Regime tape | reconstructed daily regime label using V3 CURATED-30 weights, point-in-time | per audit |
| Daily window | 5 calendar years (2021-04-23 → 2026-04-22) | matches sector_panel |
| Intraday window (where available) | 60 trading days from Kite 1-min cache | rolling, current limit |
| Bootstrap | 200 random 252-day windows per (sector, regime) for stability | per protocol |
| Verdict bar (for promotion to hypothesis) | mean > 0 AND hit > 55% AND Sharpe > 0.5 AND bootstrap stability ≥ 70% | strict, matches sector_correlation study |
| Anti-data-snooping | the time-bucket grid + sector list + regime tape are FROZEN at study start | binding |

## Outputs

- `pipeline/data/research/sector_regime/sector_regime_matrix_<date>.csv`
- `pipeline/data/research/sector_regime/sector_regime_matrix_<date>.parquet`
- `pipeline/data/research/sector_regime/findings_<date>.md` — plain-English readout per regime

## Decision tree at the end

| Result | Next step |
|---|---|
| ≥1 (sector × regime × time-bucket) cell passes verdict bar | Register one or more new hypotheses (e.g., `H-2026-05-NN-sector-RR-TB`) for forward holdout tests |
| Zero cells pass | Document as null — sectors don't differentiate by regime over the past 5y window |

## Why this is the missing brain layer

Today the system has:
- Regime → 5 zones ✓
- Regime → top stocks (Phase B daily ranker) ✓
- Stock → correlation breaks within sector (Phase C) ✓
- **Regime → sector behavior** ← MISSING

Adding this closes the architectural loop. Once cells start passing verdict, the existing 13 INDIA_SPREAD_PAIRS baskets can be re-architected as data-primary + news-confirmation: instead of "fire on `escalation` keyword", it becomes "fire when (regime is X) AND (sector A in time bucket Y has historically had hit rate Z%) AND (today's data confirms position vs that historical mean)" — with news as optional reassurance.

## Honest expectation

The 5y window includes only ONE major regime transition (post-COVID NEUTRAL → escalating-volatility). Most cells will be dominated by NEUTRAL since NEUTRAL is 80% of days. RISK-OFF / EUPHORIA cells will be small-n and likely fail the verdict bar.

The most-likely-passing cells:
- Pharma in RISK-OFF (defensive premium)
- IT_Services in RISK-ON (cyclical lift)
- Banks in EUPHORIA (credit demand surge)
- Power_Utilities in NEUTRAL low-vol (steady-state)

The most-likely-failing:
- Anything in EUPHORIA (n too small)
- Anything in lunch-window (intraday flat)
- Sectors that are part of the mega-cluster (20/22 are correlated — nothing differentiates)
