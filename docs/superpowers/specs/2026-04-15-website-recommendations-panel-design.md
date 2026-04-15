# Website Wave 2 — "Today's Recommendations" Panel — Design Spec

**Date:** 2026-04-15
**Status:** Approved for implementation
**Predecessor:** `2026-04-15-website-cleanup-regime-score-design.md` (Wave 1, shipped)
**Successor (planned):** Wave 3 — Holiday-resilient pipeline (`is_stale`/`source_timestamp` hooks added in this spec are the contract for Wave 3)

---

## Goal

Add a single **Today's Recommendations** section to `index.html`, immediately below the Global Regime Score hero and above Live Positions. It surfaces the actual trade-eligible output of the four engines that already run inside the morning + intraday scans:

- **Spread Intelligence** (`spread_intelligence.py`)
- **Reverse-Regime Ranker — Phase B** (`reverse_regime_ranker.py`)
- **Correlation Breaks — Phase C** (`reverse_regime_breaks.py`, when wired)
- **News Intelligence** (`news_intelligence.py` + `news_verdicts.json`)

One block, one source of truth. No second mental model for what's tradeable today.

---

## Non-goals (Wave 2)

- Holiday-fallback logic (Wave 3 — pipeline change, this spec only exposes the UI hook)
- Article freshness validation (separate effort)
- F&O news refresh job (separate effort)
- Track record / EOD P&L surface (separate effort)
- Telegram / share buttons
- Backfill or rerun of historical recommendations on the page

---

## Architecture

```
                       ┌─────────────────────────────────┐
                       │  pipeline/website_exporter.py   │
                       │  + export_today_recommendations │
                       └────────────────┬────────────────┘
                                        │ reads
       ┌────────────────────────────────┼─────────────────────────────────┐
       ▼                ▼               ▼                ▼                ▼
recommendations.json  regime_ranker_  news_events_   news_verdicts.json  today_regime.json
(spread engine)       state.json      today.json     (670 historical    (drives is_stale
                      _history.json                   verdicts, stats)   threshold check)
                                        │
                                        ▼
                       ┌─────────────────────────────────┐
                       │  data/today_recommendations.json│ (canonical website file)
                       └────────────────┬────────────────┘
                                        │ fetch
                       ┌─────────────────────────────────┐
                       │  index.html  #today-recs        │
                       │  3-column grid (spreads/stocks/ │
                       │  news), per-card freshness pill │
                       └─────────────────────────────────┘
```

**No new pipeline engine is built.** This spec only adds: one exporter function, one website file, one HTML section, one bat-file wire-up. All trade logic already exists upstream.

---

## File contract: `data/today_recommendations.json`

```json
{
  "updated_at": "2026-04-15T09:25:00.000+05:30",
  "regime_zone": "NEUTRAL",
  "regime_source_timestamp": "2026-04-15T09:25:00.000+05:30",
  "spreads": [
    {
      "name": "Upstream vs Downstream",
      "action": "ENTER",
      "conviction": "HIGH",
      "z_score": -1.85,
      "reason": "Z_BELOW_MEAN_2STD",
      "source_timestamp": "2026-04-15T09:25:08.000+05:30",
      "is_stale": false
    }
  ],
  "stocks": [
    {
      "ticker": "HAL",
      "direction": "LONG",
      "conviction": "HIGH",
      "trigger": "regime_transition_EUPHORIA→RISK-OFF",
      "source": "ranker",
      "source_timestamp": "2026-04-15T09:25:00.000+05:30",
      "is_stale": false
    }
  ],
  "news_driven": [
    {
      "ticker": "RELIANCE",
      "headline": "Q4 results beat estimates by 8%",
      "category": "earnings",
      "direction": "LONG",
      "shelf_days": 3,
      "historical_hit_rate": 0.71,
      "precedent_count": 14,
      "source_timestamp": "2026-04-15T08:21:00.000+05:30",
      "is_stale": false
    }
  ],
  "holiday_mode": false
}
```

**Field semantics:**

- `updated_at` — when the exporter ran (always now)
- `regime_source_timestamp` — when `today_regime.json` was last written
- `is_stale` per card — `true` if the source file mtime is older than 4 hours **on a trading day**; always `false` on holidays (Wave 3 will set this correctly)
- `holiday_mode` — `false` in Wave 2 always; Wave 3 will populate from `trading_calendar.is_trading_day()`
- Conviction values: `HIGH`, `MEDIUM`, `LOW`, `NONE`
- Card order within each list: by conviction desc, then by absolute z-score / hit-rate desc

**Limits per column:** top 3 in each. Cards beyond top 3 are dropped (kept simple; explorer view is a future spec).

---

## Exporter changes — `pipeline/website_exporter.py`

### New constants

```python
RECOMMENDATIONS_FILE = DATA_DIR / "recommendations.json"          # spread engine
RANKER_STATE_FILE    = DATA_DIR / "regime_ranker_state.json"
RANKER_HISTORY_FILE  = DATA_DIR / "regime_ranker_history.json"
NEWS_EVENTS_FILE     = DATA_DIR / "news_events_today.json"
NEWS_VERDICTS_FILE   = DATA_DIR / "news_verdicts.json"
STALE_HOURS          = 4
```

