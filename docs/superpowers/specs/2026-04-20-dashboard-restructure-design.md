# Dashboard Restructure — Design Spec

**Date:** 2026-04-20
**Status:** Approved (brainstorm complete, ready for implementation plan)
**Scope:** Project A only — terminal UI restructure. Projects B/C tracked separately.

## Problem

Current `pipeline/terminal/static/js/pages/dashboard.js` is a single page mixing four distinct concerns:

1. Open shadow positions (real money-at-risk surface)
2. Eligible spreads from `INDIA_SPREAD_PAIRS` (static config browsing)
3. Stock recommendations from Phase B ranker (regime-derived)
4. Regime banner + KPI cards (state summary)

Symptoms:
- "Open Positions P&L" header miscounts (5 vs 6) due to race between writer and reader
- KAYNES appears as SHORT in Active Positions (Phase C) AND LONG HIGH in Stock Recommendations (Phase B) on the same screen
- Top Eligible Spreads showed only win-rate without legs or today's conviction (partial fix shipped 2026-04-20)
- User cannot tell at a glance which surface is "money on the table" vs "things the system is thinking about"
- Static `INDIA_SPREAD_PAIRS` is the only spread source; no path for dynamically generated pairs

Discovery phase runs until **2026-06-01**. During this phase the conviction threshold may move (currently 80, may drop to 65), basket composition may change, new candidate sources will land. The UI must not require structural rework when these knobs move.

## Decisions

### D1. Dashboard tab is live positions only

Dashboard is the "money is on the table, watch it carefully" surface. Nothing speculative.

**Top section:** Open Positions table — entry, current, P&L, stop, target, exit triggers, days held, source signal that opened the position.
**Bottom section:** Portfolio aggregates / P&L scenario strip — total open exposure, gross/net, scenario P&L (regime flip, key stop levels hit).

**No watch list on Dashboard.** Watch/browse activity moves to Trading tab.

**Feed source:** Dashboard is fed exclusively by the signal-execution layer (auto-opened shadow positions). No tab promotes positions onto Dashboard via user action. When Layer 8 (Kite) wires in, the same UI continues to work — only the broker backend underneath changes.

### D2. Trading tab is read-only candidate browser

Single scannable table of all `tradeable_candidates[]` regardless of source. Filter chips above the table for Source / Conviction / Horizon. Click a row → expandable inline drawer with full narration (scorecard delta, regime context, why it qualified, last backtest stats, related Phase A/B/C history, **Spread Intelligence 5-layer narration** for spread candidates).

**No promote/act buttons.** If the user takes a trade based on something on Trading without the system formally signaling it, that is their judgment — the system does not endorse it and does not auto-create a Dashboard position from it.

Sub-tabs (Spreads / Singles / Options) rejected: forces a taxonomy on engine output that is not always clean. Source tag becomes a column instead.

### D3. Schema split — tradeable_candidates vs signals

Two separate arrays in the same feed file. Drives the Trading vs Scanner tab split.

```json
{
  "tradeable_candidates": [
    {
      "source": "static_config" | "regime_engine" | "dynamic_pair_engine",
      "name": "Pharma vs Banks",
      "long_legs": ["SUNPHARMA", "DRREDDY"],
      "short_legs": ["HDFCBANK", "ICICIBANK"],
      "conviction": "HIGH" | "MEDIUM" | "LOW",
      "score": 87,
      "horizon_days": 5,
      "horizon_basis": "mean_reversion" | "event_decay" | "regime_persistence",
      "sizing_basis": "notional" | "delta_neutral" | "vol_scaled" | null,
      "reason": "regime=NEUTRAL, scorecard delta favours longs, z=-1.8"
    }
  ],
  "signals": [
    {
      "source": "ta_scanner" | "oi_anomaly" | "correlation_break",
      "name": "APLAPOLLO DMA200_CROSS_UP",
      "ticker": "APLAPOLLO",
      "event_type": "DMA200_CROSS_UP",
      "fired_at": "2026-04-20T10:15:00+05:30",
      "context": { ... },
      "suggests_pair_with": null
    }
  ]
}
```

