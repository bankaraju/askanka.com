// Read-only browser of all tradeable_candidates from /api/candidates.
// Filter by source / conviction / horizon_basis (URL-encoded).
import { get } from '../lib/api.js';
import * as filterChips from '../components/filter-chips.js';
import * as candidatesTable from '../components/candidates-table.js';

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

async function loadData() {
  try {
    const data = await get('/candidates');
    _allCandidates = data.tradeable_candidates || [];

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
    }, applyFilters);

    applyFilters(filterChips.getState());
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
