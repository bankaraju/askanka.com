# Forensic Card v1 — 4σ Correlation-Break Decomposition

**Source:** events.json from compliance_H-2026-04-23-001_20260423-150125

**Filter:** |z| ≥ 4.0 on T AND |z| ≥ 3.0 on T-1, same sign
**Note:** T-1 persistence is stricter than spec (|z|≥3 vs intended |z|≥2) — events.json only carries |z|≥3 rows, sub-threshold T-1 z's not recoverable without a panel rebuild.
**Generated:** 2026-04-25T09:49:53.975509+00:00

## Counts

- Total 4σ events with persistence: **1774**
- Of these, persistent at T-1: **48** (2.7%)

### By year
- 2021: 222
- 2022: 329
- 2023: 385
- 2024: 377
- 2025: 326
- 2026: 135

### By sector
- UNMAPPED: 808
- BANKNIFTY: 208
- NIFTYENERGY: 161
- NIFTYIT: 158
- NIFTYPHARMA: 131
- NIFTYFMCG: 111
- NIFTYMETAL: 103
- NIFTYAUTO: 75
- NIFTYREALTY: 19

### Top 20 tickers
- ADANIGREEN: 21
- YESBANK: 21
- RVNL: 21
- TATAELXSI: 20
- TRENT: 19
- AMBUJACEM: 18
- IEX: 18
- PNBHOUSING: 17
- ADANIENT: 17
- ADANIPOWER: 17
- AUBANK: 16
- BSE: 16
- NBCC: 16
- SUZLON: 16
- CDSL: 16
- ANGELONE: 15
- BOSCHLTD: 15
- IRFC: 15
- BHEL: 14
- BANDHANBNK: 14

## Cause-channel headline rates

- earnings within T-3..T+1 window: **31.3%**
- sector index also moved (|z|≥1.5 same-sign): **9.4%**
- volume z ≥ 2 on T: **67.5%**

## 4-quadrant earnings × sector decomposition

- earnings + sector spike: **4.5%**
- earnings only (no sector spike): **26.8%**
- sector spike only (no earnings): **9.5%**
- neither (true idiosyncratic): **59.2%**

## By regime

- NEUTRAL: 22.3%
- CAUTION: 20.3%
- RISK-ON: 18.3%
- EUPHORIA: 17.5%
- RISK-OFF: 17.4%
- UNKNOWN: 4.2%

## Channel availability (NULL share)

- volume_z: NULL 4.1%
- volume_z_T1: NULL 9.2%
- sector_index_ret_T: NULL 45.6%
- sector_index_z: NULL 47.1%
- india_vix_z: NULL 81.8%
- regime: NULL 4.2%

## Out of v1 (deferred to v2)

- news_tagged / news_kind / news_sentiment — historical news log < 5y
- bulk_deal_T / bulk_deal_side — IndianAPI endpoint not yet integrated
- promoter_trade_T / promoter_side — SAST/PIT not yet pulled
- fii_sector_net_T — daily_dump per-sector breakdown TBD
- |z|≥2 (vs ≥3) T-1 persistence — needs full residual-panel rebuild
