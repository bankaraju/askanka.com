// Sortable table of tradeable_candidates with click-to-expand row drawer.
import * as drawer from './candidate-drawer.js';

let _sortCol = 'score';
let _sortDir = -1;

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

export function render(container, candidates) {
  if (!candidates || candidates.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>No candidates match these filters</p></div>';
    return;
  }

  const sorted = [...candidates].sort((a, b) => {
    let av = a[_sortCol], bv = b[_sortCol];
    if (av == null) av = _sortDir === -1 ? -Infinity : Infinity;
    if (bv == null) bv = _sortDir === -1 ? -Infinity : Infinity;
    if (typeof av === 'string') return _sortDir * av.localeCompare(bv);
    return _sortDir * (av - bv);
  });

  function legsCell(c) {
    const longs = (c.long_legs || []).join(', ');
    const shorts = (c.short_legs || []).join(', ');
    if (longs && !shorts) return `<span class="text-green">LONG ${_esc(longs)}</span>`;
    if (shorts && !longs) return `<span class="text-red">SHORT ${_esc(shorts)}</span>`;
    return `<span class="text-green">L: ${_esc(longs)}</span><br><span class="text-red">S: ${_esc(shorts)}</span>`;
  }

  function convClass(c) {
    if (c === 'HIGH') return 'badge--gold';
    if (c === 'MEDIUM') return 'badge--amber';
    return 'badge--muted';
  }

  const cols = [
    { key: 'name', label: 'Name' },
    { key: 'source', label: 'Source' },
    { key: 'long_legs', label: 'Legs' },
    { key: 'conviction', label: 'Conviction' },
    { key: 'score', label: 'Score' },
    { key: 'horizon_days', label: 'Horizon' },
  ];

  const thHtml = cols.map(col => {
    const arrow = col.key === _sortCol ? (_sortDir === -1 ? ' ▼' : ' ▲') : '';
    return `<th class="sortable" data-col="${_esc(col.key)}" style="cursor: pointer;">${_esc(col.label)}${arrow}</th>`;
  }).join('');

  const rows = sorted.map((c, i) => `
    <tr class="clickable" data-idx="${i}">
      <td>${_esc(c.name)}</td>
      <td><span class="badge badge--muted">${_esc(c.source)}</span></td>
      <td>${legsCell(c)}</td>
      <td><span class="badge ${convClass(c.conviction)}">${_esc(c.conviction)}</span></td>
      <td class="mono">${_esc(c.score)}</td>
      <td class="mono">${_esc(c.horizon_days)}d</td>
    </tr>
    <tr class="drawer-row" data-drawer-for="${i}" style="display: none;">
      <td colspan="6"><div id="drawer-content-${i}"></div></td>
    </tr>`).join('');

  container.innerHTML = `
    <table class="data-table">
      <thead><tr>${thHtml}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  container.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (_sortCol === col) { _sortDir *= -1; }
      else { _sortCol = col; _sortDir = -1; }
      render(container, candidates);
    });
  });

  container.querySelectorAll('tr.clickable').forEach(row => {
    row.addEventListener('click', () => {
      const idx = row.dataset.idx;
      const drawerRow = container.querySelector(`tr[data-drawer-for="${idx}"]`);
      if (!drawerRow) return;
      const isOpen = drawerRow.style.display === 'table-row';
      container.querySelectorAll('tr.drawer-row').forEach(d => { d.style.display = 'none'; });
      if (!isOpen) {
        drawerRow.style.display = 'table-row';
        const mount = document.getElementById(`drawer-content-${idx}`);
        if (mount) drawer.render(mount, sorted[idx]);
      }
    });
  });
}
