# askanka.com V2 — LIVE Market Intelligence Hub
## Spec | April 3, 2026

---

## VISION

Transform askanka.com from a static report archive into a **LIVE market intelligence dashboard** that updates in real-time, shows our track record with real P&L, and drives Telegram subscriber growth.

**One sentence:** Bloomberg Terminal aesthetic meets retail investor accessibility — powered by our live pipeline.

---

## CURRENT STATE (what we have)

- Static HTML pages: index.html, 5 report pages
- Dark theme (good — keep it)
- No live data, no P&L display, no interactivity
- Reports are manually published HTML files
- Pipeline runs in background, sends signals to Telegram only

## TARGET STATE (what we want)

A website that:
1. **Feels LIVE** — data updates without page refresh
2. **Shows our track record** — real P&L from real recommendations
3. **Converts visitors to Telegram subscribers** — the CTA is everywhere
4. **Publishes weekly reports automatically** — no manual work
5. **Looks institutional** — dark, clean, data-dense, credible

---

## PAGE STRUCTURE

### 1. HOMEPAGE (index.html) — The Dashboard

**Hero section:**
- Anka Research logo + tagline: "Data-Driven Spread Trading Signals"
- LIVE MSI gauge (0-100, color-coded) — updated from pipeline JSON
- "Join @ANKASIGNALS on Telegram" CTA button (prominent, gold)

**Live Stats Bar:**
- Open positions count
- Cumulative P&L % (since inception)
- Win rate %
- Total signals generated
- Days active

**Active Positions Panel:**
- Each open spread shown as a card:
  - Spread name, tier badge (SIGNAL 🟢 / EXPLORING 🟡)
  - Long leg tickers → current prices → P&L %
  - Short leg tickers → current prices → P&L %
  - Spread P&L % with color (green/red)
  - Entry date, days held
  - Data-driven stop levels
- Auto-updates from a JSON file the pipeline writes at each 30-min cycle

**Track Record Table:**
- All closed trades in a sortable table:
  - Signal ID, Spread name, Category, Entry date, Exit date
  - Entry spread, Exit spread, P&L %
  - Win/Loss badge
  - Days held
- Summary row: total trades, win rate, avg P&L, best trade, worst trade

**Signal Universe Explorer:**
- Interactive grid of all 25 spreads
- Click a spread → see its backtest stats across all 18 event categories
- Hit rate heatmap: rows = spreads, columns = event categories
- Color intensity = hit rate (darker green = higher)

**MSI History Chart:**
- Line chart of MSI score over time (from msi_history.json)
- Color-coded background bands: green (<35), yellow (35-64), red (≥65)
- Interactive: hover to see components breakdown

**Weekly Reports Section:**
- Cards for each weekly report (auto-generated)
- Latest report prominently featured
- Archive grid below

**Footer:**
- Telegram CTA (repeated)
- Disclaimer
- "Powered by Anka Research Pipeline — fully automated, zero human intervention"

### 2. LIVE P&L PAGE (/live or /track-record)

Dedicated page showing full track record with:
- Equity curve chart (cumulative P&L over time)
- Monthly returns table
- Win/loss streak
- Best/worst trades
- P&L by event category (which events make us money?)
- P&L by spread pair (which spreads perform best?)

### 3. SIGNAL UNIVERSE PAGE (/signals or /universe)

Deep dive into all 25 spreads:
- Each spread gets a card with:
  - Constituent stocks (long + short)
  - Backtest hit rates by trigger category
  - Historical spread chart (cumulative spread movement)
  - Current spread level vs entry level vs stop level
  - Recent signals for this spread

### 4. WEEKLY REPORT PAGE (/reports/week-NNN.html)

Auto-generated each week by `weekly_report_generator.py`:
- Market regime summary
- MSI trend
- Signal activity (new, closed, stopped)
- P&L summary
- Top performing spreads
- Macro outlook
- Data tables + charts

---

## TECHNICAL APPROACH

### Data Flow: Pipeline → Website

The pipeline already produces all the data. We just need to export it as JSON files that the website reads:

