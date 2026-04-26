# NEUTRAL Regime Tradability Slice — H-001 Mechanical Engine

**Generated:** 2026-04-26 19:32 IST
**Universe:** 478 GATED 4σ correlation breaks over 27 trade-dates (2026-03-12 → 2026-04-23)
**Source:** `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet`
**Origin:** Task #51 — "is the regime gate (regime != NEUTRAL) ever wrong about a NEUTRAL day being un-tradable?"

## Setup

The H-2026-04-26-002 hypothesis is that the regime gate (`regime != NEUTRAL`) improves the unconditional H-001 sigma-break rule. NEUTRAL days are filtered out. This study asks: **what happens when a NEUTRAL-day trade DOES survive the sector-confirmation gate?** Are those NEUTRAL trades actually tradable?

The replay parquet has the SECTOR-CONFIRMATION gate (§5.2 of mechanical-v1 spec) applied — only trades where the sector is NOT moving against the fade direction get in. 47 of those 478 gated trades happened on production-v2-NEUTRAL days.

## Headline by regime (cluster-robust at trade_date)

| Regime | n trades | n dates | avg gross bps | net bps | hit rate | cluster mean ± SE bps |
|---|---|---|---|---|---|---|
| EUPHORIA | 50 | 6 | -12.7 | -32.7 | 56.0% | -5.1 ± 18.2 |
| RISK-ON | 70 | 5 | +14.1 | -5.9 | 54.3% | +19.7 ± 37.7 |
| **NEUTRAL** | **47** | **5** | **-3.2** | **-23.2** | **57.4%** | **-9.8 ± 11.0** |
| CAUTION | 123 | 7 | -33.0 | -53.0 | 43.9% | -31.1 ± 10.6 |
| RISK-OFF | 188 | 4 | +25.6 | +5.6 | 50.5% | +3.1 ± 44.4 |

## Direction asymmetry inside NEUTRAL (n=47)

| Direction | n | avg gross bps | comment |
|---|---|---|---|
| LONG | 26 | **+12.7** | Modestly tradable on NEUTRAL days |
| SHORT | 21 | **-22.9** | Loses money on NEUTRAL days |

This is the OPPOSITE asymmetry from non-NEUTRAL regimes (where SHORT carries the P&L and LONG loses). On NEUTRAL days the mean-reversion fade flips direction.

## Sigma-bucket breakdown for NEUTRAL

| Bucket | n | avg gross bps |
|---|---|---|
| rare (≥3.5σ) | 6 | -68.1 |
| mild (2-3σ) | 41 | +6.3 |

Mild fades on NEUTRAL days are roughly break-even gross; rare fades on NEUTRAL days lose 68 bps. The rare-fade deterioration is consistent with the broader 60d_v0.1 result — extreme breaks on NEUTRAL days lack the regime tailwind.

## Exit-reason breakdown for NEUTRAL (the key signal)

| Exit | n | n positive | avg gross bps |
|---|---|---|---|
| Z_CROSS | 24 | 20 | **+41.4** |
| T1_CLOSE | 12 | 7 | **+41.2** |
| SECTOR_FLIP | 6 | 0 | -110.3 |
| STOP | 3 | 0 | -301.6 |
| SKIP_NO_NEXT_DAY | 2 | 0 | -35.3 |

**Z_CROSS exits return +41 bps on 24 NEUTRAL-day trades with 83% positive rate.** This is the clean mean-reversion-completes signal — the residual crosses zero before any other exit fires.

## Findings

### 1. NEUTRAL days are NOT a uniform "no-trade" zone

The naive H-002 framing treats NEUTRAL = "skip everything." The data show that NEUTRAL-day trades come in two distinct modes:

- **The 24 Z_CROSS-exit trades:** +41 bps avg, 83% hit rate. These are trades where the residual completes its mean-reversion within the trading day.
- **The 9 SECTOR_FLIP/STOP/SKIP trades:** -180 bps avg combined. These are trades where the regime drifts during the holding period.

The Z_CROSS signal isn't predictable in advance, but the EXIT REASON is.

### 2. LONG side is mildly tradable on NEUTRAL days

26 LONG trades on NEUTRAL days returned +12.7 bps avg. This contradicts the broader data where LONG is the losing direction (-7.7 bps in v2_pass cohort). The reason is likely the smaller sample but it could reflect a genuine NEUTRAL-day asymmetry: when there's no regime tailwind, the fade-down (SHORT) loses its edge but the fade-up (LONG) survives because it's mean-reverting against retail FOMO buying.

n=26 is small — needs validation with more NEUTRAL days.

### 3. The H-002 gate has a marginal cost

By filtering out 47 NEUTRAL trades that returned -3.2 bps gross / -23.2 bps net, H-002 is leaving roughly -150 bps of NET P&L on the table per 60-day window (small win for being in the rule, since net is firmly negative).

But it's also leaving the +41 bps Z_CROSS subset on the table. A "cleverer" gate would be:
- NEUTRAL day + LONG direction + mild bucket → keep
- NEUTRAL day + SHORT direction → skip
- NEUTRAL day + rare bucket → skip

This would require a forward test before going into production.

## Implications for H-002 (regime-gated rule)

The H-002 hypothesis (regime gate filters NEUTRAL days) is well-supported as a P&L-improver — net P&L on NEUTRAL trades is -23 bps. **But it's leaving a tradable subset on the table.** A conditional gate ("NEUTRAL days are skip UNLESS LONG and mild") might capture more edge.

This is a candidate refinement, NOT a re-run of H-002. The single-touch holdout window (2026-04-27 → 2026-05-26) is reserved for the H-002 gate AS REGISTERED. Refinements need their own forward test.

## Files

- This verdict: `pipeline/data/research/etf_v3/2026-04-26-neutral-tradability.md`
- Source data: `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet`
- Source summary: `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_summary.json`

## Open threads

- Validate LONG/mild NEUTRAL-day positive bias on additional forward data (need 30+ NEUTRAL trade-dates)
- Investigate whether Z_CROSS-exit predictability has a leading indicator at trigger time (sector momentum? PCR direction?)
- Consider H-2026-05-XX-001: conditional NEUTRAL-day rule (LONG + mild only)
