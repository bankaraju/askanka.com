// Read-only browser of all tradeable_candidates from /api/candidates.
// Filter by source / conviction / horizon_basis (URL-encoded).
import { get } from '../lib/api.js';
import * as filterChips from '../components/filter-chips.js';
import * as candidatesTable from '../components/candidates-table.js';
import * as attractiveness from '../components/attractiveness-cell.js';

let _allCandidates = [];

export async function render(container) {
  container.innerHTML = `
    <div style="margin-bottom: var(--spacing-md);">
      <h2 style="margin-bottom: var(--spacing-xs); font-size: 1.125rem;">Trading — All Tradeable Candidates</h2>
      <div class="text-muted" style="font-size: 0.75rem;">Read-only. Filter and study; no actions taken from this surface.</div>
    </div>
    <div id="trading-filters" style="margin-bottom: var(--spacing-md); display: flex; flex-wrap: wrap; gap: var(--spacing-sm);"></div>
    <div id="trading-count" class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);"></div>
    <div id="trading-table"></div>`;

  await loadData();
}

export function destroy() {}

function _attachAttractiveness(candidates, scores) {
  const map = (scores && scores.scores) || {};
  for (const c of candidates) {
    const raw = c.long_legs?.[0] || c.short_legs?.[0] || c.ticker;
    if (!raw) { c.attractiveness = undefined; continue; }
    const key = String(raw).toUpperCase();
    c.attractiveness = map[key];
  }
}

function _attachAnalyses(candidates, fcs, ta, digest, corr) {
  const fcsMap = (fcs && fcs.scores) || {};
  const taMap  = (ta && ta.scores)  || {};
  const spreadsByName = Object.fromEntries(
    (digest.spread_theses || []).map(s => [s.name, s]));
  const corrByTicker  = Object.fromEntries(
    (corr.breaks || []).map(b => [String(b.ticker || '').toUpperCase(), b]));
  for (const c of candidates) {
    const raw = c.long_legs?.[0] || c.short_legs?.[0] || c.ticker;
    const key = raw ? String(raw).toUpperCase() : null;
    c.analyses_raw = {
      fcs:    key      ? (fcsMap[key]         || null) : null,
      ta:     key      ? (taMap[key]           || null) : null,
      spread: c.name   ? (spreadsByName[c.name] || null) : null,
      corr:   key      ? (corrByTicker[key]    || null) : null,
    };
  }
}

async function loadData() {
  try {
    // Fetch candidates + all four analysis engines in parallel. Each engine is a soft
    // dependency: if it fails, we still render candidates (each will show em-dash).
    const [dataRes, fcsRes, taRes, spreadRes, corrRes] = await Promise.allSettled([
      get('/candidates'),
      get('/attractiveness'),
      get('/ta_attractiveness'),
      get('/research/digest'),
      get('/correlation_breaks'),
    ]);
    _allCandidates = (dataRes.status === 'fulfilled'
      ? (dataRes.value.tradeable_candidates || []) : []);

    const fcsScores  = (fcsRes.status === 'fulfilled')    ? fcsRes.value    : { scores: {} };
    const taScores   = (taRes.status === 'fulfilled')     ? taRes.value     : { scores: {} };
    const digest     = (spreadRes.status === 'fulfilled') ? spreadRes.value : { spread_theses: [] };
    const corrBreaks = (corrRes.status === 'fulfilled')   ? corrRes.value   : { breaks: [] };

    _attachAnalyses(_allCandidates, fcsScores, taScores, digest, corrBreaks);

    // Keep existing attractiveness cell attachment for the table column.
    _attachAttractiveness(_allCandidates, fcsScores);

    const sources = [...new Set(_allCandidates.map(c => c.source).filter(Boolean))];
    const convictions = [...new Set(_allCandidates.map(c => c.conviction).filter(Boolean))];
    const horizons = [...new Set(_allCandidates.map(c => c.horizon_basis).filter(Boolean))];

    const filterEl = document.getElementById('trading-filters');
    filterChips.render(filterEl, {
      groups: [
        { key: 'source', label: 'Source', options: sources },
        { key: 'conviction', label: 'Conviction', options: convictions },
        { key: 'horizon_basis', label: 'Horizon', options: horizons },
      ],
    }, applyFilters, 'trading');

    applyFilters(filterChips.getState('trading'));
  } catch (err) {
    document.getElementById('trading-table').innerHTML =
      `<div class="empty-state"><p>Failed to load candidates: ${err.message}</p></div>`;
  }
}

function applyFilters(state) {
  const filtered = _allCandidates.filter(c => {
    if (state.source?.length && !state.source.includes(c.source)) return false;
    if (state.conviction?.length && !state.conviction.includes(c.conviction)) return false;
    if (state.horizon_basis?.length && !state.horizon_basis.includes(c.horizon_basis)) return false;
    return true;
  });

  const countEl = document.getElementById('trading-count');
  if (countEl) countEl.textContent = `${filtered.length} of ${_allCandidates.length} candidates`;

  const tableEl = document.getElementById('trading-table');
  if (tableEl) candidatesTable.render(tableEl, filtered);
}
