# Unified Analysis Panel (UAP) v1 — Design

**Date:** 2026-04-23
**Status:** Brainstorm complete, spec frozen
**Scope:** v1 only — Ticker Brief deferred to v2

---

## Why

The Anka Terminal currently renders four analysis engines through four different visual shapes:

- **Feature Coincidence Scorer (FCS)** — `components/attractiveness-panel.js` (feature contribution bars)
- **Spread Intelligence** — inline 5-layer narration block hardcoded in `components/candidate-drawer.js`
- **Correlation Breaks** — rendered ad-hoc on Scanner and Regime pages
- **Technical Analysis (TA)** — spec exists, not yet built

Traders see four different layouts for what are conceptually sibling outputs. User feedback verbatim: *"otherwise analysis looks broken."*

This spec defines one shared component and one shared data envelope so every analysis engine presents the same five primitives (Verdict, Conviction, Evidence, Model Health, Freshness) in the same visual vocabulary, with the calibration status made explicit so traders can tell walk-forward-earned numbers from heuristic-asserted ones at a glance.

## Scope

**In v1:**
- Shared component: `components/analysis/panel.js`
- Four client-side adapters (FCS, TA, Spread, Correlation Break) mapping engine-native output → shared envelope
- TA Coincidence Scorer v1 (RELIANCE-only pilot per `docs/superpowers/specs/TA Analysis Thoughts for implementation.md`) — includes the TA endpoints this spec's panel consumes
- Clean replace of `attractiveness-panel.js` and the spread 5-layer block in `candidate-drawer.js`
- Drawer on Trading tab uses the unified panel for all four engines

**Out of v1 (explicit):**
- **Ticker Brief page** — a dedicated one-page-per-ticker view that stacks all four analyses. Deferred to v2; v1 component is built to support it when that brainstorm runs.
- **Cross-engine synthesis** — a single "overall score" averaging the four. Verdict stays per-engine; trader reads each independently.
- **WebSocket freshness push** — existing polling / page-refresh pattern stays.
- **TA universe expansion beyond RELIANCE** — separate spec, gated by 60-day forward uplift audit.
- **Walk-forward calibration for Spread / Correlation Break** — both stay `heuristic` in v1; calibration is its own project.

## Architecture decisions (locked)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Scope shape | C — shared anatomy now, Ticker Brief v2 | Coherence today without waiting for v2 schema reconciliation |
| 2 | Anatomy | C — responsive (stacked narrow / header+2col wide) | One component, two surfaces, no duplication |
| 3 | Data contract | B — envelope + `calibration` tag | Matches no-hallucination mandate; cheap now, expensive to retrofit |
| 4 | API shape | B — per-engine endpoints + frontend adapters | Extends existing `/api/attractiveness` pre-fetch pattern; no new backend aggregation layer |
| 5 | Retrofit | A — clean replace | Half-retrofit is the worst outcome; "analysis looks broken" demands one pattern |
| 6 | v1 engine scope | Scope-3 — all four | TA gets built on top of unified spec from day one; no "build then migrate" |

## Code layout

```
pipeline/terminal/static/js/components/analysis/
  panel.js                    shared renderer; responsive via CSS grid + container query
  envelope.js                 envelope shape + defensive parse helpers
  health.js                   band → color + detail formatter
  adapters/
    fcs.js                    /api/attractiveness          → envelope
    ta.js                     /api/ta_attractiveness       → envelope   (new)
    spread.js                 /api/research/digest         → envelope
    corr.js                   /api/correlation_breaks      → envelope
```

**Deletions on day one (the "clean replace"):**
- `components/attractiveness-panel.js` — absorbed into `adapters/fcs.js` + `panel.js`
- `candidate-drawer.js` — the inline `layersHtml` 5-layer block becomes `adapters/spread.js`

**Kept (compact inline surfaces, not panels):**
- `attractiveness-cell.js` (Trading table column)
- `attractiveness-badge.js` (Positions P&L badge)

## Shared envelope

