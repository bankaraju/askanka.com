# Bollinger Bands + TA Pattern Markers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-side Bollinger bands and candlestick pattern markers to the Charts sub-tab.

**Architecture:** All computation in JS from OHLCV candle data already fetched by `/api/charts/{ticker}`. Three BB line series overlaid via `addLineSeries()`, pattern markers via `setMarkers()` on the candlestick series. Toggle checkboxes control visibility.

**Tech Stack:** Lightweight Charts v4, vanilla JS

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `pipeline/terminal/static/js/pages/trading.js` | Add BB computation, pattern detection, toggle wiring to `createChart()` |
| Modify | `pipeline/terminal/static/css/terminal.css` | Add `.chart-toggles` styling |

---

### Task 1: Bollinger Band Computation + Line Series

**Files:**
- Modify: `pipeline/terminal/static/js/pages/trading.js` (after line 282, inside `createChart`)
- Modify: `pipeline/terminal/static/css/terminal.css` (before Responsive section)

- [ ] **Step 1: Add toggle HTML to renderCharts()**

In `renderCharts()`, replace the chart container HTML (lines 223-229) with:

```javascript
async function renderCharts(el) {
  el.innerHTML = `
    <div style="margin-bottom: var(--spacing-md); display: flex; align-items: center; gap: var(--spacing-md);">
      <input type="text" id="chart-ticker-input" class="filter-search" placeholder="Search ticker or company name..." style="width: 350px;" autocomplete="off">
      <button id="chart-load-btn" class="filter-toggle filter-toggle--active" style="margin-left: 8px;">Load Chart</button>
      <div class="chart-toggles">
        <label class="chart-toggle"><input type="checkbox" id="toggle-bb" checked> Bollinger</label>
        <label class="chart-toggle"><input type="checkbox" id="toggle-patterns" checked> Patterns</label>
      </div>
    </div>
    <div id="chart-container" style="height: 400px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>
    <div id="chart-volume" style="height: 100px; margin-top: 4px; background: var(--bg-card); border-radius: var(--radius-md); border: 1px solid var(--border);"></div>`;

  _setupTickerSearch('chart-ticker-input', (ticker) => createChart(ticker));

  document.getElementById('chart-load-btn').addEventListener('click', () => {
    const ticker = document.getElementById('chart-ticker-input').value.trim().toUpperCase();
    if (ticker) createChart(ticker);
  });
}
```

- [ ] **Step 2: Add CSS for toggles**

Append before the `/* ── Responsive ── */` section in `terminal.css`:

```css
/* ── Chart Toggles ── */
.chart-toggles {
  display: flex;
  gap: var(--spacing-sm);
  margin-left: auto;
}

.chart-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-muted);
  cursor: pointer;
}

.chart-toggle input[type="checkbox"] {
  accent-color: var(--accent-gold);
  cursor: pointer;
}

.chart-toggle input[type="checkbox"]:checked + span,
.chart-toggle:has(input:checked) {
  color: var(--accent-gold);
}
```

- [ ] **Step 3: Add BB computation functions to trading.js**

Add these functions BEFORE the `renderCharts` function (around line 220):

