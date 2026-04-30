# Bootstrap-aware addendum to findings_2026-04-30 (2026-04-30 22:50 IST)

**Trigger:** Background bootstrap-included re-run (b527z9v4q, started 22:04, completed 22:49) populated `bootstrap_stability_pct` for 195/234 Mode B cells. The 39 INSUFFICIENT_N cells have no bootstrap value (correctly skipped). This addendum records what the bootstrap-aware view changes vs the bootstrap-blind view in `findings_2026-04-30.md`.

## Bootstrap stability distribution

195 cells with values:
- mean: 42.5%, median: 42.5%, std: 26.3%
- 25th pct: 22%, 75th pct: 60%, max: 100%
- 14 cells ≥80% bootstrap

## The 1 PASS cell — confirmed

| Basket | Regime | Hold | n | post-20bp | t | hit | bootstrap | verdict |
|---|---|---|---|---|---|---|---|---|
| Reliance vs OMCs | EUPHORIA | 5d | 28 | +274.6 bps | 4.38 | 75% | **100%** | **PASS** |

The targeted bootstrap I ran earlier (`bootstrap_relomc_pass_cell.py`, 1000 iters, calendar-window) and the full runner (200 iters, panel-window) agree at 100%.

## Cells that the bootstrap reveals as more interesting than first-pass

These cells failed by a single gate but show >80% bootstrap stability — suggesting the underlying alpha is real and persistent, just shy of the multiplicity-corrected bar.

| Basket | Regime | Hold | n | post-20bp | t | hit | bootstrap | verdict | comment |
|---|---|---|---|---|---|---|---|---|---|
| EV Plays vs ICE Auto | EUPHORIA | 5d | 28 | +91.2 | 2.15 | 64.3% | **100%** | FAIL_BH_FDR | NEW: same shape as RELOMC. Sister hypothesis candidate. |
| Defence vs IT | NEUTRAL | 3d | 884 | +29.8 | 2.39 | 52.7% | 98.0% | FAIL_BH_FDR | hit-rate is the binding constraint (52.7% vs 55%). Could promote the 5d sibling (already H-DEFIT-NEUTRAL). |
| Defence vs Auto | NEUTRAL | 3d | 884 | +22.5 | 2.09 | 52.0% | 88.0% | FAIL_BH_FDR | Same family — hit-rate binding. |
| **Defence vs Auto** | **NEUTRAL** | **5d** | **882** | **+47.5** | **3.32** | **53.4%** | **86.5%** | **FAIL_HITRATE** | **NEW**: similar to DEFIT-NEUTRAL, fails hit-rate by 1.6pt. Possible third Defence sister hypothesis. |
| Coal vs OMCs | EUPHORIA | 3d | 28 | +84.9 | 1.68 | 64.3% | 85.8% | FAIL_TSTAT | Underpowered but consistent. |
| Coal vs OMCs | EUPHORIA | 5d | 28 | +122.7 | 1.72 | 64.3% | 81.3% | FAIL_TSTAT | Same. |
| PSU Energy vs Private | RISK-OFF | 5d | 27 | +70.1 | 0.99 | 70.4% | 87.4% | FAIL_TSTAT | Tiny n; high bootstrap on small sample is suspect. |

## What this changes

### EV Plays vs ICE Auto EUPHORIA 5d — possible sister hypothesis

The unconditional basket #12 was killed by Task #34 because mean is -22.7bp post-cost across ALL regimes. But the EUPHORIA-conditional cell is +91bp at 100% bootstrap stability. **Same shape as RELOMC**. Worth registering as `H-2026-04-30-EVAUTO-EUPHORIA` if Bharat agrees.

Caveat: n=28 in 5y means EUPHORIA fires only ~5-6 times/year on this basket. Forward holdout will collect <30 obs in 24 months — single-touch holdout would need n≥10 minimum, auto-extend to 2027 likely needed.

### Defence vs Auto NEUTRAL 5d — third Defence sister?

We already have H-DEFIT-NEUTRAL (Defence vs IT, NEUTRAL, 5d) and H-DEFAU-RISKON (Defence vs Auto, RISK-ON, 5d). The Defence vs Auto NEUTRAL 5d cell shows post +47bp / t=3.32 / hit 53.4% / bootstrap 86.5% — fails hit-rate by 1.6pt only. The NEUTRAL slice of the Defence-vs-Auto basket may itself have alpha.

Decision needed: is this a third Defence hypothesis or are we stretching multiplicity-correction by promoting too many cells from a single 5y backtest?

### Reading: bootstrap is informative but not decisive

The bootstrap distribution centers at 42% with std 26% — meaning a random cell has roughly even odds of >50% stability. >80% is strong but not rare (14/195 = 7.2%). The verdict still rests on the multi-gate AND test (mean + p + hit + MaxDD + bootstrap), where bootstrap is one of five gates.

## Recommendations

1. **Reliance vs OMCs / EUPHORIA / 5d**: PASS confirmed (100% bootstrap). H-RELOMC-EUPHORIA already promoted.
2. **EV Plays vs ICE Auto / EUPHORIA / 5d**: review-and-decide. 100% bootstrap is striking; n=28 is the constraint.
3. **Defence vs Auto / NEUTRAL / 5d**: review-and-decide. 86.5% bootstrap; 1.6pt hit-rate shortfall. If Bharat is comfortable bundling 3 Defence hypotheses, register as `H-2026-04-30-DEFENCE-AUTO-NEUTRAL` with hit-rate gate relaxed to 53% (mirror of DEFIT-NEUTRAL's relaxation, declared as parameter amendment).
4. **No revision** to the kill switch — the unconditional ALL-regime profile of the killed baskets is still negative. The EUPHORIA-conditional sister of EV-vs-ICE-Auto would be a separate forward-only test, distinct from the news-driven parent's death.

## Honest caveat

This addendum was computed AFTER the in-sample backtest run, so the cells flagged here have been "looked at" twice. Per backtesting-specs §10.4 single-touch rule, the in-sample window is consumed; any further filter on these cells (e.g., re-promoting EVAUTO-EUPHORIA after it survived a second look) is post-hoc data-snooping vs the original Task #24 verdict bar. The defensible move: register the borderline cells AS-IS now (no parameter changes vs the bootstrap-revealed evidence), let the forward holdout decide.
