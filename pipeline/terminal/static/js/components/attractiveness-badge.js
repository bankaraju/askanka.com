// Session-memoized attractiveness badge for open positions.
// The memo captures each ticker's score the first time its position renders
// in this browser session, so the arrow shows trajectory since position open.
//
// Used by components/positions-table.js. Kept separate from
// components/attractiveness-cell.js because the Positions badge has different
// semantics: it tracks *change over time* rather than an absolute band.

const _openAttractMemo = new Map();

function _esc(s) {
  if (s == null) return '';
  const d = (typeof document !== 'undefined') ? document.createElement('div') : null;
  if (d) {
    d.textContent = String(s);
    return d.innerHTML;
  }
  // Fallback for node test harnesses: minimal entity escape.
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Renders the trajectory badge for a single-leg position.
// - `ticker` — uppercased inside; used as memo key.
// - `row` — an attractiveness score row (e.g. { score, band, ... }) or null.
//   Must have a numeric `score` to produce output; otherwise returns ''.
//
// First call for a ticker records opening score; subsequent calls compare
// current vs opening with a ±2 dead-zone to suppress chatter.
export function renderBadge(ticker, row) {
  if (!ticker || !row || row.score == null) return '';
  const current = Number(row.score);
  if (!Number.isFinite(current)) return '';
  const t = String(ticker).toUpperCase();

  if (!_openAttractMemo.has(t)) _openAttractMemo.set(t, current);
  const opening = _openAttractMemo.get(t);

  let arrow, cls;
  if (current > opening + 2) { arrow = '↑'; cls = 'attract-rising'; }
  else if (current < opening - 2) { arrow = '↓'; cls = 'attract-falling'; }
  else { arrow = '→'; cls = 'attract-flat'; }

  const title = `Attractiveness now ${current}; at position open ${opening}`;
  return `<span class="attract-badge ${cls}" title="${_esc(title)}">Attract ${_esc(current)} ${arrow}</span>`;
}

// Drops a ticker's opening score from the session memo. Intended for a future
// position-close flow so a re-opened position starts a fresh trajectory rather
// than inheriting the stale opening from a prior trade on the same ticker.
export function resetPositionMemo(ticker) {
  if (ticker) _openAttractMemo.delete(String(ticker).toUpperCase());
}
