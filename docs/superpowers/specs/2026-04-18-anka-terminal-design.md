# Anka Terminal — Trading Intelligence Terminal Design Spec

> **For agentic workers:** This is a design specification. Use superpowers:writing-plans to create the implementation plan.

**Goal:** Build a local web-based trading intelligence terminal that serves as the primary product — a sophisticated, investor-grade interface over the Anka Research pipeline.

**Product type:** Local web app distributed via `pip install anka-terminal`, opened at `http://localhost:8501`

**Target users:** (1) Bharat as daily cockpit for pre-market → intraday → EOD workflow, (2) External investors/subscribers viewing signals, research, and track record.

---

## 1. Architecture & Tech Stack

### Distribution

```
pip install anka-terminal
anka serve            # starts FastAPI on localhost:8501
                      # auto-opens browser
```

### Backend — Python / FastAPI

- FastAPI application serving REST endpoints
- Reads directly from existing pipeline JSON files (`pipeline/data/`, `pipeline/autoresearch/`)
- WebSocket channel for intraday real-time updates (regime changes, new signals, price ticks)
- No database — the pipeline's JSON files are the single source of truth
- Static file serving for frontend assets (HTML/CSS/JS bundled in the pip package)

### Frontend — Vanilla JS + Lightweight Charts

- Single HTML entry point, ES module JS files (no build step, no Node.js dependency)
- [Lightweight Charts](https://github.com/nicktomlin/lightweight-charts) by TradingView for all candlestick/line/area charts (npm: `lightweight-charts`, CDN-loadable)
- Lucide icons (SVG, no emoji per ui-ux-pro-max rule `no-emoji-icons`)
- No framework — vanilla JS with module pattern for components

### Design System (Locked)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0a0e1a` | Page background |
| `--bg-card` | `#111827` | Card/panel surfaces |
| `--bg-elevated` | `#1e293b` | Hover states, active items |
| `--border` | `#1e293b` | Card borders, dividers |
| `--text-primary` | `#f1f5f9` | Headlines, primary content |
| `--text-secondary` | `#94a3b8` | Labels, secondary info |
| `--text-muted` | `#64748b` | Timestamps, tertiary |
| `--accent-gold` | `#f59e0b` | Primary accent, regime EUPHORIA |
| `--accent-green` | `#10b981` | Bullish, LONG, positive P&L |
| `--accent-red` | `#ef4444` | Bearish, SHORT, negative P&L, RISK-OFF |
| `--accent-blue` | `#3b82f6` | Neutral regime, informational |
| `--accent-amber` | `#d97706` | Caution regime, warnings, EXPLORING tier |
| `--font-display` | `DM Serif Display, serif` | Section headers, hero text |
| `--font-body` | `Inter, sans-serif` | Body text, labels, UI |
| `--font-mono` | `JetBrains Mono, monospace` | Prices, numbers, tabular data |
| `--radius-sm` | `6px` | Small elements |
| `--radius-md` | `10px` | Cards |
| `--radius-lg` | `14px` | Modals, panels |
| `--spacing-unit` | `8px` | Base spacing (multiples: 4, 8, 12, 16, 24, 32, 48) |

### Data Flow

```
Pipeline scheduled tasks
    ↓ write
pipeline/data/*.json + pipeline/autoresearch/*.json
    ↓ read
FastAPI REST endpoints + WebSocket
    ↓ serve
Browser (Vanilla JS + Lightweight Charts)
```

The terminal performs zero data processing — it is a pure presentation layer.

---

## 2. Navigation Structure

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│  [Regime Badge: EUPHORIA]    Market: OPEN    IST 10:34:22   │  ← Top Bar
├────────┬─────────────────────────────────────────────────────┤
│        │                                                     │
│  🏠 D  │              Main Content Area                      │
│  📈 T  │                                                     │
│  🧠 I  │                                                     │
│  📊 R  │                                            ┌───────┤
│  ⚙️ S  │                                            │Context│ ← Right Panel
│        │                                            │ Panel │    (slide-out)
│        │                                            │       │
├────────┴────────────────────────────────────────────┴───────┘
```

Note: Icons above are placeholders — implementation uses Lucide SVG icons.

### Primary Tabs (Fixed Left Sidebar)

| # | Tab | Icon | Keyboard |
|---|-----|------|----------|
| 1 | Dashboard | `layout-dashboard` | `1` |
| 2 | Trading | `trending-up` | `2` |
| 3 | Intelligence | `brain` | `3` |
| 4 | Track Record | `bar-chart-2` | `4` |
| 5 | Settings | `settings` | `5` |

### Sub-Tab Navigation

- **Trading:** Signals | Spreads | Charts | TA
- **Intelligence:** Trust Scores | News | Research
- **Settings:** Broker | Alerts | Display

Sub-tabs render as a horizontal strip below the top bar, within the main content area.

### Top Bar (Fixed)

- Left: Current regime zone badge (color-coded, with stability indicator)
- Center: Market status (PRE-OPEN / OPEN / CLOSED) + session timer
- Right: IST clock + staleness alert indicator (amber dot if any critical data is stale)

### Contextual Right Panel

- 400px slide-out panel, triggered by clicking any ticker anywhere in the app
- Contents: stock-specific news feed + trust score badge + mini price chart + active signals for that ticker
- Close: X button or Escape key
- Panel does not navigate away from current view — it overlays

---

## 3. Dashboard Tab

First screen users see on launch.

### Regime Banner (Full Width)

- Background color maps to regime zone:
  - EUPHORIA: gold gradient
  - RISK-ON: green
  - NEUTRAL: blue
  - CAUTION: amber
  - RISK-OFF: red
- Text: regime name + stability ("STABLE — 4 consecutive days" or "UNSTABLE — 1 day, unconfirmed")
- Secondary: MSI score + MSI regime as muted text
- Right side: last updated timestamp

### Key Metrics (4 Cards, Left Column)

| Card | Content |
|------|---------|
| ETF Composite Signal | Current value + 7-day sparkline |
| Shadow P&L | Cumulative return % + win rate + Sharpe |
| Active Signals | Count of SIGNAL tier (80+ conviction) trades |
| Risk Gate Status | L0/L1/L2 level + current sizing factor |

Cards use `--bg-card` background, `--radius-md` border radius, subtle gold left-border for emphasis.

### Today's Signals Summary (Center)

- Table sorted by conviction score (highest first)
- Columns: Ticker, Direction (LONG ↑ green / SHORT ↓ red), Conviction (score/100), Entry Price, Stop, Target, Age (days)
- Row styling:
  - 80+ conviction: gold left border accent
  - 60-79 (EXPLORING): muted opacity (0.7), italic "EXPLORING" badge
  - Closed today: strikethrough with P&L result
- Click any row → navigates to Trading > Signals with that signal expanded

### Quick Glance (Right Column)

- Nifty 50 mini intraday line chart (Lightweight Charts, 200px height)
- India VIX: current value + direction arrow (▲ red / ▼ green)
- FII/DII net flows: today's value in crores
- Top 3 eligible spreads from regime trade map (name + win rate)

---

## 4. Trading Tab

The core working area. 4 sub-tabs.

### 4.1 Signals Sub-Tab

**Filter bar (top):**
- Tier filter: SIGNAL / EXPLORING / ALL (toggle buttons)
- Direction: LONG / SHORT / ALL
- Sector dropdown
- Search: ticker name

**Signal list (main area):**
- Card-based list, each signal is a collapsible card
- Collapsed: Ticker | Direction | Conviction | Entry | Current | P&L% | Age
- Expanded card shows:
  - **Conviction breakdown**: base score (from backtest win rate) + trust modifier (+10/+15) + velocity signals (+5/+8) = total
  - **Price ladder**: visual vertical strip showing entry, current, stop (red line), target (green line), trailing stop (amber dashed)
  - **Entry rationale**: regime at entry, which Phase (A/B/C) generated it, correlation break z-score if applicable
  - **TA snapshot**: active technical patterns for this stock (from fingerprint engine)
  - **Stock news**: 3 most recent news items for this ticker, inline (not in side panel)
- Actions per signal: "View Chart" (jumps to Charts sub-tab with ticker loaded), "View Spread" (if part of a spread)

### 4.2 Spreads Sub-Tab

**Layout:** Card grid (2 columns on desktop)

**Each spread card:**
- Header: Spread name (e.g., "Defence vs IT"), regime eligibility badge
- Stats row: Win Rate | Best Period | Sharpe
- Legs: Long leg ticker + trust grade vs Short leg ticker + trust grade
- Expand to show:
  - Backtest equity curve (Lightweight Charts area chart, 150px height)
  - Both legs' trust score comparison (side-by-side grade badges)
  - Stock news for both legs (split panel)
  - Entry/exit levels from spread intelligence engine
  - Sizing: position size from risk guardrails (L0/L1 factor applied)

**Sorting:** By win rate (default), by Sharpe, by best period

### 4.3 Charts Sub-Tab

**Full-width Lightweight Charts candlestick view.**

- **Ticker selector**: search input with autocomplete (213 F&O stocks)
- **Timeframe strip**: 1D | 1W | 1M | 3M | 1Y | 5Y (toggle buttons)
- **Main chart**: Candlestick with volume bars below
- **Overlays** (toggleable checkboxes):
  - SMA 20/50/200
  - EMA 9/21
  - Bollinger Bands
- **Below chart**: RSI panel (separate pane, 100px height)
- **Signal markers**: Entry arrows (green ↑ / red ↓), stop level (red horizontal), target (green horizontal), trailing stop (amber dashed)
- **TA pattern markers**: Vertical dashed lines on dates where fingerprint patterns fired
- Chart colors: bullish candles `#10b981`, bearish candles `#ef4444`, volume bars 40% opacity

### 4.4 TA (Technical Analysis) Sub-Tab

**Stock selector** at top (same autocomplete as Charts).

**Fingerprint card (main area):**
- 15-pattern grid (3×5), each pattern is a small card:
  - Pattern name (e.g., "Bullish Engulfing", "MACD Crossover")
  - Status: ACTIVE (green pulse) / INACTIVE (muted)
  - Historical hit rate: "72% over 5yr"
  - Average return when pattern fires
  - Event count: "143 events"
- Active patterns get elevated card style (`--bg-elevated`) with green left border

**Backtest summary below:**
- Table: Pattern | Events (5yr) | Win Rate | Avg Return | Last Fired
- Sortable by any column
- Click pattern row → jumps to Charts sub-tab with date range of that pattern highlighted

---

## 5. Intelligence Tab

3 sub-tabs for research and analysis context.

### 5.1 Trust Scores Sub-Tab

**Search + filter bar:**
- Text search (ticker or company name)
- Sector dropdown filter
- Grade range filter (A+ to F)
- Sort by: Grade (default), Score, Sector, Last Updated

**Universe table (main area):**
- Full 213-stock table with columns: Ticker | Company | Sector | Trust Grade | Score | Last Updated
- Grade badges color-coded:
  - A/A+: `#10b981` green background
  - B/B+: `#3b82f6` blue
  - C: `#f59e0b` amber
  - D/F: `#ef4444` red
  - "?": `#64748b` muted with "Pending" text
- Click any row → opens contextual right panel with full scorecard detail

**Sector heatmap (above table):**
- Grid of rectangles, one per stock, grouped by sector
- Sized by market cap, colored by trust grade
- Hover shows ticker + grade
- Click → scrolls table to that stock

### 5.2 News Sub-Tab (General/Macro)

**Reverse-chronological feed:**
- Each item: headline, source attribution, timestamp (relative: "2h ago"), impact badge
- Impact classification: HIGH (red), MEDIUM (amber), LOW (blue) — always with text label, not color alone
- Tags: affected sectors, affected regime zones
- Special badge: "REGIME CATALYST" (gold) for news that triggered a regime change
- Filter bar: impact level, sector, date range picker

### 5.3 Research Sub-Tab

**Card layout (2-column grid):**
- Each article card: headline (DM Serif Display), category tag (INVESTIGATION / GEOPOLITICAL / MARKET), publication date, estimated read time
- Hero card for today's article (larger, gold border, top position)
- Click opens full article rendered in the main content area (markdown → HTML)
- Archive section below with date picker for historical articles
- Each article shows a regime context banner: "Written during EUPHORIA regime — ETF signal: +2.3"

---

## 6. Track Record Tab

The proof layer that converts investors.

### Headline Metrics (4 Large KPI Cards, Top Strip)

| KPI | Display |
|-----|---------|
| Cumulative Return | Large percentage number + equity sparkline |
| Win Rate | Percentage + fraction (e.g., "67.3% — 34/51") |
| Sharpe Ratio | Value, color-coded: green >1.5, gold >1.0, red <1.0 |
| Max Drawdown | Worst peak-to-trough percentage + date range |

Cards are wider than Dashboard cards — hero-sized with prominent numbers in `--font-mono`.

### Equity Curve (Center)

- Lightweight Charts area chart, full width, 350px height
- Primary: shadow P&L cumulative return line
- Toggle overlay: Nifty 50 benchmark (muted blue line)
- Background bands: regime zones as semi-transparent colored regions behind the curve
- Timeframe selector: 1M / 3M / 6M / YTD / ALL

### Closed Trades Table (Below Curve)

- All closed shadow trades, sortable by any column
- Columns: Spread/Ticker | Direction | Entry Date | Exit Date | Entry Price | Exit Price | P&L % | Exit Reason | Regime | Conviction
- P&L color: green positive, red negative (with ▲/▼ icon, not color alone)
- Exit reason badges: TARGET HIT (green), STOPPED (red), TRAILING STOP (amber), EXPIRED (muted)
- Click row → expands to show full trade lifecycle: rationale, price path mini-chart, where stop/target were set

### Performance Breakdown (Bottom)

**3 panels side by side:**

1. **By Regime**: Table + horizontal bar chart — win rate and avg return per regime zone
2. **By Sector**: Which sectors generated alpha, sorted by total return
3. **Monthly Returns Heatmap**: Grid of months × years, each cell colored by return (green positive, red negative, intensity by magnitude)

---

## 7. Settings Tab

### 7.1 Broker Sub-Tab

- Kite API credentials: API key input, API secret input (masked)
- Stored locally (file-based), never transmitted to any server
- Connection status: green dot "Connected" / red dot "Disconnected"
- "Test Connection" button with loading state
- Future brokers section (greyed out): "Coming soon: Upstox, Angel One, Groww"

### 7.2 Alerts Sub-Tab

- Telegram configuration: Bot token input, Chat ID input, "Test Alert" button
- Toggle switches for alert types:
  - New SIGNAL tier trades (80+ conviction)
  - Regime changes
  - Stop loss hits
  - Risk gate triggers (L1/L2)
  - Daily EOD summary
- Frequency: Instant / Batched every 15 min (radio buttons)

### 7.3 Display Sub-Tab

- Theme: Dark (default, only option for v1 — note: "Light mode coming soon")
- Data refresh interval: 15s / 30s / 60s / Manual (radio buttons)
- Default chart timeframe: dropdown (1D through 5Y)
- Number format: Indian (1,00,000) / International (100,000) toggle
- Timezone: IST (locked for v1)

---

## 8. Cross-Cutting UX Patterns

### Contextual Right Panel

- 400px wide slide-out panel from right edge
- Triggered by clicking any ticker text anywhere in the app
- Content: stock-specific news feed (5 most recent) + trust score badge + mini price chart (100px Lightweight Charts) + active signals for that ticker
- Close: X button, Escape key, or click outside
- Panel overlays — does not navigate away from current view
- Transition: slide in 200ms ease-out, slide out 150ms ease-in

### Loading States

- Skeleton shimmer on all cards and tables while data loads
- Never show blank screens or empty containers without explanation
- Loading duration >300ms triggers skeleton; <300ms shows content directly
- Chart loading: grey rectangle with centered spinner

### Staleness Indicators

- Any data older than its watchdog freshness contract gets an amber "STALE" badge
- Badge shows: "Last updated: 2h ago (expected: every 15m)"
- Top bar shows amber dot next to clock if any critical data is stale
- Matches `pipeline/config/anka_inventory.json` grace_multiplier contracts

### Keyboard Navigation

| Key | Action |
|-----|--------|
| `1` - `5` | Switch primary tabs |
| `/` | Focus ticker search |
| `Esc` | Close right panel / close expanded card |
| `←` `→` | Switch sub-tabs within current tab |
| `j` / `k` | Navigate up/down in lists |

### Responsive Behavior

| Breakpoint | Layout |
|------------|--------|
| 1440px+ | Full layout: sidebar + main + right panel |
| 1024px | Sidebar collapses to icons only, right panel overlays fully |
| 768px | Sidebar becomes bottom nav (5 icons), single column content, right panel is full-screen modal |
| <768px | Simplified read-only view — no trading actions, stacked cards |

### Error States

- API connection lost: top bar shows red banner "Connection lost — retrying..."
- Data load failure: card shows error message with "Retry" button
- Empty states: helpful message + guidance (e.g., "No signals today — regime is RISK-OFF, spreads are paused")

---

## 9. API Endpoints (REST)

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/regime` | GET | Current regime zone, MSI, stability, timestamp |
| `/api/signals` | GET | Active + recent closed signals with full metadata |
| `/api/signals/{ticker}` | GET | Signals for a specific ticker |
| `/api/spreads` | GET | Eligible spreads from regime trade map |
| `/api/trust-scores` | GET | Full 213-stock trust score universe |
| `/api/trust-scores/{ticker}` | GET | Individual stock scorecard detail |
| `/api/track-record` | GET | Shadow P&L summary + closed trades |
| `/api/track-record/equity-curve` | GET | Time-series data for equity curve chart |
| `/api/news/macro` | GET | General/macro news feed |
| `/api/news/{ticker}` | GET | Stock-specific news for contextual panel |
| `/api/charts/{ticker}` | GET | OHLCV data for Lightweight Charts |
| `/api/ta/{ticker}` | GET | TA fingerprint card + active patterns |
| `/api/risk-gates` | GET | Current risk gate status |
| `/api/health` | GET | System health + data freshness status |

### WebSocket

- `ws://localhost:8501/ws` — pushes regime changes, new signals, price updates, alert events
- Client subscribes to topics: `regime`, `signals`, `prices:{ticker}`, `alerts`

---

## 10. File Structure

```
pipeline/terminal/
├── __init__.py
├── app.py                  # FastAPI application, static file mount
├── api/
│   ├── __init__.py
│   ├── regime.py           # /api/regime endpoints
│   ├── signals.py          # /api/signals endpoints
│   ├── spreads.py          # /api/spreads endpoints
│   ├── trust_scores.py     # /api/trust-scores endpoints
│   ├── track_record.py     # /api/track-record endpoints
│   ├── news.py             # /api/news endpoints
│   ├── charts.py           # /api/charts endpoints
│   ├── ta.py               # /api/ta endpoints
│   └── websocket.py        # WebSocket handler
├── static/
│   ├── index.html          # Single entry point
│   ├── css/
│   │   └── terminal.css    # Design system tokens + component styles
│   ├── js/
│   │   ├── app.js          # Router, tab management, keyboard shortcuts
│   │   ├── components/
│   │   │   ├── regime-banner.js
│   │   │   ├── signal-card.js
│   │   │   ├── spread-card.js
│   │   │   ├── trust-heatmap.js
│   │   │   ├── equity-curve.js
│   │   │   ├── kpi-card.js
│   │   │   ├── news-feed.js
│   │   │   ├── context-panel.js
│   │   │   └── ta-fingerprint.js
│   │   ├── pages/
│   │   │   ├── dashboard.js
│   │   │   ├── trading.js
│   │   │   ├── intelligence.js
│   │   │   ├── track-record.js
│   │   │   └── settings.js
│   │   └── lib/
│   │       ├── charts.js   # Lightweight Charts wrapper
│   │       ├── ws.js       # WebSocket client
│   │       └── api.js      # REST API client
│   └── assets/
│       └── icons/          # Lucide SVG icons (bundled)
└── cli.py                  # `anka serve` CLI entry point
```

---

## 11. Non-Goals (Explicitly Out of Scope for V1)

- Multi-broker integration (Upstox, Angel One, etc.)
- Performance fee calculation and billing
- Live order execution through the terminal
- Light mode theme
- Mobile-native app (PWA or native)
- User authentication / multi-user support
- Cloud hosting — this is a local-only application
- Custom indicator creation by users

---

## 12. Success Criteria

| Criterion | Measure |
|-----------|---------|
| Visual quality | Passes ui-ux-pro-max pre-delivery checklist (accessibility, contrast, touch targets, responsive) |
| Data accuracy | Every number in the terminal traces to a pipeline JSON file — zero computed values in frontend |
| Performance | Initial load <2s, tab switch <200ms, chart render <500ms |
| Staleness visibility | All data shows freshness; stale data is visibly flagged |
| Keyboard navigable | All primary actions reachable via keyboard shortcuts |
| Responsive | Usable at 768px+ with graceful degradation |
| Distribution | Single `pip install` + `anka serve` — no Node.js, no build step |
