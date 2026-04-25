# Correlation-break forensics v2 — data-source feasibility audit

**Date:** 2026-04-25
**Scope:** Grade the v2 forensic-card channels (bulk deals, insider/promoter trades, 5y historical news, per-sector FII) on availability, cost, and integration effort *before* committing to any of them.
**Policy binding:** Lightweight feasibility scan. Full §6 dataset registration (per `anka_data_validation_policy_global_standard.md`) deferred until a channel is actually used in a backtest with an edge claim.
**Triggered by:** v1 forensic card found that **59.2%** of 4σ correlation breaks are *true idiosyncratic* (no earnings, no sector spike). The four v2 channels are the candidate explanations for that residual.

## Channel-by-channel grading

### 1. Bulk / block deals — TRACTABLE (Tier A)

| | |
|---|---|
| **Source** | NSE daily bulk-deals + block-deals reports |
| **URL** | `https://www.nseindia.com/reports-cm-bulk-deals` and `/reports-cm-block-deals` (free, no API key) |
| **Coverage** | Full archive available 2010+; daily after market close (typically T+1 morning) |
| **Schema** | `Date, Symbol, Client_Name, Buy/Sell, Quantity, Trade_Price, Remarks` |
| **Auth** | Session cookie required (same pattern as `pipeline/fii_flows.py`); no API key |
| **Backfill cost** | ~5y × ~250 trading days × 2 reports = ~2,500 CSV downloads, scriptable in 1–2 hours. Disk: <100 MB |
| **Going-forward cost** | Daily fetch added to overnight batch (≤30 s) |
| **Integration effort** | 1 day: write fetcher + parser + parquet archiver, parallel to `fii_flows.py` |
| **Cleanliness risk** | Client_Name normalisation (FII/DII/promoter mapping) needs a lookup table. Bulk deals appear when single client trades >0.5% of company shares — covers concentrated activity but misses spread-out activity |

**Verdict: ship it.** Highest-value v2 channel; no recurring cost; backfill is fast.

### 2. Insider / promoter trades — TRACTABLE (Tier A)

| | |
|---|---|
| **Source** | NSE corporate-filings PIT (Prohibition of Insider Trading) disclosures |
| **URL** | `https://www.nseindia.com/companies-listing/corporate-filings-insider-trading` (free, no API key) |
| **Alt source** | BSE corporate-filings; `https://stock.indianapi.in/recent_announcements` may include insider filings (need to confirm — current artifact only carries 5 recent items) |
| **Coverage** | Full archive 2015+; per-symbol disclosures lagged 1–2 trading days |
| **Schema** | `Symbol, Name_of_Person, Designation, Acquisition_Mode, Securities_Held_Pre, No_of_Securities_Acquired_Disposed, Securities_Held_Post, Date_of_Allotment, Mode_of_Acquisition` |
| **Auth** | NSE session cookie or IndianAPI X-Api-Key |
| **Backfill cost** | One-time scrape of NSE PIT archive: ~5y × ~213 stocks = ~10,000 disclosures (estimate), 2–4 hours scripting |
| **Going-forward cost** | Daily fetch in overnight batch |
| **Integration effort** | 1–2 days: NSE scraper + designation-classifier (Promoter / KMP / Director / Other) + parquet archiver |
| **Cleanliness risk** | Designation field is free-text; promoter classification needs careful mapping. SAST disclosures (≥5% acquisitions) are a separate report — covers different activity from PIT |

**Verdict: ship it.** High-value channel; lagged 1–2 days but always available before forensics runs.

### 3. 5-year historical news — NOT TRACTABLE (Tier C)

| | |
|---|---|
| **Existing artifacts** | `opus/artifacts/<symbol>/eodhd_news.json` carries last 50 items per stock, ~3 months coverage. `indianapi_news.json` carries last 20 items |
| **EODHD historical news API** | Charges per-query; 5y × 213 stocks at typical volumes ≈ **$200–500** one-time backfill |
| **Google News scrape** | Unreliable for historical (Google deprecates older results); rate-limited; also legally grey |
| **GDELT** | Free, ~5y archive, but stock-mention extraction is noisy and English-press-biased |
| **Indian-press scrapers** | Moneycontrol, ET, BloombergQuint — each requires its own scraper + 5y archive; ≥1 week of work; brittle |

**Verdict: do not pursue for v2.** Cost-to-value is poor. Substitute strategy: pull news *forward-only* into v3 using existing `news_scanner.py` integrations, and run forensics on the new-incident slice 6 months from now once 6 months of clean news exists. For the historical 5y forensics question, treat news as unobserved and use bulk deals + insider trades as the surrogate "private information" channel.

### 4. Per-sector FII flow — PARTIALLY TRACTABLE (Tier B)

| | |
|---|---|
| **What's available daily** | NSE `fiidiiTradeReact` (already pulled by `pipeline/fii_flows.py`) → aggregate FII equity buy/sell/net only. **No per-sector breakdown.** |
| **What's available monthly** | NSDL DPI publishes FPI sector-wise holding values monthly. Useful for slow drift, *not* for daily 4σ event attribution |
| **Daily proxy: sector ETF flows** | Each NSE sectoral index has matching ETFs (e.g. NIFTYBEES, BANKBEES, ITBEES). Volume-weighted ETF flow on the break date is a noisy but daily proxy for sector-rotation pressure. We already have ETF daily bars |
| **Coverage** | Aggregate FII: full archive on NSE. Sector ETFs: depends on each ETF's launch date (NIFTYBEES 2001+, NIFTYIT-ETF 2017+) |

**Verdict: ship the proxy.** Skip per-sector FII; use sector-ETF daily volume z-score as the rotation signal. Cheap, daily, no new fetch needed (ETF bars already pulled). Rename column to `sector_etf_volume_z_T` to be honest about what it measures.

## Recommended v2 build order

1. **Bulk deals fetcher + 5y backfill** (1 day, cheap, high value)
2. **PIT/insider trades fetcher + 5y backfill** (1–2 days, cheap, high value)
3. **Sector ETF volume z-score** (a few hours, already-pulled bars, modest value)
4. **Defer historical news** — revisit when 6 months of forward-only news has accumulated, or if user wants to budget $200–500 for an EODHD backfill

Total v2 effort: ~3 days of focused work for items 1–3. v2 forensic card adds 5 columns (`bulk_deal_T`, `bulk_deal_side`, `insider_trade_T`, `insider_side`, `sector_etf_vol_z_T`) and a similar 4-quadrant tabulation extended to 6+ channels.

## Open questions for user

1. **Approve order: bulk deals → insider → ETF proxy, defer news?** Or different priority?
2. **Where to run:** v2 backfill is cheap and one-shot — local fine. Going-forward fetches join the overnight batch as new scheduled tasks.
3. **Promoter-only filter for insider channel?** Current scrape would pull all PIT (KMP, Directors, Other). Filtering to only Promoter trades is the highest-signal subset; a column for "any insider" + "promoter only" is cheap to keep both.
4. **News deferral OK?** If yes, v2 forensic card will not have a news_tagged column — only the four channels above plus the v1 channels.
