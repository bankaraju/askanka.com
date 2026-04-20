import { get } from '../lib/api.js';

const GRADE_COLORS = {
  'A+': 'badge--green', 'A': 'badge--green',
  'B+': 'badge--blue', 'B': 'badge--blue',
  'C': 'badge--amber',
  'D': 'badge--red', 'F': 'badge--red',
  '?': 'badge--muted',
};

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function _heatmapBg(score) {
  if (score == null) return '';
  if (score >= 80) return 'background: rgba(34,197,94,0.25)';
  if (score >= 60) return 'background: rgba(34,197,94,0.12)';
  if (score >= 40) return 'background: rgba(245,158,11,0.15)';
  if (score >= 20) return 'background: rgba(249,115,22,0.15)';
  return 'background: rgba(239,68,68,0.15)';
}

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [data, sectorsData] = await Promise.all([
      get('/trust-scores'),
      get('/trust-scores/sectors').catch(() => ({ sectors: {} })),
    ]);
    const stocks = data.stocks || [];
    const sectorsRaw = sectorsData.sectors || {};
    const sectors = Array.isArray(sectorsRaw)
      ? sectorsRaw
      : Object.entries(sectorsRaw).map(([id, v]) => ({
          id, display_name: v.name || id, count: v.count || 0,
        }));

    if (stocks.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No trust scores available</p></div>';
      return;
    }

    sectors.sort((a, b) => (b.count || 0) - (a.count || 0));
    const sectorOptions = sectors.map(sec =>
      `<option value="${_esc(sec.id)}">${_esc(sec.display_name)} (${sec.count})</option>`
    ).join('');

    container.innerHTML = `
      <div class="filter-bar" style="display:flex; align-items:center; gap: var(--spacing-sm); flex-wrap:wrap; margin-bottom: var(--spacing-sm);">
        <input type="text" id="trust-search" class="filter-search" placeholder="Search ticker..." style="min-width:140px;">
        <select id="trust-sector" class="filter-search" style="min-width:160px;">
          <option value="">All Sectors</option>
          ${sectorOptions}
        </select>
        <span id="trust-count" class="text-muted" style="font-size: 0.75rem;">${stocks.length} stocks scored</span>
      </div>
      <div id="trust-table-wrap"></div>`;

    let sortCol = 'composite_score';
    let sortDir = -1;

    const renderTable = () => {
      const tickerFilter = (document.getElementById('trust-search')?.value || '').toUpperCase();
      const sectorFilter = document.getElementById('trust-sector')?.value || '';
      let filtered = stocks.filter(s => {
        const matchTicker = !tickerFilter || (s.symbol || '').toUpperCase().includes(tickerFilter);
        const matchSector = !sectorFilter || (s.sector || '') === sectorFilter;
        return matchTicker && matchSector;
      });
      filtered = [...filtered].sort((a, b) => {
        let av = a[sortCol], bv = b[sortCol];
        if (av == null) av = sortDir === -1 ? -Infinity : Infinity;
        if (bv == null) bv = sortDir === -1 ? -Infinity : Infinity;
        if (typeof av === 'string') return sortDir * av.localeCompare(bv);
        return sortDir * (av - bv);
      });
      document.getElementById('trust-count').textContent = `${filtered.length} / ${stocks.length} stocks`;

      const colDefs = [
        { key: 'symbol', label: 'Ticker' },
        { key: 'display_name', label: 'Sector' },
        { key: 'sector_grade', label: 'Grade' },
        { key: 'composite_score', label: 'Composite' },
        { key: 'financial_score', label: 'Fin' },
        { key: 'management_score', label: 'Mgmt' },
        { key: 'sector_rank', label: 'Rank' },
        { key: 'grade_reason', label: 'Remark' },
      ];
      const thHtml = colDefs.map(col => {
        const active = col.key === sortCol ? 'style="color:var(--accent-gold);"' : '';
        return `<th class="sortable" data-col="${col.key}" ${active}>${col.label}</th>`;
      }).join('');

      const rows = filtered.map(s => {
        const grade = s.sector_grade || s.trust_grade || '?';
        const badgeCls = GRADE_COLORS[grade] || 'badge--muted';
        const composite = s.composite_score ?? s.trust_score;
        const fin = s.financial_score;
        const mgmt = s.management_score;
        const rank = (s.sector_rank != null && s.sector_total != null)
          ? `${s.sector_rank}/${s.sector_total}` : '--';
        const remarkFull = s.grade_reason || s.thesis || '';
        const remarkShort = remarkFull.length > 80 ? remarkFull.slice(0, 80) + '…' : remarkFull;
        const sectorDisplay = (s.display_name || s.sector || '').slice(0, 20);
        return `<tr><td style="font-family: var(--font-mono); font-weight:600;">${_esc(s.symbol)}</td>
          <td class="text-muted" style="font-size:0.75rem;" title="${_esc(s.display_name || s.sector || '')}">${_esc(sectorDisplay)}</td>
          <td><span class="badge ${badgeCls}">${_esc(grade)}</span></td>
          <td class="mono" style="${_heatmapBg(composite)}">${composite != null ? composite : '--'}</td>
          <td class="mono" style="${_heatmapBg(fin)}">${fin != null ? fin : '--'}</td>
          <td class="mono" style="${_heatmapBg(mgmt)}">${mgmt != null ? mgmt : '--'}</td>
          <td class="mono" style="font-size:0.75rem;">${_esc(rank)}</td>
          <td class="text-muted" style="font-size:0.75rem; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${_esc(remarkFull)}">${_esc(remarkShort)}</td>
        </tr>`;
      }).join('');

      document.getElementById('trust-table-wrap').innerHTML = `
        <table class="data-table">
          <thead><tr>${thHtml}</tr></thead>
          <tbody>${rows}</tbody>
        </table>`;

      document.querySelectorAll('#trust-table-wrap th.sortable').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
          const col = th.dataset.col;
          if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = -1; }
          renderTable();
        });
      });
    };

    renderTable();
    document.getElementById('trust-search').addEventListener('input', renderTable);
    document.getElementById('trust-sector').addEventListener('change', renderTable);
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load trust scores</p></div>';
  }
}

export function destroy() {}