```
Pipeline (runs on schtask)
    ↓ writes JSON files
data/website/
    ├── live_status.json      ← MSI, regime, open positions, P&L
    ├── track_record.json     ← all closed trades with P&L
    ├── spread_universe.json  ← 25 spreads with backtest stats
    ├── msi_history.json      ← MSI time series
    └── equity_curve.json     ← cumulative P&L time series
    ↓
Website reads JSON via fetch()
    ↓
Renders live dashboard (no backend needed)
```

### Stack

- **Pure static site** — HTML + CSS + vanilla JS (or lightweight Alpine.js)
- **No backend server** — all data comes from JSON files written by pipeline
- **GitHub Pages** — free hosting, custom domain (askanka.com already on CNAME)
- **Charts** — Plotly.js (already used in reports) or Chart.js (lighter)
- **Auto-deploy** — git push → GitHub Pages updates

### Pipeline Export Module (new: `website_exporter.py`)

New module that runs after each signal cycle:
1. Reads open_signals.json, closed_signals.json, msi_history.json
2. Computes live P&L using current prices
3. Writes clean JSON files to `data/website/`
4. These JSON files are committed to git repo and served on GitHub Pages

### Update Frequency

- **Every 30 min during market hours** — pipeline cycle already runs
- **After market close** — EOD report updates track record
- **Weekly** — weekly report auto-generated and committed

---

## DESIGN LANGUAGE

### Visual Identity
- **Dark theme** (keep current palette — it's good)
- **Gold accent** (#f59e0b) for CTAs and highlights
- **Green/Red** for P&L (standard)
- **JetBrains Mono** for numbers/data (monospace = credibility)
- **Inter** for body text

### Layout Principles
- Data-dense but not cluttered
- Cards with subtle borders, not heavy shadows
- Animated number counters for stats
- Subtle pulse animation on live data points
- Mobile-first responsive design

### Credibility Markers
- "LIVE" badge with green dot (pulsing) next to data that updates
- "Last updated: 12:45 IST" timestamp
- "Backtested on 90 events, 4 years of data" — show your methodology
- Track record table is the #1 credibility driver

---

## PHASE PLAN

### Phase 1: Data Export (build first)
- [ ] Create `website_exporter.py` in pipeline
- [ ] Wire into signal cycle (run after each 30-min check)
- [ ] Export: live_status.json, track_record.json, spread_universe.json
- [ ] Test with real data from Monday's market

### Phase 2: Homepage Redesign
- [ ] New index.html with live dashboard layout
- [ ] MSI gauge component
- [ ] Active positions panel (reads live_status.json)
- [ ] Track record table (reads track_record.json)
- [ ] Telegram CTA buttons
- [ ] Mobile responsive

### Phase 3: Charts & Interactivity
- [ ] MSI history line chart
- [ ] Equity curve chart
- [ ] Spread universe heatmap
- [ ] Interactive spread explorer cards
- [ ] Animated stat counters

### Phase 4: Auto-Generated Reports
- [ ] Weekly report auto-generation from pipeline data
- [ ] Auto-commit + push to GitHub Pages
- [ ] Report archive page

### Phase 5: Polish & Launch
- [ ] SEO meta tags, Open Graph images
- [ ] Loading states + error handling
- [ ] Performance optimization (lazy load charts)
- [ ] Share buttons (Twitter, WhatsApp)
- [ ] Google Analytics

---

## SUCCESS METRICS

1. **Telegram subscriber growth** — CTA click rate from website
2. **Track record visibility** — visitors can see every trade we made
3. **Zero manual work** — pipeline writes data, website reads it, reports auto-publish
4. **Professional appearance** — looks like a real research house, not a hobby project
5. **Mobile-first** — 70%+ of Indian retail investors browse on phone

---

## NOTES FOR AGENTS

- Start with Phase 1 (data export) — everything else depends on it
- The dark theme and Inter/JetBrains Mono fonts are already set up — keep them
- Plotly.js is already included in report pages — reuse for charts
- All data is in the pipeline — no new APIs or backends needed
- CNAME file already maps to askanka.com — don't change
- Test with real JSON data from the pipeline, not mock data
