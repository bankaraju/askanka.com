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

// Recompute and patch every per-row "Today" cell on the Dashboard from
// freshly-patched LTPs, using each leg's data-live-ltp-prev-close attribute.
// Mirrors signal_tracker._compute_todays_spread_move:
//   today_move = avg(long_today_moves) + avg(short_today_moves)
// where each leg's today_move = (ltp/prev_close - 1)*100 for long,
//                              = (1 - ltp/prev_close)*100 for short.
//
// After patching every row, sum the row totals and patch the page-level
// "Today: ±X.XX%" aggregate. This is the fix for the chronic "Today P&L
// frozen at +0.58% no matter where the LTP is" — was reported 4×.
function recomputeTodayCells() {
  const rows = document.querySelectorAll('[data-live-today-cell]');
  if (!rows || rows.length === 0) return;
  const perRowToday = [];
  rows.forEach(cell => {
    const sigId = cell.getAttribute('data-live-today-cell');
    if (!sigId) return;
    // Find every leg LTP span belonging to this row. The leg spans live in
    // the same <tr> as the today cell (priceCell column).
    const tr = cell.closest('tr');
    if (!tr) return;
    const legs = tr.querySelectorAll('[data-live-ltp-ticker]');
    const longMoves = [];
    const shortMoves = [];
    legs.forEach(leg => {
      const prev = parseFloat(leg.getAttribute('data-live-ltp-prev-close'));
      const side = leg.getAttribute('data-live-ltp-side');
      // The patched LTP lives in the cell's textContent as "₹N,NNN.NN".
      const ltpStr = (leg.textContent || '').replace(/[₹,\s]/g, '');
      const ltp = parseFloat(ltpStr);
      if (!Number.isFinite(prev) || prev <= 0 || !Number.isFinite(ltp)) return;
      const pct = side === 'short'
        ? (1 - ltp / prev) * 100
        : (ltp / prev - 1) * 100;
      (side === 'short' ? shortMoves : longMoves).push(pct);
    });
    if (longMoves.length + shortMoves.length === 0) {
      // No live LTPs yet — leave the snapshot value alone.
      return;
    }
    const avg = arr => arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0;
    const today = avg(longMoves) + avg(shortMoves);
    perRowToday.push(today);
    // Preserve the warn marker if the snapshot put one there (the snapshot's
    // <span title="snapshot missing — ..."> ⚠ glyph). Strip it before recompute
    // and we'll re-derive it by trusting the live recompute now agrees.
    cell.textContent = fmtPct(today);
    cell.className = `mono ${pnlClass(today)}`;
  });
  // Page-level aggregate: sum across recomputed rows. Only updates the span
  // if EVERY visible row produced a number (matches positions-table's null
  // guard logic so we don't paint "Today: NaN%" if a leg LTP fails to fetch).
  const aggSpan = document.querySelector('[data-live-today-aggregate]');
  if (!aggSpan) return;
  if (perRowToday.length === 0 || perRowToday.length !== rows.length) return;
  const total = perRowToday.reduce((s, v) => s + v, 0);
  aggSpan.textContent = `Today: ${fmtPct(total)}`;
  aggSpan.className = `mono ${pnlClass(total)}`;
  // Inline style to match the snapshot render (preserve baseline font-size).
  aggSpan.style.fontSize = '1rem';
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
  // After every leg LTP has been patched, recompute per-row Today cells +
  // the page-level aggregate. Order matters: this MUST run after the LTPs
  // are written so the textContent read inside the recompute sees fresh
  // values. Failed-fetch rows fall through (no Today change for them).
  recomputeTodayCells();
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