### New function `export_today_recommendations() -> dict`

Pseudocode:

```
1. updated_at = now(IST).isoformat()
2. regime_zone, regime_ts = load(today_regime.json) → regime, timestamp
3. spreads = []
   for rec in load(recommendations.json).recommendations:
       if rec.action in {"ENTER", "EXIT"} and rec.conviction != "NONE":
           spreads.append({...; source_timestamp = recs.timestamp; is_stale = stale_check(recs.timestamp)})
   spreads.sort(key=conviction_rank desc, abs(z_score) desc)[:3]
4. stocks = []
   ranker = load(regime_ranker_state.json)
   for rec in ranker.active_recommendations:
       stocks.append({ticker, direction, conviction, trigger="ranker_active", source="ranker", ts=ranker.updated, ...})
   # Add Phase C breaks if/when correlation_breaks output exists (placeholder for now)
   stocks.sort(...)[:3]
5. news_driven = []
   today_events = load(news_events_today.json).events
   verdicts_idx = build map from news_verdicts.json by (symbol, category) for hit-rate lookup
   for ev in today_events:
       v = verdicts_idx.get((ev.symbol, ev.category))
       if v and v.recommendation in {"BUY", "SELL"}:
           news_driven.append({ticker, headline=ev.title, category, direction,
                              shelf_days=v.shelf_days, historical_hit_rate=v.historical_hit_rate,
                              precedent_count=v.precedent_count, ts=events.last_scan, ...})
   news_driven.sort(by hit_rate desc)[:3]
6. return {updated_at, regime_zone, regime_source_timestamp=regime_ts,
           spreads, stocks, news_driven, holiday_mode=False}
```

### Helper `stale_check(timestamp_str: str) -> bool`

Returns `True` if `now - parse(timestamp) > STALE_HOURS` (and we're on a trading day; in Wave 2 the trading-day guard always returns True).

### `run_export()` update

Add the new file to the export loop:

```python
for name, data in [
    ("global_regime.json", regime),
    ("live_status.json", live),
    ("today_recommendations.json", recs),     # NEW
]:
    ...
```

---

## HTML changes — `index.html`

### Insertion point
Immediately after `<section id="regime-hero">`, before `<section id="live-positions">`.

### Markup

```html
<section id="today-recs" class="recs-block">
  <h2 class="block-title">Today's Recommendations</h2>
  <div class="recs-grid">
    <div class="rec-column">
      <div class="rec-header">Spread Trades</div>
      <div class="rec-cards" id="recs-spreads"><div class="rec-empty">Loading…</div></div>
    </div>
    <div class="rec-column">
      <div class="rec-header">Standalone Stocks</div>
      <div class="rec-cards" id="recs-stocks"><div class="rec-empty">Loading…</div></div>
    </div>
    <div class="rec-column">
      <div class="rec-header">News-Driven</div>
      <div class="rec-cards" id="recs-news"><div class="rec-empty">Loading…</div></div>
    </div>
  </div>
</section>
```

### CSS (additions to existing style block)

```css
.recs-block { padding: 24px; max-width: 1200px; margin: 0 auto; border-bottom: 1px solid #2a2a2a; }
.recs-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
@media (max-width: 800px) { .recs-grid { grid-template-columns: 1fr; } }
.rec-column { background: #161616; border-radius: 8px; padding: 14px; }
.rec-header { font-family: 'Inter', sans-serif; font-size: 11px; text-transform: uppercase;
              letter-spacing: 0.08em; color: #9c9c9c; margin-bottom: 10px; }
.rec-cards { display: flex; flex-direction: column; gap: 10px; }
.rec-card { background: #1f1f1f; border-radius: 6px; padding: 10px 12px;
            font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #f3f3f3; }
.rec-card .name { font-size: 14px; font-weight: 600; }
.rec-card .meta { color: #9c9c9c; font-size: 11px; margin-top: 4px; }
.rec-card .stale-pill { display: inline-block; padding: 1px 6px; background: #3a2a18; color: #ffa94d;
                       border-radius: 3px; font-size: 10px; margin-left: 6px; text-transform: uppercase; }
.rec-card .conv-HIGH   { color: #69db7c; }
.rec-card .conv-MEDIUM { color: #f59e0b; }
.rec-card .conv-LOW    { color: #9c9c9c; }
.rec-card .dir-LONG  { color: #69db7c; }
.rec-card .dir-SHORT { color: #ff6b6b; }
.rec-empty { color: #6e6e6e; font-size: 12px; font-style: italic; }
```

### JavaScript

```javascript
async function loadTodayRecs() {
  try {
    const res = await fetch('data/today_recommendations.json?t=' + Date.now());
    if (!res.ok) throw new Error('fetch failed');
    const d = await res.json();
    renderRecColumn('recs-spreads', d.spreads, renderSpreadCard,
      'No spread setups today — regime stable');
    renderRecColumn('recs-stocks', d.stocks, renderStockCard,
      'No standalone stock signals today');
    renderRecColumn('recs-news', d.news_driven, renderNewsCard,
      'No news-driven trades today');
  } catch (e) {
    ['recs-spreads', 'recs-stocks', 'recs-news'].forEach(id =>
      document.getElementById(id).innerHTML = '<div class="rec-empty">Offline</div>');
  }
}

function renderRecColumn(elId, items, renderFn, emptyMsg) {
  const el = document.getElementById(elId);
  el.innerHTML = '';
  if (!items || items.length === 0) {
    el.innerHTML = '<div class="rec-empty">' + emptyMsg + '</div>';
    return;
  }
  items.forEach(it => el.insertAdjacentHTML('beforeend', renderFn(it)));
}

function stalePill(it) { return it.is_stale ? '<span class="stale-pill">stale</span>' : ''; }

function renderSpreadCard(s) {
  return '<div class="rec-card">' +
    '<div class="name">' + s.name + stalePill(s) + '</div>' +
    '<div class="meta"><span class="conv-' + s.conviction + '">' + s.conviction + '</span>' +
    ' · ' + s.action + ' · z=' + Number(s.z_score).toFixed(2) + ' · ' + s.reason + '</div>' +
    '</div>';
}

function renderStockCard(s) {
  return '<div class="rec-card">' +
    '<div class="name"><span class="dir-' + s.direction + '">' + s.direction + '</span> ' +
    s.ticker + stalePill(s) + '</div>' +
    '<div class="meta"><span class="conv-' + s.conviction + '">' + s.conviction + '</span>' +
    ' · ' + s.trigger + '</div>' +
    '</div>';
}

function renderNewsCard(n) {
  return '<div class="rec-card">' +
    '<div class="name"><span class="dir-' + n.direction + '">' + n.direction + '</span> ' +
    n.ticker + stalePill(n) + '</div>' +
    '<div class="meta">' + n.headline + '</div>' +
    '<div class="meta">hit ' + Math.round(n.historical_hit_rate * 100) + '%' +
    ' · ' + n.precedent_count + ' precedents · ' + n.shelf_days + 'd shelf</div>' +
    '</div>';
}

loadTodayRecs();
setInterval(loadTodayRecs, 60_000);
```

---

## Empty-state policy

When an engine produces zero qualifying items:
- Column header still renders (so layout stays stable)
- Card area shows the explicit empty message ("No spread setups today — regime stable")
- This is honest; hiding the column would make the page look different on quiet days vs busy days for no good reason

---

## Staleness policy

`is_stale` is computed at export time:
- Source file mtime > 4 hours old → `is_stale: true`, render with orange "STALE" pill
- File missing → that engine's column shows the empty message (don't fabricate)
- 4-hour threshold matches "if morning scan ran but no intraday refresh happened, flag it"
- Wave 3 will modify the threshold logic so holidays don't falsely flag stale (the `is_stale` field already exists, only the computation changes)

