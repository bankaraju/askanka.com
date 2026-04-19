# TA Scanner + Shared Ticker State — Design Spec

## Goal

Add a filterable TA pattern scanner as the first sub-tab in the Trading tab, and make the selected ticker persist across Charts/TA/Scanner sub-tabs so the user can freely navigate without retyping.

## Architecture

Two independent features that compose together:

1. **Scanner sub-tab** — filter 213 stocks by TA pattern conviction (win rate, direction, occurrences), display as card grid grouped by stock, click to drill into Charts/TA.
2. **Shared ticker state** — a JavaScript-level state variable that Charts, TA, and Scanner all read/write. Selecting a stock anywhere updates all sub-tabs.

No new data pipeline. No LLM-generated content. Reads existing `/data/ta_fingerprints/*.json` files.

## Backend

### New endpoint: `GET /api/scanner`

**File:** `pipeline/terminal/api/scanner.py`

**Query parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `min_win` | int | 60 | Minimum win_rate_5d as percentage (0-100) |
| `direction` | str | `ALL` | Filter: `ALL`, `LONG`, `SHORT` |
| `min_occ` | int | 10 | Minimum occurrences |
| `sort` | str | `win_rate` | Sort key: `win_rate`, `avg_return`, `occurrences` |
| `significance` | str | `STRONG,MODERATE` | Comma-separated significance levels |

**Logic:**
1. Read all `*.json` files from `pipeline/data/ta_fingerprints/`
2. For each stock, extract `fingerprint` array
3. Filter patterns by: `win_rate_5d >= min_win/100`, direction match, `occurrences >= min_occ`, significance match
4. Group remaining patterns by stock symbol
5. For each stock group: compute `best_win` (max win_rate_5d), `pattern_count`, attach `personality` and `best_pattern` from the fingerprint file
6. Sort stock groups by the chosen sort key (descending)
7. Return only stocks that have >= 1 matching pattern

**Response schema:**
```json
{
  "stocks": [
    {
      "symbol": "RELIANCE",
      "personality": "mixed",
      "best_win": 0.72,
      "pattern_count": 3,
      "patterns": [
        {
          "pattern": "ATR_COMPRESSION",
          "direction": "LONG",
          "significance": "STRONG",
          "win_rate_5d": 0.72,
          "avg_return_5d": 2.1,
          "avg_return_10d": 3.4,
          "avg_drawdown": -1.8,
          "occurrences": 45,
          "last_occurrence": "2026-04-14"
        }
      ]
    }
  ],
  "total_stocks": 12,
  "total_patterns": 47,
  "filters": {
    "min_win": 70,
    "direction": "ALL",
    "min_occ": 10,
    "sort": "win_rate"
  }
}
```

**Registration:** Add router to `pipeline/terminal/app.py` under `/api` prefix.

**Caching:** The 213 fingerprint files total ~2MB. Read them all on first request, cache in a module-level dict with a 5-minute TTL. Subsequent filter requests hit the cache.

## Frontend

### Shared ticker state

**File:** `pipeline/terminal/static/js/pages/trading.js`

A module-level variable `_activeTicker` (initially `null`) that all sub-tabs read/write.

**Functions:**
- `setActiveTicker(symbol)` — sets `_activeTicker`, updates the badge UI, re-renders the currently visible sub-tab if it uses the ticker
- `getActiveTicker()` — returns current ticker or null
- `clearActiveTicker()` — resets to null, removes badge, resets sub-tabs to their empty/search state

**Badge UI:** A small bar below the sub-tab buttons, visible only when `_activeTicker` is set:
```
Viewing: RELIANCE — Reliance Industries  [✕]
```
Styled with gold border, consistent with terminal design. The ✕ calls `clearActiveTicker()`.

**Integration points:**
- Scanner card click → `setActiveTicker(symbol)` + switch to Charts sub-tab
- Charts ticker search → `setActiveTicker(symbol)` (existing search, just add the setter)
- TA ticker search → `setActiveTicker(symbol)` (same)
- Sub-tab switch → if `_activeTicker` is set, auto-load that ticker's data instead of showing empty state

### Scanner sub-tab

**Position:** First sub-tab in Trading (before Signals).

**Filter bar:** Row of button groups for each filter parameter. Active button highlighted with gold border. Changing any filter re-fetches `/api/scanner` with updated params.

**Card grid:** CSS grid, 3 columns (collapses to 2 at 768px, 1 at 480px). Each card:
- Header: stock symbol (gold, bold) + badge showing pattern count + direction color
- Body: one row per matching pattern — `PATTERN_NAME  win%  ·  avg_return%  ·  occurrences×`
- Footer: `Best: PATTERN_NAME · Last fired DATE`
- Hover: gold border highlight
- Click: calls `setActiveTicker(symbol)` + switches to Charts

**Result count:** Right-aligned in filter bar — "12 stocks · 47 patterns"

### Sub-tab order change

Current: `Signals | Spreads | Charts | TA`
New: `Scanner | Signals | Spreads | Charts | TA`

The `renderTrading()` function's sub-tab array gets Scanner prepended. Default active sub-tab becomes Scanner.

## Pattern stat narration

Each pattern row in the Scanner card and in the TA sub-tab detail view shows a compact stat line. This is template-rendered, not LLM-generated:

```
ATR_COMPRESSION  72%  ·  +2.1%  ·  45×
```

Where:
- `72%` = `win_rate_5d` formatted as percentage, green if >= 65%, yellow if >= 55%, red below
- `+2.1%` = `avg_return_5d` with sign
- `45×` = `occurrences` count

The card footer adds: `Best: ATR_COMPRESSION · Last fired Apr 14`

In the TA sub-tab detail view (after clicking through), each pattern card also shows:
- `avg_return_10d` as a secondary stat
- `avg_drawdown` as worst case
- `Fired N times in 5 years. Won X% over 5 days. Avg +Y%, worst -Z%.`

This one-liner is the "narration" — factual, templated, no LLM.

## What we are NOT building

- No spread filtering or spread-level conviction in the Scanner
- No LLM-generated narration or commentary
- No new data pipeline or fingerprint changes
- No changes to Signals or Spreads sub-tabs
- No changes to the Intelligence or Track Record tabs
- No persistent storage of filter preferences (resets on page reload)

## Testing

1. **Scanner API:** Test with various filter combinations, empty results, edge cases (min_win=100 returns nothing, min_win=0 returns everything)
2. **Shared ticker state:** Test that selecting in Scanner propagates to Charts and TA, that selecting in Charts propagates to TA, that clearing works
3. **Card rendering:** Test with stocks that have 0, 1, 5+ matching patterns
4. **Responsive:** Verify grid collapses at 768px and 480px breakpoints