```json
{
  "engine": "fcs | ta | spread | corr_break",
  "ticker": "RELIANCE",
  "verdict": "LONG | SHORT | NEUTRAL | WATCH | NO_SIGNAL | UNAVAILABLE",
  "conviction_0_100": 72,
  "evidence": [
    { "name": "ticker_rs_10d",     "contribution":  0.38, "direction": "pos" },
    { "name": "sector_5d_return",  "contribution":  0.22, "direction": "pos" },
    { "name": "realized_vol_60d",  "contribution": -0.11, "direction": "neg" }
  ],
  "health": { "band": "GREEN | AMBER | RED | UNAVAILABLE", "detail": "mean AUC 0.61 · min 0.54 · 6 folds" },
  "calibration": "walk_forward | heuristic",
  "computed_at": "2026-04-23T14:42:00+05:30",
  "source": "own | cohort | static_config",
  "empty_state_reason": "optional — shown on UNAVAILABLE cards"
}
```

Missing fields become `null` (never `undefined`). Empty evidence = `[]`.

## Engine adapter normalization

| Engine | `conviction_0_100` rule | `calibration` | `verdict` rule | `health` source |
|---|---|---|---|---|
| **FCS** | `score` identity | `walk_forward` | ≥60 LONG, ≤40 SHORT, else NEUTRAL | model band + mean/min AUC |
| **TA** | same math as FCS | `walk_forward` if fitted; else `UNAVAILABLE` + `empty_state_reason: "TA pilot — RELIANCE only, 212 tickers await v2 rollout"` | same as FCS | model band + mean/min AUC |
| **Spread** | PASS+HIGH=80, PASS+MED=60, PASS+LOW=40, FAIL=20 | `heuristic` | LONG on long-leg ticker, SHORT on short-leg, WATCH if gate FAIL | gate status + `spread_stats` freshness |
| **Corr Break** | `min(100, abs(sigma) * 25)` — 4σ saturates at 100 | `heuristic` | If stock has diverged *below* sector (negative σ, "cheap"): LONG. If diverged *above* (positive σ, "rich"): SHORT. \|σ\| < 1.5: NEUTRAL. Mean-reversion semantics, matching Phase C ADD trades. | literal `"heuristic — no calibration yet"` |

**Evidence top-3 source per engine:**
- FCS / TA: logistic contributions (already sorted by `|coef × feature|`)
- Spread: 5 layer results as {regime_gate, scorecard_delta, technicals, news, composer} with ±1 contributions (PASS/FAIL)
- Correlation Break: top-3 of {σ, sector_divergence, volume_anomaly, trust_delta} — raw z-scores

## Engine cadence (freshness semantics)

Each engine refreshes on its own schedule. The panel's `computed_at` reflects the engine's last run — not the page load. Traders reading a card need to know how stale the underlying number is; spelling this out here also tells the watchdog what "fresh" means per engine.

| Engine | Cadence | Typical `computed_at` at 14:00 IST | Watchdog source |
|---|---|---|---|
| **FCS** | Every 15 min during market hours (via `intraday_scan.bat`) | 13:57 | `AnkaFeatureScorerIntraday` (already wired) |
| **TA** | **Daily EOD — 16:00 IST** (`AnkaTAScorerScore`). Not intraday. | Previous session 16:00 | `AnkaTAScorerScore` (new, added with scorer build) |
| **Spread** | Morning scan 09:25 + every 15 min intraday | 13:57 | existing spread-engine watchdog |
| **Corr Break** | Every 15 min intraday (`AnkaCorrelationBreaks`) | 13:57 | `AnkaCorrelationBreaks` (already wired) |

**Implication for the UI:** the TA card during market hours is always showing yesterday's close signal. That's correct by design — TA patterns are daily-bar phenomena — but the card header MUST show the previous-session timestamp prominently, and the `health.detail` field should include "daily bars, EOD cadence" so traders don't mistake it for stale intraday data. Cards from FCS / Spread / Corr Break inside the same drawer will show a 3-5 min timestamp, making the 16:00-previous-day timestamp on TA visually distinct on its own merits — no special badge needed, just honest labeling.

## Data flow

1. **Page-level pre-fetch** (extend existing `trading.js` pattern):
   ```
   Promise.allSettled([
     get('/attractiveness'),
     get('/ta_attractiveness'),
     get('/research/digest'),
     get('/correlation_breaks')
   ]) → attach raw responses to each candidate as candidate.analyses_raw = {fcs, ta, spread, corr}
   ```
2. **Drawer open** — `panel.js` iterates `candidate.analyses_raw`, runs each through its adapter, gets four envelopes.
3. **Render loop** — each envelope becomes one card, stacked inside the drawer.
4. **Responsive layout** — CSS picks at runtime: narrow drawer → stacked rows; future Ticker Brief → header+2col.

## UI behavior

