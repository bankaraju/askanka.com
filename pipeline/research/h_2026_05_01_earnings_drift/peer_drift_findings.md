# Sector spillover (peer-drift) study — findings 2026-05-01

**Stage A widen #74. Forensic only. NOT a hypothesis. No registry row.**

## Question

When a NIFTY Bank or NIFTY IT name prints earnings, do its sector peers drift in the same direction over T+1, T+3, T+5? If yes, that opens a v2 spread hypothesis (LONG peer-cohort post-BEAT vs SHORT peer-cohort post-MISS).

## Method

- 314 events from `event_factors.csv` (2021-05 → 2024-04, 40-name Banks+IT universe)
- For each event (E, sector, direction), peer cohort = all OTHER names in same sector
- Anchor: peer's last close ≤ event_date; horizons h ∈ {1, 3, 5} trading days post
- Aggregate: mean / median / hit-positive% by direction × sector × regime

5,674 event-peer pairs assembled (254 skipped for missing forward bars).

## Verdict — NEGATIVE: peer drift is NOT a tradeable spillover spread

### 1. BEAT − MISS spread is near zero across all horizons

| Horizon | mean(BEAT − MISS) | median(BEAT − MISS) |
|---|---|---|
| h=1 | −5.8 bps | −0.3 bps |
| h=3 | −22.7 bps | +5.4 bps |
| h=5 | −5.8 bps | −2.3 bps |

**Peer drift is NOT direction-conditional**. After both BEAT and MISS, peers drift in the SAME direction (positive). The "spread trade" hypothesis (LONG-peers-on-BEAT minus SHORT-peers-on-MISS) collapses to zero.

### 2. Sector momentum dominates, with opposite signs in Banks vs IT

| Sector × direction | n events | h5 mean peer ret |
|---|---|---|
| Banks BEAT_LIKE | 86 | +51 bps |
| Banks MISS_LIKE | 90 | +58 bps |
| IT BEAT_LIKE | 74 | −23 bps |
| IT MISS_LIKE | 62 | −27 bps |

Both directions look the same WITHIN sector. **Banks peers go up after any earnings event; IT peers go down.** This is sector-regime momentum, not event spillover.

### 3. Regime breakdown shows mixed direction-conditional structure

| Regime × direction | n | h3 mean peer ret | h3 hit % |
|---|---|---|---|
| NEUTRAL BEAT | 112 | +16 bps | 55% |
| NEUTRAL MISS | 105 | +61 bps | 56% |
| RISK-ON BEAT | 30 | −22 bps | 48% |
| RISK-ON MISS | 27 | −26 bps | 46% |
| CAUTION BEAT | 18 | +55 bps | 54% |
| CAUTION MISS | 13 | −36 bps | 45% |
| RISK-OFF MISS | 3 | −26 bps | 43% |

**CAUTION shows the cleanest direction-split** (BEAT +55 / MISS −36 → +91 bps spread at h=3). But n=18 BEAT and n=13 MISS in CAUTION across 3 years — too thin for inference. Most events are NEUTRAL where the BEAT vs MISS difference is small (+16 vs +61, INVERTED relative to expected — MISS-day peer drift is HIGHER, possibly because MISS names sell off and money rotates into peers).

## Implications for v1 design

1. **v1 single-name LONG cell is the right framing.** Spillover does not amplify the on-the-name signal cleanly.
2. **No v2 peer-spread hypothesis emerges from this evidence.** The cleanest signal (CAUTION-direction-split) is too thin (n=31).
3. **NEUTRAL inversion is interesting** (peer drift after MISS > peer drift after BEAT) — possibly relative-value rotation. But not actionable as a spread; could feed a v2 single-name MISS-day-peer LONG hypothesis if we ever expand SHORT-side coverage.

## Files

- `peer_drift_study.py` — analysis script
- `peer_drift_per_event.csv` — 5,674 rows (event × peer × horizon)
- `peer_drift_summary.json` — aggregated stats
- `peer_drift_findings.md` — this memo

## Next-step decision

Skip v2 peer-spread design. Move on to Stage A widen #75 (large-print pre-event signature) and v1 holdout open 2026-05-04.
