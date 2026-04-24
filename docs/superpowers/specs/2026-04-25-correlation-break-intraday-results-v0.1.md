# Intraday Correlation-Break Replay — v0.1 Results (FAIL)

**Date:** 2026-04-25
**Pre-registration anchor:** commit `10a39a8` — `docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis-v0.1.md`
**Sector map anchor:** commit `10a39a8` — `docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis-v0.1-sector-map.json`
**Artefacts:**
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet` (gated, n=478)
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet` (ungated, n=696)
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_summary.json`

**Code:** `pipeline/autoresearch/intraday_break_replay_v01.py`

---

## 1. Verdict

**FAIL** by the §7 pre-registered rule.

v0.1 thesis §7 (FROZEN before any results computed):

```
FAIL if gated α_mean < 20 bps OR p ≥ 0.10 (cluster-robust, two-sided, vs 0).
WEAK if 20 ≤ α_mean < 40 bps with p < 0.10.
PASS if α_mean ≥ 40 bps AND p < 0.05 AND hit_alpha ≥ 50%.
H1b (gate adds value) needs (gated − ungated) α_mean ≥ +25 bps.
```

Observed on the 30-day in-sample window:

| Quantity | Value |
|---|---|
| Gated α_mean | **−22.35 bps** |
| Gated SE (cluster-robust, by trade_date) | 6.06 bps |
| Gated t vs 0 | **−3.69** (p ≈ 0.0002 two-sided) |
| Gated t vs +40 bps (H1 bar) | −10.29 |
| Gated hit_alpha | 38.1% |
| Gated avg net P&L | −18.0 bps |
| Ungated α_mean | −25.23 bps |
| Gate lift (gated − ungated) | **+2.88 bps** |
| H1 (α ≥ +40 bps) | **REJECTED** |
| H1b (gate ≥ +25 bps over ungated) | **REJECTED** (lift is +2.88 bps, not 25 bps) |

The sign of α is wrong and the gate adds essentially nothing. The strategy is not just weak — it is significantly negative-α with high confidence.

## 2. Sample

| Slice | Value |
|---|---|
| Window | 30 trading days (2026-03-12 → 2026-04-23) |
| Trigger universe | 150 F&O tickers mapped to NSE sector |
| Sigma gate | `z ≥ 1.5` (absolute), LAG geometry only |
| Gate | sector opposing move ≥ 0.3% blocks the trigger |
| Intra-hold | SECTOR_FLIP at 0.5% opposing since entry |
| Exit ladder | STOP (sigma fade) → Z_CROSS → SECTOR_FLIP → T1_CLOSE @ 09:43 next day |
| Cost | 20 bps round-trip |
| Clusters (trade_date) | 27 |

The window came in short of the pre-registered §5.3 target (60 trading days → ≥ 600 clusters) because only 30 days of 1-minute bars are retrievable from Kite at this moment. The ungated arm delivers n=696 > 600, so statistical power is not the binding constraint for rejecting H1; the gated arm at n=478 is still more than adequate to reject +40 bps at t = −10.

## 3. Stratifications

### 3.1 By direction (gated)

| Dir | n | α_mean (bps) |
|---|---|---|
| SHORT | 398 | −15.14 |
| LONG | 80 | −33.80 |

Longs (mean-reversion from negative sigma) fare worse than shorts, consistent with an upward-drifting window. Neither is positive.

### 3.2 By regime (gated)

| Regime | n | α_mean (bps) |
|---|---|---|
| **RISK-OFF** | 188 | **−4.13** |
| CAUTION | 123 | −24.55 |
| RISK-ON | 70 | −25.71 |
| EUPHORIA | 50 | −29.57 |
| NEUTRAL | 47 | −35.17 |

RISK-OFF is the only regime where the gated strategy is close to breakeven. Even there α is still negative. User question during design — *"does regime have a play?"* — answer: **yes, but only as a damper, not a generator**. No regime slice clears the §7 bar.

### 3.3 By sigma bucket (gated)

| Bucket | n | α_mean (bps) |
|---|---|---|
| mild (1.5 ≤ \|z\| < 2.5) | 283 | −17.67 |
| rare (2.5 ≤ \|z\| < 3.5) | 116 | −30.82 |
| extreme (\|z\| ≥ 3.5) | 79 | −1.94 |

Extreme sigma is close to breakeven but not positive. The "pent-up demand" mechanism from §2 does not deliver the expected monotonic payoff in sigma.

### 3.4 By exit reason (gated)

| Exit | n | α_mean (bps) |
|---|---|---|
| Z_CROSS | 183 | +4.17 |
| T1_CLOSE | 110 | −0.25 |
| SECTOR_FLIP | 133 | −26.41 |
| STOP | 43 | −130.89 |
| SKIP_NO_NEXT_DAY | 9 | — (last-day boundary) |

Natural z-crossings and T1 time-outs are essentially flat. All of the damage lives in STOP (trend-following losses from sigma expansion past 1.5× entry) and SECTOR_FLIP (the sector permission slot *withdraws consent* intraday). The intra-hold SECTOR_FLIP rule did not protect the book — it signed losing trades at roughly the typical negative α for the sample.

### 3.5 By sector (gated)

Top and bottom sectors (n ≥ 15):

| Sector | n | α_mean (bps) |
|---|---|---|
| **NIFTY OIL AND GAS** | 23 | **+29.81** |
| NIFTY PHARMA | 45 | −3.57 |
| NIFTY FMCG | 32 | −4.66 |
| NIFTY PSE | 63 | −5.83 |
| NIFTY IT | 22 | −14.16 |
| NIFTY ENERGY | 36 | −15.27 |
| NIFTY CONSR DURBL | 22 | −16.27 |
| NIFTY BANK | 30 | −19.76 |
| NIFTY METAL | 37 | −29.01 |
| NIFTY REALTY | 17 | −29.50 |
| NIFTY PSU BANK | 12 | −31.73 |
| NIFTY FIN SERVICE | 77 | −32.84 |
| NIFTY AUTO | 35 | −37.18 |
| NIFTY INFRA | 27 | −42.20 |

**NIFTY OIL AND GAS is the only sector with positive α at n ≥ 15.** It is a 23-trade pocket. Per §9 falsifier discipline, we do NOT promote it out of this run. It is recorded as a candidate for pre-registered follow-up.

## 4. H1b (gate adds value) — detail

Gated − ungated α_mean = −22.35 − (−25.23) = **+2.88 bps**. Bar: ≥ +25 bps.

The gate successfully filters out triggers where the sector is already opposing (it drops n=696→n=478, killing ~31% of triggers), but the kept set performs only marginally better than the full set. The sector-permission mechanism described in §2 of the thesis is not operative at the magnitudes we hypothesised.

## 5. Reconciliation with the live 4-day sample

The live Phase C overnight book (Apr 17 – Apr 24) showed average α-vs-sector of +2.44% (23 trades). The 30-day backtest shows −0.22%. The gap is >25× too large to be sampling noise at n=23.

Most plausible explanations, in order:
1. **Q4 FY26 earnings season.** Forensic check (`C:/tmp/phase_c_news_scan.py`) found 9 of 17 big winners in the live book had Q4 earnings or earnings-adjacent catalysts inside the hold. Earnings weeks produce oversized drift that an opportunistic σ-trigger captures; the 30-day backtest window (Mar 12 – Apr 23) spans normal pre-earnings trading.
2. **Regime mix.** The live 4 days were majority RISK-OFF (the least-bad regime here). RISK-OFF alone in the backtest is only −4 bps — still negative, but much better than the other four regimes.
3. **Small-sample variance.** The standard deviation of daily α is ~±35 bps/trade; 23 trades over 4 days gives a 2σ band of roughly ±150 bps. The live +244 bps is a >3σ excursion from the backtest mean.

**Working interpretation:** the live P&L was largely an earnings-season artifact amplified by a favourable regime mix. It is not repeatable evidence of the pent-up-demand-plus-sector-permission mechanism.

## 6. Power caveats

- 30 days × 27 unique trade-date clusters is below the §5.3 target of ≥ 600 clusters. Cluster count matters for inferring the *negative* conclusion's robustness; we have enough for H1 rejection at t = −10 but the sector-level slices (n=12…77 per sector) are underpowered for individual sector claims.
- 1-minute bar retention on Kite capped at ~30 trading days; revisiting this with a full 60-day window requires a bar store (already flagged as follow-up to Phase C).
- Cluster-robust SE was computed at the trade_date level. Intra-day autocorrelation from multiple concurrent triggers per day is absorbed by the cluster; cross-day autocorrelation is weak enough to ignore over 27 clusters.
- The final day (2026-04-24) has no next-day bars available (regime_history ends 2026-04-23); 9 triggers classified SKIP_NO_NEXT_DAY are dropped from α aggregates.

## 7. What we keep / what we drop

### Drop (do NOT promote)
- v0.1 in its pre-registered form. The §7 verdict is FAIL and the experiment is closed under §11 integrity rules — the rule was frozen at commit `10a39a8` before any v0.1 output existed.
- The sector-permission gate as currently specified (0.3% opposing at entry, 0.5% SECTOR_FLIP intra-hold). The 2.88 bps lift does not justify the implementation cost or the ~31% trigger-count haircut.

### Candidate follow-ups (pre-registered, NOT launched here)
- **Earnings-week exclusion.** Rerun gated strategy with triggers dropped when any ticker in the basket has earnings within ±2 trading days. If this flips alpha positive, earnings-week effect is confirmed as the live driver (and the strategy reclassifies as an earnings-calendar signal, not a sigma+sector signal).
- **NIFTY OIL AND GAS isolation.** +29.81 bps at n=23 is suggestive but at the edge of noise. Pre-register a sector-specific test with a pre-committed sample-size target before any claim.
- **RISK-OFF isolation.** −4 bps at n=188 is the only regime that does not lose badly. Not PASS-worthy, but worth testing with a regime-gated version if we ever revisit.
- **Widening the gate.** The 0.3% threshold was a guess. A grid over (0.2%, 0.5%, 1.0%) at entry plus (0.3%, 0.7%, 1.2%) intra-hold would quantify whether gate lift is a monotonic function of strictness. To stay within pre-registration rules, this must be a fresh spec on a held-out window.

None of the above are promoted. They are logged here so that if we reopen the Phase C line, we start from pre-registered candidates rather than in-sample digging.

## 8. Operational implications

- **Phase C live shadow remains disabled for v0.1.** The pre-registered thesis FAILED; the live shadow ledger should not book new Phase C trades under this mechanism.
- **F3 Phase C live shadow** (the separate OPPORTUNITY hypothesis forward test, docs/research/phase-c-validation/) is unaffected by this verdict — different hypothesis, different pre-registration anchor (`#107`, not this spec).
- The 4-day live P&L that motivated v0.1 is treated as a cautionary example of chasing a 4-day sample. The §9 identification threats list (earnings contamination, regime contamination, sector-basket overlap) was written into the pre-reg specifically to defang that pattern; the backtest confirmed the pre-reg was right to be suspicious.

## 9. Pre-registration integrity statement

- Thesis and sector map were committed at `10a39a8` on 2026-04-25 **before** any v0.1 backtest was executed.
- No v0.1 parameters were changed between pre-reg commit and this results doc.
- Verdict rule (§7) was applied as frozen. The RISK-OFF and NIFTY OIL AND GAS pockets are called out here as *observations* only, not as slice-PASS verdicts.
- Follow-up candidates in §7 will require a fresh pre-registration on a held-out window before any promotion.

---

*Experiment closed.*
