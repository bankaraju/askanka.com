export function render(container, signals, positions) {
  if ((!signals || signals.length === 0) && (!positions || positions.length === 0)) {
    container.innerHTML = `<div class="empty-state"><p>No active signals today</p></div>`;
    return;
  }

  function renderLegs(item) {
    const longs = (item.long_legs || []).map(l => l.ticker);
    const shorts = (item.short_legs || []).map(l => l.ticker);
    if (longs.length && !shorts.length) {
      return `<span class="text-green"><b>LONG</b> ${longs.join(', ')}</span>`;
    }
    if (shorts.length && !longs.length) {
      return `<span class="text-red"><b>SHORT</b> ${shorts.join(', ')}</span>`;
    }
    return `<span class="text-green">L: ${longs.join(', ')}</span><br><span class="text-red">S: ${shorts.join(', ')}</span>`;
  }

  const rows = (positions || []).map(pos => {
    const pnl = pos.spread_pnl_pct || 0;
    const pnlClass = pnl >= 0 ? 'text-green' : 'text-red';
    const pnlIcon = pnl >= 0 ? '&#9650;' : '&#9660;';
    const tierBadge = pos.tier === 'SIGNAL'
      ? '<span class="badge badge--gold">SIGNAL</span>'
      : '<span class="badge badge--amber">EXPLORING</span>';
    return `
      <tr class="clickable">
        <td>${pos.spread_name || pos.signal_id}</td>
        <td>${renderLegs(pos)}</td>
        <td>${tierBadge}</td>
        <td>${pos.open_date || '--'}</td>
        <td class="${pnlClass} mono">${pnlIcon} ${pnl.toFixed(2)}%</td>
      </tr>`;
  }).join('');

  const recRows = (signals || []).filter(s =>
    !(positions || []).some(p => p.signal_id === s.signal_id)
  ).map(sig => {
    const tierBadge = sig.tier === 'SIGNAL'
      ? '<span class="badge badge--gold">SIGNAL</span>'
      : '<span class="badge badge--amber">EXPLORING</span>';
    const hitRate = sig.hit_rate ? `${(sig.hit_rate * 100).toFixed(0)}%` : '--';
    return `
      <tr class="clickable">
        <td>${sig.spread_name || sig.signal_id}</td>
        <td>${renderLegs(sig)}</td>
        <td>${tierBadge}</td>
        <td>${sig.open_timestamp ? sig.open_timestamp.split('T')[0] : '--'}</td>
        <td class="mono">${hitRate}</td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <h3 style="margin-bottom: var(--spacing-md);">Active Positions & Signals</h3>
    <table class="data-table">
      <thead><tr><th>Spread / Signal</th><th>Legs</th><th>Tier</th><th>Opened</th><th>P&L / Hit Rate</th></tr></thead>
      <tbody>${rows}${recRows}</tbody>
    </table>`;
}
