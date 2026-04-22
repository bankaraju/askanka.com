// Live LTP poller (Task FE-2).
//
// Every N seconds, scans the DOM for cells tagged with data-live-ltp-ticker,
// fetches /api/live_ltp?tickers=... in one batch, patches cell textContent
// in place, and recomputes the paired P&L cell (data-live-pnl-ticker).
//
// Presentation-layer only: does NOT rewrite live_status.json or touch
// snapshot-derived values (stop, peak, trail). Those come from the 15-min
// backend snapshot. This loop exists purely to keep LTP + P&L fresh
// between snapshots so the Dashboard doesn't look stale.
//
// Design notes:
//  - Cell lookup happens on every tick, so a 30s Dashboard re-render that
//    replaces the positions-table innerHTML doesn't break us — next tick
//    picks up the fresh cells.
//  - Null values in the response mean "unknown ticker / no live price" —
//    we leave the cell alone so the snapshot value stays visible.
//  - 50-ticker endpoint cap: slice defensively on the client side too.
//  - Fetch errors are swallowed + console.warn'd; next tick retries.

import { get } from '../lib/api.js';

const MAX_TICKERS = 50;

// Match positions-table's fmtPrice: Rs N,NNN.NN (Indian locale, 2 decimals).
function fmtPrice(v) {
  if (v == null || Number.isNaN(v)) return '--';
  return '\u20B9' + Number(v).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtPct(v) {
  return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
}

function pnlClass(v) {
  return v >= 0 ? 'mono text-green' : 'mono text-red';
}

// Update the P&L cell paired with an LTP cell by data-live-pnl-ticker.
function patchPnlCell(ticker, entry, side, ltp) {
  if (!entry || entry === 0 || !Number.isFinite(entry)) return;  // guard div-by-zero
  if (!Number.isFinite(ltp)) return;
  const pnl = side === 'short'
    ? (1 - ltp / entry) * 100
    : (ltp / entry - 1) * 100;
  const cells = document.querySelectorAll(
    `[data-live-pnl-ticker="${ticker}"]`
  );
  cells.forEach(c => {
    c.textContent = fmtPct(pnl);
    c.className = pnlClass(pnl);
  });
}

async function tick() {
  const cells = document.querySelectorAll('[data-live-ltp-ticker]');
  if (!cells || cells.length === 0) return;

  // Collect unique tickers preserving insertion order.
  const seen = new Set();
  const tickers = [];
  cells.forEach(c => {
    const t = c.dataset.liveLtpTicker;
    if (t && !seen.has(t)) {
      seen.add(t);
      tickers.push(t);
    }
  });
  if (tickers.length === 0) return;

  const payload = tickers.slice(0, MAX_TICKERS);
  let data;
  try {
    data = await get('/live_ltp?tickers=' + encodeURIComponent(payload.join(',')));
  } catch (err) {
    console.warn('[live-ticker] poll failed:', err);
    return;
  }

  // Patch each LTP cell whose ticker got a numeric response.
  cells.forEach(c => {
    const ticker = c.dataset.liveLtpTicker;
    if (!ticker) return;
    const ltp = data ? data[ticker] : null;
    if (typeof ltp !== 'number' || !Number.isFinite(ltp)) return;  // null/missing -> fallback
    c.textContent = fmtPrice(ltp);
    const entry = parseFloat(c.dataset.liveLtpEntry);
    const side = c.dataset.liveLtpSide;
    patchPnlCell(ticker, entry, side, ltp);
  });
}

let _intervalId = null;

/**
 * Start polling /api/live_ltp every intervalMs milliseconds.
 * First tick fires immediately (no 5s wait for the first update).
 * Returns a stop() function; calling startLivePolling twice without
 * stopping first cleanly replaces the existing interval.
 */
export function startLivePolling(intervalMs = 5000) {
  if (_intervalId != null) {
    clearInterval(_intervalId);
    _intervalId = null;
  }
  // Fire-and-forget first tick.
  tick();
  _intervalId = setInterval(tick, intervalMs);
  const stop = () => {
    if (_intervalId != null) {
      clearInterval(_intervalId);
      _intervalId = null;
    }
  };
  return stop;
}
