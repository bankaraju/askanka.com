# Research Tab — Intelligence Digest Design

> **Date:** 2026-04-18
> **Branch:** feat/data-freshness-watchdog
> **Status:** Approved — ready for implementation plan

---

## 1. Problem

The terminal's Research sub-tab (inside Intelligence) displays editorial articles
(Epstein investigations, geopolitical analysis) that belong on the public website.
The terminal is the operator's cockpit — it should present the pipeline's reasoning
in a format that can be interrogated, not consumed passively.

## 2. Solution

Replace the article-card renderer with a **two-column intelligence digest** that
presents Thesis (left) vs Evidence (right). Every number is grounded against source
JSON. Every claim is paired with its proof.

## 3. Layout — The Courtroom

```
┌──────────────────────────────────────────────────────────┐
│  RESEARCH — Intelligence Digest               [09:25 IST]│
├─────────── THESIS (The Claim) ──┬── EVIDENCE (The Proof) ┤
│                                 │                        │
│  1. REGIME THESIS               │  3. CORRELATION BREAKS │
│  Why are we in {zone}?          │  What is behaving wrong?│
│  - ETF drivers (top 3 weights)  │  - Phase C deviations  │
│  - FII flows (net ₹)           │    (|z| > 1.5σ)        │
│  - India VIX level              │  - OI confirmation     │
│  - Stability (days in zone)     │  - Decision: WARNING / │
│  - Flip triggers                │    OPPORTUNITY          │
│                                 │  - Click ticker →      │
│  2. SPREAD THESES               │    context panel       │
│  What trades fit this world?    │                        │
│  - Each SIGNAL-tier spread      │  4. BACKTEST VALIDATION│
│  - Action / conviction / z-score│  Has this worked before?│
│  - Regime fit check             │  - 716-day replay data │
│  - Trust gate status            │  - Episode count       │
│  - OI confirmation              │  - Win rate + CI bounds│
│  - Caution badges from evidence │  - Status: WITHIN_CI / │
│                                 │    EDGE_CI / OUTSIDE_CI│
└─────────────────────────────────┴────────────────────────┘
```

Reading order: 1 (top-left) → 3 (top-right) → 2 (bottom-left) → 4 (bottom-right).
Thesis and its corresponding Evidence are at the same vertical level.

## 4. Data Sources — No New Pipelines

Every card reads from files the clockwork already produces.

| Card | Source Files | Key Fields |
|------|-------------|------------|
| Regime Thesis | `pipeline/data/today_regime.json` | zone, msi_score, stability_days |
| | `autoresearch/etf_optimal_weights.json` | top 3 ETF weights by magnitude |
| | `data/flows/YYYY-MM-DD.json` | fii_net, dii_net |
| Spread Theses | `pipeline/data/recommendations.json` | spreads with action, conviction, z_score |
| | `pipeline/data/today_regime.json` | zone for regime_fit check |
| | `pipeline/data/positioning.json` | OI confirmation per leg |
| Correlation Breaks | `pipeline/data/correlation_breaks.json` | ticker, z_score, direction, decision |
| | `pipeline/data/positioning.json` | OI buildup type |
| Backtest Validation | `autoresearch/regime_trade_map.json` | per-spread per-regime: episodes, win_rate, avg_return |

## 5. Grounding Enforcer

The terminal must never hallucinate. Every numeric claim in a digest card is
validated against the raw source JSON before the API response is sent.

### Design Principle

No LLM-generated prose enters the digest. All text is template-based:
```
"Zone: {zone} | VIX: {vix} | FII: ₹{fii_net}cr | Stability: {stability_days}d"
```

Templates are filled from source JSON values. The grounding gate is a safety net
on top of this, not the primary defence.

### Validation Logic

For each card in the digest response:
1. Extract every numeric value from the rendered card
2. Compare against the corresponding raw value from the source file
3. Tolerance: 2% relative or 0.01 absolute (whichever is larger)
4. If ANY value fails: replace the card body with an error state:
   `"GROUNDING FAILURE: {field} claimed {X}, source says {Y}"`
5. Set `grounding_ok: false` on the card
6. Log the failure to `data/grounding_failures.json` with timestamp and details

### What This Prevents

- Template bugs that format a number wrong
- Stale file reads (file changed between read and render)
- Future regressions if someone adds LLM summaries later

## 6. Cross-Column Caution Badges

After both columns are built, a reconciliation pass cross-references Evidence
against Thesis cards.

### Rules

For each spread in Spread Theses (card 2):

| Evidence Condition | Badge | Displayed On |
|---|---|---|
| Backtest win_rate < 55% | `CAUTION: LOW WIN RATE` | Spread card (left) |
| Backtest status = EDGE_CI | `CAUTION: EDGE CI` | Spread card (left) |
| Backtest status = OUTSIDE_CI | `BLOCKED: OUTSIDE CI` | Spread card (left) |
| Backtest episodes < 10 | `LOW SAMPLE` | Spread card (left) |
| Correlation break on a spread leg, decision = CONFIRMED_WARNING | `BREAK: {ticker}` | Spread card (left) |

### Rendering

- Amber border + Lucide `alert-triangle` icon for CAUTION badges
- Red border + Lucide `shield-alert` icon for BLOCKED badges
- Grey border + Lucide `info` icon for LOW SAMPLE badges
- Tooltip on hover shows which Evidence card triggered the badge

## 7. API Design

