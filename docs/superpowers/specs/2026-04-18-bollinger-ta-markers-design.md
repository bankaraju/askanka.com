# Bollinger Bands + TA Pattern Markers — Design

> **Date:** 2026-04-18
> **Branch:** master
> **Status:** Approved — ready for implementation

---

## 1. Problem

The Charts sub-tab shows raw candlesticks with no indicators. The operator must
mentally compute support/resistance, volatility compression, and pattern recognition.
The TA fingerprint data exists but is only shown as text cards in the TA sub-tab —
not overlaid on the actual chart where it would be actionable.

## 2. Solution

Add client-side computed Bollinger Bands and candlestick pattern markers directly
on the chart. No backend changes — all computation from OHLCV data already in the
browser.

## 3. Bollinger Bands

Three line series overlaid on the candlestick chart:

| Line | Computation | Style |
|------|------------|-------|
| Middle | 20-day SMA | Gold (#f59e0b), 1px solid |
| Upper | SMA + 2σ | Blue (#3b82f6), 1px, 0.5 opacity |
| Lower | SMA - 2σ | Blue (#3b82f6), 1px, 0.5 opacity |

### Squeeze Detection

When Bollinger bandwidth (upper - lower) / middle falls below the 20th percentile
of the last 100 periods, the bands are in a squeeze — volatility compression that
often precedes a breakout. Visual cue: middle band line turns amber during squeeze.

### Computation (JS)

For each candle at index i (where i >= 19):
1. SMA = average of close[i-19..i]
2. σ = standard deviation of close[i-19..i]
3. Upper = SMA + 2σ
4. Lower = SMA - 2σ
5. Bandwidth = (upper - lower) / SMA

## 4. Pattern Markers

Rendered via Lightweight Charts `setMarkers()` on the candlestick series.

### Patterns Detected

| Pattern | Detection Logic | Shape | Color |
|---------|----------------|-------|-------|
| Doji | abs(open - close) < 10% of (high - low), and (high - low) > 0 | diamond | #94a3b8 (grey) |
| Hammer | lower_shadow > 2× body, upper_shadow < 30% range, body in upper third | arrowUp | #10b981 (green) |
| Inverted Hammer | upper_shadow > 2× body, lower_shadow < 30% range, body in lower third | arrowDown | #ef4444 (red) |
| Bullish Engulfing | Prior candle red, current green, current body engulfs prior body | arrowUp | #10b981 (green) |
| Bearish Engulfing | Prior candle green, current red, current body engulfs prior body | arrowDown | #ef4444 (red) |
| BB Breakout Up | close > upper band (previous close was below) | arrowUp | #3b82f6 (blue) |
| BB Breakout Down | close < lower band (previous close was above) | arrowDown | #d97706 (amber) |

### Marker Density

Only compute and display markers for the last 60 trading days. This prevents
visual clutter from 5 years of pattern noise while showing recent actionable
signals.

### Marker Format (Lightweight Charts v4)

```javascript
{
  time: '2026-04-15',
  position: 'belowBar',    // or 'aboveBar'
  color: '#10b981',
  shape: 'arrowUp',        // arrowUp, arrowDown, circle, square
  text: 'Hammer',
}
```

Multiple markers on the same candle: Lightweight Charts stacks them. If both a
Doji and BB Breakout fire on the same day, both markers appear.

## 5. Toggle Controls

A row of checkbox toggles above the chart:

```
☑ Bollinger  ☑ Patterns
```

- **Bollinger toggle:** Shows/hides the 3 line series (SMA, upper, lower)
- **Patterns toggle:** Shows/hides all markers on the candlestick series
- Default: both ON
- State persists during session (not across page reloads)

### Styling

Checkboxes use the existing `.filter-toggle` class from the terminal design system.
Active state: gold border + gold text. Inactive: muted border.

## 6. Files Changed

| File | Change |
|------|--------|
| `pipeline/terminal/static/js/pages/trading.js` | Modify `createChart()` to add BB lines + pattern markers. Add computation functions. Add toggle wiring. |
| `pipeline/terminal/static/css/terminal.css` | Add `.chart-toggles` flex row styling |

No backend changes. No new API endpoints. No new Python files.

## 7. Scope Boundaries

**In scope:**
- Bollinger Bands (20, 2) overlay with squeeze detection
- 7 candlestick/BB pattern markers with density control
- Toggle checkboxes for Bollinger and Patterns
- Client-side computation only

**Out of scope:**
- Other indicators (RSI, MACD, moving averages beyond BB)
- Configurable BB period/deviation
- Pattern alerts or signals
- Backend computation
- Saving toggle preferences across sessions