**Rationale for the split:** a TA pattern hit (`DMA200_CROSS_UP`) is an *event*, not a *trade* — it has no legs, no implied short, no horizon. Forcing it into `long_legs:["APLAPOLLO"], short_legs:[]` makes the UI lie ("the system suggests buying APLAPOLLO") when the truth is closer to "look at this." Splitting into two arrays preserves honesty.

**Rationale for `horizon_basis`:** `5d` means different things from different engines. Mean-reversion 5d (static spreads) decays differently from event-decay 5d (Phase B). Without `horizon_basis`, any sort/filter on horizon would conflate them.

**Rationale for `sizing_basis`:** populated where the engine knows how to translate legs into share counts (delta-neutral, vol-scaled, equal-notional). Null today for sources that don't compute it. Costs nothing now, prevents a Kite-execution refactor later.

### D4. Tab map (Intelligence distributed)

| Tab | Question it answers | Key contents |
|---|---|---|
| **Dashboard** | What's at risk right now? | Open positions, stops, targets, live P&L, scenarios |
| **Trading** | What can I trade? | `tradeable_candidates[]` table, filter chips, expandable narration drawer |
| **Regime** *(new)* | Where is the market? | ETF engine (31 ETFs, weights, drivers, zone, hysteresis), MSI secondary, Phase A playbook, Phase B daily ranker, Phase C correlation breaks |
| **Scanner** *(new/promoted)* | What's moving / unusual? | `signals[]` — TA fingerprint hits, OI anomalies, correlation-break events. Read-only events, not trades. |
| **Trust** | Who can I trust? | OPUS ANKA scorecards, history, methodology, Project C backtest result |
| **News** | What just happened? | News intelligence layers 1/2/3, event log, classification, anomaly detection |
| **Options** | What does OI say? | Max-pain, pinning, synthetic options pricing, leverage matrix |
| **Risk** *(new)* | Am I within bounds? | Risk gates (L0/L1/L2), sizing factors, cumulative P&L, drawdown, stress scenarios |
| **Research** | What are we writing? | Articles, daily narrative, market commentary |

No monolithic "Intelligence" tab. Each tab answers one question and has one feed.

### D5. Spread Intelligence narration lives in Trading drawer, not Regime tab

The 5-layer narration (regime gate → scorecard delta → technicals → news → composer) is per-candidate ("why is Pharma vs Banks on the watch list today?"), so it belongs next to the candidate in Trading's expandable row drawer. Regime tab stays focused on market state, not per-trade explanations.

### D6. Mode-agnostic position terminology

"Open Positions" stays as the label whether system is paper-trading or live. Shadow vs real is the *execution mode* of the system, not a property of the position. A subtle `MODE: SHADOW` badge in the page header is acceptable; per-row `Shadow Position` / `Paper Position` prefixes are not. (See `memory/feedback_open_position_terminology.md`.)

## Architecture

### Component boundaries

```
pipeline/terminal/static/js/pages/
├── dashboard.js          (Open Positions only — D1)
├── trading.js            (NEW: tradeable_candidates browser — D2)
├── regime.js             (NEW or split out — D4)
├── scanner.js            (NEW: signals[] events — D3, D4)
├── trust.js              (existing, unchanged this project)
├── news.js               (existing, unchanged this project)
├── options.js            (existing, unchanged this project)
├── risk.js               (NEW — D4)
└── research.js           (existing, unchanged this project)

pipeline/terminal/static/js/components/
├── positions-table.js    (NEW: stop/target/exit triggers, formerly part of signals-table)
├── candidates-table.js   (NEW: filterable table for Trading)
├── candidate-drawer.js   (NEW: expandable row narration)
├── filter-chips.js       (NEW: source/conviction/horizon)
├── signals-feed.js       (NEW: event-shaped rows for Scanner)
├── scenario-strip.js     (NEW: P&L scenarios for Dashboard)
└── (existing components retained where unchanged)

pipeline/terminal/api/
├── positions.py          (NEW or extracted: feeds Dashboard)
├── candidates.py         (NEW: returns tradeable_candidates[] + signals[] from existing files)
├── regime.py             (existing, may add detail endpoints)
└── risk.py               (NEW: feeds Risk tab)
```

