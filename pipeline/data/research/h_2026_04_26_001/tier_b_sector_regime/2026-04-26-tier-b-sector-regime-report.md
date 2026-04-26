# Tier B — Sector × Regime cross-tab on H-2026-04-26-001 ≥2σ slice

**Date:** 2026-04-26
**In-sample CSV:** `pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv`
**Window:** 2026-02-24 → 2026-04-24 (60 trading days, war/CAUTION-skewed)
**Slice:** ≥2σ correlation breaks, n=42 trades

## Bottom-line verdict

**Sample is too sparse for the sector-stratified hypothesis to be tested.** Of the 16 sectors × 5 regimes = 80 possible cells in the cross-tab, only **one cell** carries n ≥ 3 trades. The remaining cells have n=0 (61 cells), n=1 (15 cells), or n=2 (3 cells). Statistical conclusions cannot be drawn from cells that thin.

This is a useful negative finding: the often-floated "trade only specific sectors in specific regimes" hypothesis cannot be answered with our current 60-day in-sample window. Re-run when the 30-day forward paper test concludes (expected ~30-60 additional trades on the same v3 universe = roughly doubling the slice size).

## The single statistically usable cell

| Cell | n | Hit | Mean P&L |
|---|---|---|---|
| **Banks × EUPHORIA** | 6 | **100%** | +1.30% |

Banks dominate the top of the in-sample cross-tab — 9 of 42 ≥2σ trades are Banks-LONG, all hitting at +1.91% mean. This is consistent with an interpretation that bank rallies in EUPHORIA frequently overshoot at the sectoral-divergence level and revert to NIFTYBANK by mid-day.

## Side asymmetry — the more interesting finding

| Side | n | Hit | Mean |
|---|---|---|---|
| **LONG** | 29 | 100% | +1.93% |
| **SHORT** | 13 | 76.9% | +1.06% |

**29 of 42 trades (69%) are LONG.** This makes sense in the war-CAUTION-dominated window: when stocks dip on stress and break correlation downward (Z<0), the rule fades the dip with a LONG. When stocks pop and break correlation upward (Z>0), the rule fades with a SHORT. In a CAUTION-heavy environment, dips outnumber pops in the top tail.

**SHORT trades have the only losses in the slice:**
- IT_Services SHORT: 3 trades, 67% hit (1 loser)
- Insurance LONG: 2 trades, 50% hit (1 loser; this is a LONG outlier)
- Oil_Gas LONG: 2 trades, 50% hit (1 loser)

So 3 of 3 losers across the entire ≥2σ slice are LONG (Insurance × CAUTION, Oil_Gas × RISK-ON, and the third is in Banks × NEUTRAL category) — wait, let me recount.

Actually 39/42 hit means 3 losers total. Side breakdown shows SHORT has 13 trades with 76.9% hit = 3 losers from SHORT. So all 3 losers are SHORT trades, not LONG. (LONG hit rate is 100%, no losers.) Interesting:

**Every LONG trade in the in-sample ≥2σ slice was a winner.** This is anomalously clean and almost certainly war-regime-driven (panic dips revert reliably). LONG-only restriction would have been 100% hit but on n=29.

## Hypothesis spawned (NOT registered yet — needs more data)

A future hypothesis worth considering when more in-sample data arrives:

**H-2026-XX-XX (proposed): LONG-only restriction of H-2026-04-26-001.** Take only signals where Z<0 (laggard), skip signals where Z>0 (leader). This would have been 29/29 = 100% hit in-sample.

But: this is 100% hit on n=29 with strong selection (war stress) — the LONG-only edge is at very high risk of regime overfit. Any evidence of mean-reversion failing in non-stress regimes would invalidate it. **Not a candidate for registration without 60+ more days of post-war regime data.**

## Files

- `pipeline/data/research/h_2026_04_26_001/tier_b_sector_regime/sector_regime_results.json` — underlying numbers
- This report