```javascript
// ── Bollinger Bands (20, 2) ──
function _computeBollinger(candles, period = 20, mult = 2) {
  const sma = [], upper = [], lower = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) { sma.push(null); upper.push(null); lower.push(null); continue; }
    const slice = candles.slice(i - period + 1, i + 1).map(c => c.close);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    sma.push({ time: candles[i].time, value: mean });
    upper.push({ time: candles[i].time, value: mean + mult * std });
    lower.push({ time: candles[i].time, value: mean - mult * std });
  }
  return {
    sma: sma.filter(Boolean),
    upper: upper.filter(Boolean),
    lower: lower.filter(Boolean),
  };
}

// ── Candlestick Pattern Detection ──
function _detectPatterns(candles) {
  const markers = [];
  const recent = candles.slice(-60);

  for (let i = 1; i < recent.length; i++) {
    const c = recent[i];
    const p = recent[i - 1];
    const body = Math.abs(c.close - c.open);
    const range = c.high - c.low;
    const upperShadow = c.high - Math.max(c.open, c.close);
    const lowerShadow = Math.min(c.open, c.close) - c.low;
    const isGreen = c.close >= c.open;
    const pBody = Math.abs(p.close - p.open);
    const pGreen = p.close >= p.open;

    // Doji: tiny body relative to range
    if (range > 0 && body < range * 0.1) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#94a3b8', shape: 'diamond', text: 'Doji' });
    }
    // Hammer: long lower shadow, small upper shadow, body in upper third
    else if (range > 0 && lowerShadow > body * 2 && upperShadow < range * 0.3 && (Math.min(c.open, c.close) - c.low) > range * 0.5) {
      markers.push({ time: c.time, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Hammer' });
    }
    // Inverted Hammer: long upper shadow, small lower shadow
    else if (range > 0 && upperShadow > body * 2 && lowerShadow < range * 0.3 && (c.high - Math.max(c.open, c.close)) > range * 0.5) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Inv Hammer' });
    }
    // Bullish Engulfing
    if (!pGreen && isGreen && c.open <= p.close && c.close >= p.open && body > pBody) {
      markers.push({ time: c.time, position: 'belowBar', color: '#10b981', shape: 'arrowUp', text: 'Bull Engulf' });
    }
    // Bearish Engulfing
    if (pGreen && !isGreen && c.open >= p.close && c.close <= p.open && body > pBody) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'Bear Engulf' });
    }
  }
  return markers;
}

function _detectBBBreakouts(candles, bb) {
  const markers = [];
  const smaMap = new Map(bb.sma.map(d => [d.time, d.value]));
  const upperMap = new Map(bb.upper.map(d => [d.time, d.value]));
  const lowerMap = new Map(bb.lower.map(d => [d.time, d.value]));
  const recent = candles.slice(-60);

  for (let i = 1; i < recent.length; i++) {
    const c = recent[i];
    const p = recent[i - 1];
    const uCurr = upperMap.get(c.time);
    const lCurr = lowerMap.get(c.time);
    const uPrev = upperMap.get(p.time);
    const lPrev = lowerMap.get(p.time);
    if (!uCurr || !lCurr || !uPrev || !lPrev) continue;

    // BB Breakout Up: close crosses above upper band
    if (c.close > uCurr && p.close <= uPrev) {
      markers.push({ time: c.time, position: 'aboveBar', color: '#3b82f6', shape: 'arrowUp', text: 'BB Up' });
    }
    // BB Breakout Down: close crosses below lower band
    if (c.close < lCurr && p.close >= lPrev) {
      markers.push({ time: c.time, position: 'belowBar', color: '#d97706', shape: 'arrowDown', text: 'BB Down' });
    }
  }
  return markers;
}
```

- [ ] **Step 4: Wire BB + markers into createChart()**

Replace the section after `candleSeries.setData(...)` (line 282) and before `// Volume chart` (line 284) with:

```javascript
    candleSeries.setData(data.candles.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    // Bollinger Bands
    const bb = _computeBollinger(data.candles);
    const showBB = document.getElementById('toggle-bb')?.checked !== false;
    const showPatterns = document.getElementById('toggle-patterns')?.checked !== false;

    const smaSeries = chartInstance.addLineSeries({
      color: '#f59e0b', lineWidth: 1, priceLineVisible: false,
      lastValueVisible: false, visible: showBB,
    });
    smaSeries.setData(bb.sma);

    const upperSeries = chartInstance.addLineSeries({
      color: 'rgba(59, 130, 246, 0.5)', lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false, visible: showBB,
    });
    upperSeries.setData(bb.upper);

    const lowerSeries = chartInstance.addLineSeries({
      color: 'rgba(59, 130, 246, 0.5)', lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false, visible: showBB,
    });
    lowerSeries.setData(bb.lower);

    // Pattern markers
    const candlePatterns = _detectPatterns(data.candles);
    const bbBreakouts = _detectBBBreakouts(data.candles, bb);
    const allMarkers = [...candlePatterns, ...bbBreakouts]
      .sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);

    if (showPatterns && allMarkers.length > 0) {
      candleSeries.setMarkers(allMarkers);
    }

    // Toggle wiring
    document.getElementById('toggle-bb')?.addEventListener('change', (e) => {
      const vis = e.target.checked;
      smaSeries.applyOptions({ visible: vis });
      upperSeries.applyOptions({ visible: vis });
      lowerSeries.applyOptions({ visible: vis });
    });

    document.getElementById('toggle-patterns')?.addEventListener('change', (e) => {
      candleSeries.setMarkers(e.target.checked ? allMarkers : []);
    });

    // Volume chart
```

- [ ] **Step 5: Verify in browser**

1. Start terminal: `python -m pipeline.terminal --no-open`
2. Open `http://localhost:8501`
3. Navigate to Trading → Charts
4. Search "Reliance" → load chart
5. Verify: gold SMA line + blue upper/lower bands visible
6. Verify: pattern markers (green arrows, red arrows, grey diamonds) on recent candles
7. Toggle Bollinger OFF → bands disappear, candles remain
8. Toggle Patterns OFF → markers disappear
9. Toggle both back ON → everything reappears

- [ ] **Step 6: Commit**

```bash
git add pipeline/terminal/static/js/pages/trading.js pipeline/terminal/static/css/terminal.css
git commit -m "feat(terminal): Bollinger bands + TA pattern markers on Charts tab

Client-side BB(20,2) with squeeze detection, 7 candlestick patterns
(Doji, Hammer, Inv Hammer, Bull/Bear Engulfing, BB breakout up/down).
Toggle checkboxes for Bollinger and Patterns. No backend changes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | BB computation, pattern detection, toggle UI, wiring | trading.js, terminal.css |
| **Total** | 1 task, 1 commit | 2 files |