### New Endpoint

```
GET /api/research/digest
```

Replaces the old `/api/research` (articles) endpoint entirely.

### Response Schema

```json
{
  "generated_at": "2026-04-18T09:25:00+05:30",
  "regime_thesis": {
    "zone": "EUPHORIA",
    "vix": 12.3,
    "fii_net": 2340,
    "dii_net": -890,
    "stability_days": 4,
    "flip_triggers": ["VIX > 18", "FII outflow 3 consecutive days"],
    "top_etf_drivers": [
      {"name": "XLF", "weight": 0.39},
      {"name": "ARKK", "weight": 0.31},
      {"name": "IEF", "weight": 0.25}
    ],
    "msi_score": 0.72,
    "grounding_ok": true
  },
  "spread_theses": [
    {
      "name": "Defence vs IT",
      "long_leg": "HAL",
      "short_leg": "INFY",
      "action": "ENTER",
      "conviction": 82,
      "z_score": 1.7,
      "regime_fit": true,
      "trust_gate": {"long": "A", "short": "B+", "passed": true},
      "oi_confirm": "CALL_BUILDUP",
      "caution_badges": [],
      "grounding_ok": true
    }
  ],
  "correlation_breaks": [
    {
      "ticker": "HDFCBANK",
      "z_score": -1.8,
      "direction": "DOWN",
      "expected_direction": "UP",
      "oi_confirmation": "PUT_BUILDUP_HEAVY",
      "decision": "CONFIRMED_WARNING"
    }
  ],
  "backtest_validation": [
    {
      "spread": "Defence vs IT",
      "regime": "EUPHORIA",
      "episodes": 23,
      "win_rate": 0.67,
      "avg_return": 0.021,
      "ci_lower": 0.58,
      "ci_upper": 0.76,
      "status": "WITHIN_CI"
    }
  ],
  "grounding_failures": []
}
```

### Removed Endpoint

- `GET /api/research` (articles list) — deleted
- `GET /api/research/{filename}` (article content) — deleted

Articles stay in `articles_index.json` for the website. The terminal no longer
serves them.

## 8. Frontend

### Layout

- CSS grid: `grid-template-columns: 1fr 1fr` with `gap: var(--spacing-lg)`
- Collapses to single column (`1fr`) below 900px
- Each card is a `.card` with the existing terminal design system

### Card Structure

Each of the 4 cards follows:
```
┌──────────────────────────────┐
│ CARD TITLE          [badge?] │
│ Subtitle question            │
├──────────────────────────────┤
│ Content rows                 │
│ Key: Value                   │
│ Key: Value                   │
│ ...                          │
└──────────────────────────────┘
```

### Interaction

- **Ticker click** (Correlation Breaks): Opens existing context panel (right
  sidebar) with `/api/news/{ticker}` + `/api/trust-scores/{ticker}`. Reuses the
  same panel already built in the Trading tab.
- **Auto-refresh**: Every 5 minutes during market hours (09:30-15:30 IST).
  Outside market hours, static.
- **Timestamp header**: Always visible at top — "Last computed: {generated_at}".
  If older than 30 minutes during market hours, shows amber staleness warning.

### Badge Rendering

```javascript
// Caution badge template
`<span class="badge badge--amber" title="${tooltip}">
  <i data-lucide="alert-triangle"></i> ${label}
</span>`

// Blocked badge template
`<span class="badge badge--red" title="${tooltip}">
  <i data-lucide="shield-alert"></i> ${label}
</span>`

// Low sample badge template
`<span class="badge badge--muted" title="${tooltip}">
  <i data-lucide="info"></i> ${label}
</span>`
```

## 9. What Gets Removed

| File | Change |
|------|--------|
| `pipeline/terminal/api/research.py` | Rewritten: article endpoints → digest endpoint |
| `pipeline/terminal/static/js/pages/intelligence.js` | `renderResearch()` rewritten entirely |
| Article badge logic (INVESTIGATION/GEOPOLITICAL) | Deleted |
| Article card click handler | Deleted |

## 10. Testing

| Test | Validates |
|------|-----------|
| Digest endpoint returns valid schema | API contract |
| Grounding gate catches deliberate mismatch | No hallucination mandate |
| Grounding gate passes correct data | No false positives |
| Caution badge fires when backtest win_rate < 55% | Cross-column logic |
| BLOCKED badge fires when outside CI | Cross-column logic |
| Correlation break badge propagates to spread | Cross-column logic |
| Empty correlation_breaks returns empty list (not error) | Graceful degradation |
| Missing source file returns error state (not crash) | Resilience |
| Stale timestamp triggers amber warning | Operator awareness |

## 11. Acceptance Gate Alignment

This design supports the 15-day Acceptance Gate from Golden Goose Plan 4:
- Shadow trades are visible in Track Record tab
- Backtest validation provides the statistical baseline
- Caution badges surface when live performance drifts from backtest CI
- The operator sees claim vs proof every morning — the system can't hide bad results

## 12. Scope Boundaries

**In scope:**
- Replace Research sub-tab with intelligence digest
- New backend endpoint with grounding enforcement
- Cross-column caution badge logic
- Ticker click → context panel wiring
- Auto-refresh during market hours
- 9 tests

**Out of scope:**
- Changes to other tabs (Dashboard, Trading, Track Record)
- New pipeline scripts or scheduled tasks
- Settings tab (separate work item)
- Website article changes