**Card render order (frozen):** `FCS → TA → Spread → Corr Break`. Async adapter resolution never changes panel layout — the render loop iterates a fixed array, so a late FCS response doesn't push TA down. This keeps the visual scan path stable across reloads and across tickers.

**Calibration tag visible in the UI (the no-hallucination mandate made visible):**
- `walk_forward` scores: `conviction_0_100` rendered in `var(--accent-gold)`.
- `heuristic` scores: rendered in `var(--text-muted)` with a dotted underline; tooltip on hover: *"Not calibrated — heuristic mapping from gate/σ."*

**Health band → dot color:** GREEN → `var(--accent-green)`, AMBER → `var(--accent-gold)`, RED → `var(--accent-red)`, UNAVAILABLE → `var(--text-muted)`.

**Freshness rendering:** every card shows `computed_at` as a relative timestamp in the footer (e.g., "3 min ago", "yesterday 16:00"). Cards older than 2× their expected cadence get an amber dot next to the timestamp (matches watchdog's grace-multiplier convention).

**Empty / UNAVAILABLE card:** still renders. Muted colors, no evidence bars, `empty_state_reason` as body text. Hidden cards read as bugs; transparent UNAVAILABLE reads as honest progress.

## Error handling

- `Promise.allSettled` at page level — one slow/errored engine doesn't block the others.
- Per-adapter defensive parse — if response shape doesn't match expected, adapter returns `verdict: "UNAVAILABLE"` + `empty_state_reason: "response malformed (adapter=<name>)"`.
- Missing fields become `null`. Panel has one null-check path, not four.

## Testing contract

- `pipeline/terminal/tests/test_analysis_panel.py` — FastAPI TestClient integration: each engine endpoint → adapter → envelope → golden snapshot assertion.
- Adapter unit tests (Node or jsdom — whichever the existing test runner supports): one fixture per engine covering GREEN / AMBER / UNAVAILABLE / malformed paths. ~20 tests total across 4 adapters.
- Visual fixtures: `pipeline/terminal/tests/fixtures/analysis-panel/*.html` — one HTML snapshot per engine × verdict; rendered at test time and diffed.
- Migration: existing `attractiveness-panel` tests and drawer 5-layer tests are rewritten against the new shape. Net test count goes up, not down.

## Doc-sync mandate (every code change in implementation)

- `docs/SYSTEM_OPERATIONS_MANUAL.md` — new Station 10: Unified Analysis Panel
- `pipeline/config/anka_inventory.json` — `AnkaTAScorerFit` (weekly, warn) + `AnkaTAScorerScore` (daily EOD, warn) entries land with the TA scorer tasks
- `CLAUDE.md` — architecture section gets the Analysis Panel line; Clockwork gets the two TA tasks
- Memory — new `project_unified_analysis_panel.md`, `MEMORY.md` index entry

## Success criteria

1. All four engines render through the same component on the Trading drawer. No engine-specific panels survive.
2. `walk_forward` vs `heuristic` is visually distinguishable without hover — gold vs muted.
3. UNAVAILABLE cards (TA for non-RELIANCE, Spread for tickers without a pair) render with honest prose, not blank or missing.
4. Drawer load time unchanged (±50ms) — `Promise.allSettled` doesn't serialize the fetches.
5. Test count: new adapter + panel tests exceed deleted `attractiveness-panel` + drawer 5-layer tests.
6. Spec-reviewer confirms: Ticker Brief v2 can be built by composing `panel.js` with no refactor to the shared component or adapters.

## Dependencies

- **Blocks:** v2 Ticker Brief spec (future), TA universe expansion spec (future)
- **Blocked by:** TA Coincidence Scorer v1 build (pilot — RELIANCE only). This spec's TA adapter consumes endpoints that scorer produces.
- **Related:** `docs/superpowers/specs/TA Analysis Thoughts for implementation.md` (TA scorer spec)
- **Related:** `memory/project_feature_coincidence_scorer.md` (FCS pattern this mirrors)

## Open questions for implementation plan

- Which existing CSS tokens need extension for `.analysis-card` variants? (Probably none — reuse `--accent-*`, `--text-muted`, `--bg-elevated`, `--font-mono`.)
- Does the TA scorer spec's Task 10 ("TA panel UI") collapse into "build a TA adapter" here? Yes — writing-plans will reconcile.
- How much of FCS's `/api/attractiveness` response needs reshaping vs passing through? Adapter handles it; endpoint unchanged.
