// Shared helper for rendering Feature Coincidence Scorer output.
//
// Exposes:
//   fetchAll()              -> cached 10s GET /api/attractiveness
//   bandClass(band)         -> CSS class for GREEN/AMBER/RED/other
//   tooltipText(row)        -> plain-text tooltip for a score row
//   renderCellHtml(row)     -> sync HTML string given an already-fetched row
//   renderAttractivenessCell(ticker) -> async convenience wrapper used when
//                              the caller cannot pre-fetch.
//
// Meant to be reused across Trading tab, Positions badge, TA panel.
import { get } from '../lib/api.js';

let _cache = null;
let _cacheTs = 0;
const CACHE_TTL_MS = 10_000;

export async function fetchAll() {
  const now = Date.now();
  if (_cache && (now - _cacheTs) < CACHE_TTL_MS) return _cache;
  try {
    _cache = await get('/attractiveness');
    _cacheTs = now;
  } catch (e) {
    _cache = { scores: {} };
    _cacheTs = now;
  }
  return _cache;
}

export function bandClass(band) {
  if (band === 'GREEN') return 'attract-green';
  if (band === 'AMBER') return 'attract-amber';
  if (band === 'RED') return 'attract-red';
  return 'attract-none';
}

export function tooltipText(row) {
  if (!row) return 'no model';
  const header = `Model health: ${row.band || '-'} (${row.source || 'own'})`;
  const lines = (row.top_features || []).slice(0, 3).map(f => {
    const c = Number(f.contribution);
    const sign = c > 0 ? '+' : '';
    const val = Number.isFinite(c) ? c.toFixed(2) : String(f.contribution);
    return `${sign}${val}  ${f.name}`;
  });
  return lines.length ? `${header}\n${lines.join('\n')}` : header;
}

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

export function renderCellHtml(row) {
  if (!row) {
    return '<span class="attract-none" title="no model">—</span>';
  }
  const cls = bandClass(row.band);
  const tip = tooltipText(row);
  return `<span class="attract ${cls}" title="${_esc(tip)}">${_esc(row.score)}</span>`;
}

export async function renderAttractivenessCell(ticker) {
  if (!ticker) return '<span class="attract-none" title="no model">—</span>';
  const all = await fetchAll();
  const row = all?.scores?.[String(ticker).toUpperCase()];
  return renderCellHtml(row);
}
