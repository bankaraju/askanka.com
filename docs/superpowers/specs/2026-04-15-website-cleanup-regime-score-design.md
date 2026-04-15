# Website Cleanup + Global Regime Score — Design Spec

**Date:** 2026-04-15
**Status:** Approved (Wave 1 of 3)
**Author:** Brainstormed with Bharat

## Why

The askanka.com website has three staleness + structure problems:

1. **Stale data.** `data/live_status.json` and `data/msi_history.json` last updated 2026-04-10 09:45. The homepage displays a 5-day-old MSI score of 41.
2. **Wrong number.** The displayed "MSI" is the legacy 5-input MSI (FII/VIX/USD-INR/Nifty/crude), not the 31-ETF Global Regime Score that actually drives the trading system.
3. **Clutter.** The site carries sections that aren't production-ready (methodology, telegram link, heatmap, track record, weekly archive) — making the signal-to-noise ratio poor for subscribers.

Wave 1 fixes all three in one pass. It also establishes the clean data spine that Wave 2 (article workflow) and Wave 3 (trader terminal) will consume.

## Root causes (from systematic-debugging session)

- **Bug A:** `pipeline/website_exporter.py` is working code but never scheduled — no bat file calls it. The `data/*.json` files only ever update on manual runs.
- **Bug B:** `run_eod_report.py` computes and appends MSI but hit a log-file PermissionError on 2026-04-14 (VS Code lock race, same pattern as commit b9fd068). Result: `msi_history.json` touched but Apr 14 entry never written.
- **Structural:** The website reads legacy MSI files. The real 31-ETF regime score lives in `pipeline/data/today_regime.json` (written by `unified_regime_engine.py` / `reverse_regime_ranker.py`) and has never been wired to the website.

## What we build (scope)

### 1. Pipeline — `pipeline/website_exporter.py` refactor

**New:**
- `export_global_regime()` reads `pipeline/data/today_regime.json` and writes `data/global_regime.json` with schema:
  ```json
  {
    "updated_at": "<ISO IST>",
    "zone": "NEUTRAL",
    "score": 43.7,
    "regime_source": "etf_engine",
    "stable": true,
    "consecutive_days": 2,
    "components": {
      "inst_flow": {"norm": 0.5, "weight": 0.3, "contribution": 15.0},
      "india_vix": {"raw": 19.93, "norm": 0.49, "weight": 0.25, "contribution": 12.3},
      ...
    },
    "top_drivers": ["<component_name_1>", "<component_name_2>", "<component_name_3>"]
  }
  ```
  `top_drivers` is the 3 components with largest absolute `contribution`.

**Modified:**
- `export_live_status()` — strip out win/loss/track-record stats. Keep only: `updated_at`, `positions` (open spreads with live prices), `fragility`.

**Removed:**
- `export_track_record()` — delete function
- `export_spread_universe()` — delete function
- The `track_record.json` and `spread_universe.json` writes from `run_export()`

**`run_export()` final writes:** `global_regime.json`, `live_status.json`. Nothing else.

### 2. Scheduling

Add `python -X utf8 website_exporter.py >> logs/website_exporter.log 2>&1` to:
- `pipeline/scripts/intraday_scan.bat` — end of script. Refreshes every 15 min during market hours.
- `pipeline/scripts/eod_track_record.bat` — end of script. Final snapshot after EOD compute.

Use deferred-log-open pattern (same as b9fd068) inside `website_exporter.py` to dodge VS Code lock race.

### 3. Website — `index.html` surgery

**Remove entirely:**
- Methodology section + nav link
- Telegram link / footer reference
- Heatmap / Spread Universe Explorer block + "25 spreads" section
- Track Record table + closed-trades section
- Weekly Reports archive + weekly_index.json fetch
- MSI gauge component (replaced by Global Regime Score)
- Signal ticker scrolling bar (depends on live_status track stats)

**Keep:**
- Articles section (reads `articles_index.json`)
- F&O News scroll (reads `fno_news.json`)

**Add (new centerpiece):**
- **Global Regime Score hero block** — above the fold:
  - Zone badge: `NEUTRAL` (color-coded: RISK-OFF=red, CAUTION=amber, NEUTRAL=gold, RISK-ON=green-muted, EUPHORIA=green-bright)
  - Numeric score: `43.7`
  - Stability line: "Stable · Day 2 of NEUTRAL regime"
  - Top drivers mini-list: 3 bullets with component name + contribution
  - Updated timestamp
- **Live Positions tracker** — simple table, reads `live_status.json` `positions` array:
  - Spread name, open date, entry, current, today's move, cumulative %

### 4. Explicitly deferred

- **Historical regime backfill** — risky, not needed. Site shows only today's score. If we later want a chart, we start fresh from tomorrow onward using the new global_regime.json as canonical.
- **`run_eod_report.py` log-lock fix** — the MSI it computes is being deprecated from public display. Fix in a separate task, or delete the MSI append path entirely once Wave 2 confirms we don't need it.
- **Kite terminal wiring** — Wave 3.
- **Article workflow rewrite** — Wave 2.

## Data flow (after changes)

```
31 ETF prices
   ↓
unified_regime_engine.py (09:25 morning scan, every 15 min intraday)
   ↓
pipeline/data/today_regime.json (authoritative)
   ↓
website_exporter.py (runs at end of each intraday_scan.bat + eod_track_record.bat)
   ↓
data/global_regime.json + data/live_status.json
   ↓
askanka.com/index.html (fetches JSON on page load)
```

One source of truth. Same number in terminal (Wave 3), articles (Wave 2), and website (Wave 1).

## Verification plan

Wave 1 is complete when:

1. `python pipeline/website_exporter.py` runs clean, produces fresh `data/global_regime.json` with today's timestamp
2. `intraday_scan.bat` executes the exporter as final step without errors (check log)
3. askanka.com shows the new hero block with live regime score, positions tracker, articles, and F&O news — nothing else
4. Removed sections return no console errors, no 404s for deleted JSON files
5. Page looks clean, not broken

## Appendix — Wave 2 article voice (banked, not built here)

Captured so nothing is lost. The article template for Wave 2 will follow this structure:

1. **Anchor** — reference Global Regime Score with date, cite ETFs that moved
2. **Read the tape** — contrast market reaction to political/news rhetoric
3. **Where stress is hiding** — structural risks visible in ETF divergences
4. **Pattern recognition** — historical parallels our system flagged
5. **Our positioning** — current spread performance, forming setups
6. **News as color, at the end** — authoritative sources (global wires → Indian wires → YouTube only if <24h) consolidated in a bottom sources block

Design principle: terminal + analysis + website = one unified piece. Same regime score drives all three. Same spreads. Same thesis.

## Appendix — Open questions for tomorrow

- `today_regime.json` timestamp is currently `2026-04-14T09:25` — one day stale. Today's 09:25 morning scan may not have run (or not yet). Verify during first live test.
- BSE RSS 404 for corporate announcements — separate open thread from yesterday.
