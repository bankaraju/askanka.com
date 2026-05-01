# Trendlyne Pro Global — manual export landing zone

**Subscription:** Trendlyne Pro Global (acquired 2026-05-01).
**Access:** UI-only — no programmatic API. CSV exports from web UI only.

This directory is where raw Trendlyne CSV/Excel exports land before normalization.
Every export gets dropped under `raw_exports/<dataset>/` exactly as Trendlyne ships
it (no rename, no edit). Normalization to parquet happens in
`pipeline/research/theme_detector/data_loaders.py` (or a dedicated ingest
module — TBD when we see actual export shape).

## Folder layout

```
pipeline/data/trendlyne/
├── README.md                          ← this file
├── raw_exports/
│   ├── shareholding/                  ← TD-D7 — FII shareholding panel
│   │   └── <symbol>_<YYYY-Q>.csv      (or whatever Trendlyne names it)
│   ├── eps_surprise/                  ← TD-D9 — Quarterly EPS surprise
│   │   └── <symbol>_quarterly.csv
│   ├── ipo_calendar/                  ← TD-D3 — IPO listings
│   │   └── ipos_<YYYY>.csv
│   └── nifty500_weights/              ← TD-D1 (alt source — NSE direct is free)
│       └── nifty500_<YYYY-MM>.csv
└── normalized/                        ← parquet outputs after ingestion
    ├── fii_shareholding.parquet
    ├── eps_surprise.parquet
    ├── ipo_calendar.parquet
    └── nifty500_weights.parquet
```

## What to download from Trendlyne — priority order

Below is the concrete shopping list. Each item is paired with where to look
in the Trendlyne UI and what we hope it contains. If a section gives you a
download button on the page → grab it. If not, screenshot the page and send
me the URL so I can figure out a workaround.

### 1. FII shareholding history (HIGHEST PRIORITY → unblocks B3 signal)

**What we need:** for each F&O stock, the quarterly time series of
`fii_holding_pct` going back 3-5 years (2021-2026 minimum).

**Where to look:**
- Top nav → look for "Shareholding Pattern" or "Ownership"
- Try a single stock first: `https://trendlyne.com/equity/<SYMBOL>/shareholding-pattern/`
- See if there's a "Download" / "Export" / "CSV" button on that page

**Best-case shape:** one CSV per stock with columns
`quarter, promoter_pct, fii_pct, dii_pct, public_pct`.

**Backup if per-stock-only:** look for a SCREENER or DASHBOARD where you can
pull "FII change" across many stocks for one quarter — e.g.
"Shareholding Change Screener" → all F&O stocks → export. 20 quarter exports
beats 213 stock exports.

### 2. EPS surprise (PIT) (HIGH PRIORITY → unblocks C5 signal)

**What we need:** for each F&O stock, per-quarter `actual_eps`,
`consensus_eps_at_announcement`, `revenue_actual`, `revenue_consensus`.

**Where to look:**
- "Quarterly Results" tab on a stock page
- Or top nav → "Quarterly Results" / "Earnings Watch" / "Beat-Miss" screener

**Critical question:** does the consensus value shown reflect what consensus
WAS at announcement time, or is it the current/revised consensus? If the
latter, Trendlyne is not PIT-correct for this signal — usable for a forward
forecast but not for a backtest. (We have to test this with one quarter and
compare to the public record.)

### 3. IPO calendar (LOW PRIORITY → unblocks B5 signal)

**What we need:** list of NSE main-board IPOs since 2018 with `listing_date`,
`issue_size_inr_cr`, `subscription_multiples`, `sector`.

**Where to look:**
- "IPO Center" — Trendlyne's IPO product page
- Should have a list view with all-time / by-year filter

### 4. NIFTY-500 weights (NOT NEEDED FROM TRENDLYNE)

**Source instead:** `https://www.niftyindices.com/reports/historical-data` →
free monthly publication of NIFTY-500 constituent weights. Don't burn
Trendlyne on this; we'll script a small NSE scrape.

## After download

1. Drop file as-is in `raw_exports/<dataset>/`
2. Tell me what shape you got (column names from the CSV header is enough)
3. I'll write the ingest function + signal wire-up

## Refresh cadence

- FII shareholding: refresh quarterly (after each results season)
- EPS surprise: refresh quarterly
- IPO calendar: refresh monthly when new IPOs list

Manual operations — no scheduled task can fetch since there's no API.