### Data flow (no new pipeline writers in this project)

Project A is purely a UI restructure. **No new engines, no new scheduled tasks.** It re-shapes the existing feed files into the new schema and reorganizes how the terminal consumes them.

- `tradeable_candidates[]` is composed at API layer from existing files: `today_regime.json` (eligible_spreads with conviction merged in — already done), `recommendations.json` (Phase B ranker output), and signal events.
- `signals[]` is composed from `ta_fingerprints/` events, OI anomaly outputs, and Phase C correlation breaks.
- Dashboard's positions feed continues to come from the existing shadow-positions writer.

When Project B (dynamic pair engine) lands, it writes `pipeline/data/dynamic_pairs.json` in the same `tradeable_candidates[]` shape, and the API layer concatenates it into the response. Trading tab automatically picks them up tagged `source=dynamic_pair_engine`. Zero UI changes.

### Error handling

- Each API endpoint returns a partial response on individual feed failures (existing pattern via `Promise.allSettled`).
- Empty states: every table shows a "No <X> available" row rather than collapsing to nothing.
- Stale-data badge on candidate rows when source feed is older than its expected freshness (uses existing watchdog inventory).

### Testing

- Each new component gets a smoke test that renders with empty data, partial data, and full data without throwing.
- Each new API endpoint gets a test that verifies schema shape against frozen fixtures.
- Manual checklist: open positions show stops; filter chips persist across reloads; row drawer opens/closes; no "5 vs 6" race (positions header reads from same snapshot the table renders).
- No backtest or alpha-validation work in Project A — that is Project C.

## Out of scope (tracked separately)

- **Project B — Dynamic Pair Engine.** Generates pairs from the 215-stock universe, writes `pipeline/data/dynamic_pairs.json` in the schema above. Separate brainstorm. Sequenced **after** Project C completes (C's result determines whether one whole class of B's output is viable).
- **Project C — Trust-as-beta backtest.** Validates whether trust-score delta is exploitable as a within-sector spread (e.g. long ICICI / short Bandhan on bank-stress days). 1-2 hours. Runs **before** Project B's brainstorm. Result lives on Trust tab.
- **Layer 8 (Kite live execution).** Schema accommodates it via `sizing_basis` field. Wiring happens later.
- **KAYNES Phase B vs Phase C contradiction.** Underlying issue: `MIN_PRECEDENTS=5` rule used in spread engine is not enforced in stock ranker. Engine-side fix, not UI.
- **Position-counter race (5 vs 6).** Fixed implicitly when Dashboard reads positions from a single snapshot for both header and table.

## Open issues to flag during implementation

- Determine the exact API contract for the composed `tradeable_candidates[]` endpoint before building consumers (composition rules, ordering, dedup of same name from multiple sources).
- Confirm filter-chip state persistence: localStorage per tab, or URL-encoded? URL preferred so links can deep-link to filtered views.
- Decide whether Risk tab includes an interactive scenario builder or read-only current state (lean read-only first, scenario builder later).

## Discovery-phase compatibility

- Conviction threshold change (80 → 65, etc.): no code change needed. The threshold determines what gets `tier=SIGNAL` upstream; Trading tab filters by conviction client-side. Dashboard is unaffected (it consumes positions, not signals).
- New candidate sources: add to API composition layer, tag with new `source` value. Filter chips accept new source values from the data, not a hardcoded list.
- Basket composition changes: no impact (Trading consumes whatever the API returns).

This spec is intentionally narrow on visual styling — exact column widths, colors, spacing follow existing terminal style and are decided during implementation, not here.