---

## Bat-file wiring

Both `pipeline/scripts/intraday_scan.bat` and `pipeline/scripts/eod_track_record.bat` already invoke `website_exporter.py` at the end (Wave 1). Nothing new needed — `run_export()` will write the new file automatically.

---

## Verification plan

**Unit tests** (`pipeline/tests/test_website_exporter.py`):
- `test_today_recommendations_basic_fields` — fixture-driven, validates top-level keys
- `test_today_recommendations_spreads_filter_inactive` — INACTIVE/NONE recs are dropped
- `test_today_recommendations_top3_limit` — only 3 cards per column
- `test_today_recommendations_stale_flag` — old fixture mtime → `is_stale: true`
- `test_today_recommendations_missing_engine_files` — graceful empty arrays, not exception

**Smoke test:**
- Run `python -X utf8 pipeline/website_exporter.py`
- Verify `data/today_recommendations.json` exists, is valid JSON, has 3 lists
- Open `index.html` in browser, confirm the 3-column block renders below the hero
- Confirm a stale source file produces the orange pill

**Live verification:**
- After morning scan completes, the page should show fresh recommendations
- DevTools → Network: `today_recommendations.json` returns 200, no other 404s introduced

---

## Open questions for Wave 3 (logged, not blocking)

1. Holiday-fallback in `trading_calendar` + every scanner (use D-1 India data, label clearly)
2. Phase C correlation breaks — currently no scheduled task wraps `correlation_breaks.bat`. Wire it during Wave 3 so the stocks column gets break-triggered ADDs
3. Overnight news backtest — `overnight_news.bat` exists but isn't scheduled. Add `AnkaOvernightNews` task at 04:30
4. `holiday_mode: true` UI banner — pinned to the regime hero on holidays

---

## Acceptance criteria

- [ ] `data/today_recommendations.json` exists after exporter runs, has all 3 lists
- [ ] Each list has at most 3 items
- [ ] Cards include `source_timestamp` and `is_stale`
- [ ] `index.html` renders the 3-column block immediately below the hero
- [ ] Empty engine outputs render as honest empty messages, not as fake content
- [ ] STALE pill appears when a source file is >4h old on a trading day
- [ ] No new console errors, no new 404s
- [ ] All Wave 1 functionality (hero, positions) still works
- [ ] Unit tests for new export function all pass
