# Forensic Card v2 — 4σ Correlation-Break Decomposition (with private-channel evidence)

**Source:** events.json from compliance_H-2026-04-23-001 + bulk_deals/ + insider_trades/
**Filter:** |z| ≥ 4.0 on T AND |z| ≥ 3.0 on T-1, same sign
**Generated:** 2026-04-25T10:31:58.208653+00:00
**Total events:** 1774

## Coverage of new channels

- Events with bulk-deal data observed: 0 / 1774 (0.0%)
- Events with insider-trade data observed: 1774 / 1774 (100.0%)

Bulk-deal data is forward-only from 2026-04-24 — historical events get NULL.
Insider data covers 2021+ via NSE corporates-pit endpoint.

## v1 baseline (unchanged)

- earnings within T-3..T+1 window: **31.3%**
- sector index also moved (|z|≥1.5 same-sign): **9.4%**

## 4-quadrant earnings × sector decomposition

- earnings + sector spike: **4.5%**
- earnings only: **26.8%**
- sector spike only: **9.5%**
- neither (true idiosyncratic): **59.2%**

## Insider/promoter channel

- Insider trade on T (any category): **4.5%** of 1774 observed events
- Insider trade in T-3..T+1 window: **9.8%**
- Promoter/Promoter-Group trade in window: **1.9%**
- Director/KMP trade in window: **1.1%**
- Side alignment with break direction (Buy→UP, Sell→DOWN): **39.6%** of 134 directional matches (remainder = counter-side, suggests filing was for hedging or unrelated)

## Reattributing the v1 'neither' residual

Of the 1051 v1 'true idiosyncratic' events, **1051** have insider-channel coverage.
Of those:
- have an insider trade in T-3..T+1: **10.7%**
- have a promoter trade specifically in the window: **2.5%**
- remain unexplained (no earnings, no sector, no insider): **89.3%**

## Bulk-deal channel (forward-only)

- Events covered by daily-collection era: 0
- Bulk deal on T: **n/a** of covered events
- Bulk deal in T-1..T window: **n/a**

Coverage will grow daily — re-run the card weekly to track.

## Base-rate sanity check

Random-null comparison via `scripts/insider_base_rate_check.py` (1,774 random (ticker, date) pairs from the same ticker set + date range, seed=42):

| | random null | 4σ events | lift |
|---|---|---|---|
| any insider in T-3..T+1  | 9.9% | 9.8% | **0.99x** |
| any promoter in window   | 1.6% | 1.9% | **1.14x** |

**Verdict: insider channel is null.** Insider activity around 4σ correlation breaks is indistinguishable from insider activity on random dates. Side alignment is below 50% (39.6%), reinforcing that PIT filings are not directionally informative for these moves.

## What's left (open question)

Of the 1,774 4σ events:
- 31% explained by earnings, 9% by sector, 5% by both
- 9.8% co-occur with insider trades but at base-rate frequency (no signal)
- **~55–60% remain genuinely unexplained by all four channels.**

Plausible remaining drivers (none yet measurable on historical data):
- News / corporate announcements not in earnings calendar (rating action, regulatory, M&A rumour)
- Bulk/block deal liquidity events (forward-only collection started 2026-04-24)
- Index rebalancing or F&O ban-list entry/exit
- OFS / preferential offerings (partly captured in PIT under 'Preferential Offer' acq_mode — could be split out)
- Residual-model error: peer cohort wrong, regime mis-tagged, beta mis-estimated

## Out of v2 (deferred)

- Historical news log — defer to forward-only collection (3+ months)
- Per-sector FII flow — substitute sector-ETF volume z (not yet wired)
- 5y bulk-deal backfill — not available free from NSE (see memory)
