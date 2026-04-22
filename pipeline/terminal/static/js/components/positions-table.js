// Renders the Open Positions table for Dashboard.
// Shows entry, current, P&L, stop, target, exit triggers, days held, source signal.

export function render(container, positions) {
  if (!positions || positions.length === 0) {
    container.innerHTML = `
      <div class="empty-state"><p>No open positions</p>
      <p class="text-muted">When a signal fires and executes, it will appear here.</p></div>`;
    return;
  }

  function legsHtml(item) {
    const longs = (item.long_legs || []).map(l => l.ticker || l).join(', ');
    const shorts = (item.short_legs || []).map(l => l.ticker || l).join(', ');
    if (longs && !shorts) return `<span class="text-green"><b>LONG</b> ${longs}</span>`;
    if (shorts && !longs) return `<span class="text-red"><b>SHORT</b> ${shorts}</span>`;
    return `<span class="text-green">L: ${longs}</span><br><span class="text-red">S: ${shorts}</span>`;
  }

  function fmtPrice(v) {
    if (v == null) return '--';
    return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Single-leg trades (Phase C breaks etc.) get entry → LTP inline.
  // Multi-leg baskets show '—' here; the per-leg entry/current is in the
  // signal payload but rendering it tabularly is deferred.
  function priceCell(item) {
    const longs = item.long_legs || [];
    const shorts = item.short_legs || [];
    if (longs.length + shorts.length !== 1) {
      return '<span class="text-muted" title="Multi-leg basket — per-leg prices in detail view">—</span>';
    }
    const leg = longs[0] || shorts[0];
    if (!leg || typeof leg !== 'object') return '--';
    const dir = leg.pnl_pct != null ? pnlClass(leg.pnl_pct) : '';
    return `<span class="mono">₹${fmtPrice(leg.entry)} → <span class="${dir}">₹${fmtPrice(leg.current)}</span></span>`;
  }

  function fmtPct(v) {
    if (v == null) return '--';
    return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
  }

  function pnlClass(v) {
    if (v == null) return '';
    return v >= 0 ? 'text-green' : 'text-red';
  }

  // Days held computed from open_date — positions.days_held isn't populated
  // by the exporter, so derive it here against today's IST date.
  function daysHeld(openDate) {
    if (!openDate) return null;
    const open = new Date(openDate.replace(' ', 'T'));
    if (Number.isNaN(open.getTime())) return null;
    const today = new Date();
    const diffMs = today - open;
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    return Math.max(0, days);
  }

  // Human-friendly definition of each signal source, surfaced as a tooltip
  // on the source badge + inline caption under the table. Future-you will
  // not remember what "CORRELATION_BREAK" means at 3am — keep it on screen.
  const SOURCE_DEFS = {
    'SPREAD': 'Multi-leg sector spread trade (long basket / short basket). Fired when regime + spread z-score + news/OI all align. Mean-reversion thesis.',
    'CORRELATION_BREAK': 'Phase C: a stock moved significantly differently than its regime peers expected (|z| ≥ 2σ from regime-conditional mean). OPPORTUNITY classification = fade the move (mean-reversion). Mechanical 5-day horizon; intraday exit at 14:30 for the live F3 shadow.',
    'PHASE_C': 'Phase C: regime-conditional stock divergence signal. See CORRELATION_BREAK.',
    'SIGNAL': 'Legacy spread signal.',
  };
  function sourceBadge(source, exitTrigger) {
    const def = SOURCE_DEFS[source] || '';
    const badge = `<span class="badge badge--gold" title="${def.replace(/"/g, '&quot;')}">${source}</span>`;
    return badge + (exitTrigger ? ` <span class="badge badge--amber">${exitTrigger}</span>` : '');
  }

  const rows = positions.map(p => {
    const pnl = p.spread_pnl_pct ?? p.pnl_pct ?? 0;
    // Per-spread stop levels — computed by signal_tracker.check_signal_status,
    // exported flat by website_exporter.export_live_status. Some fields may be
    // nested under _data_levels for legacy callers; fall back to that shape.
    // Reference:
    //   docs/superpowers/plans/2026-04-15-trailing-stop-and-replay.md
    //   pipeline/signal_tracker.py:10-20  (live trail config + backtest cite)
    const lvl = p._data_levels || {};
    const dailyStop = p.daily_stop ?? lvl.daily_stop;
    const trailStop = p.trail_stop ?? lvl.trail_stop;
    const peakPnl = p.peak_pnl ?? lvl.peak;

    const stop = dailyStop != null ? fmtPct(dailyStop) : '--';
    // Muted dot when the stop came from the fallback path (ATR requested
    // for a Phase C break but unavailable → using spread-stats default,
    // which isn't volatility-calibrated for this ticker). Tooltip explains
    // the degradation so the viewer doesn't have to guess.
    const stopSource = p.stop_source ?? lvl.stop_source;
    const fallbackDot = stopSource === 'fallback'
      ? ' <span title="using fallback stop — ATR unavailable" style="color: var(--colour-muted, #888); font-size: 0.7em;">◦</span>'
      : '';
    const trail = trailStop != null ? fmtPct(trailStop) : '--';
    const peak = peakPnl != null ? fmtPct(peakPnl) : '--';
    const opened = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : '--');
    const computedDays = p.days_held != null ? p.days_held : daysHeld(p.open_date || p.open_timestamp);
    const days = computedDays != null ? `${computedDays}d` : '--';
    const source = p.source || p.source_signal || p.tier || '--';
    const exitTrigger = p.exit_trigger || (p.is_stale ? 'STALE' : '');
    const whyTooltip = (p.event_headline || '').replace(/"/g, '&quot;');

    return `<tr${whyTooltip ? ` title="${whyTooltip}"` : ''}>
      <td>${p.spread_name || p.signal_id || '--'}</td>
      <td>${legsHtml(p)}</td>
      <td>${priceCell(p)}</td>
      <td class="mono">${opened}</td>
      <td class="mono ${pnlClass(pnl)}">${fmtPct(pnl)}</td>
      <td class="mono text-red" title="Daily stop = -(avg_favorable × 0.50). Per-spread, from 1mo history.">${stop}${fallbackDot}</td>
      <td class="mono ${pnlClass(trailStop)}" title="Trail stop = peak - (avg_favorable × sqrt(days_since_check)). Arms when peak ≥ budget.">${trail}</td>
      <td class="mono text-green" title="Running peak P&L since entry — trail stop ratchets off this.">${peak}</td>
      <td class="mono">${days}</td>
      <td>${sourceBadge(source, exitTrigger)}</td>
    </tr>`;
  }).join('');

  const totalPnl = positions.reduce((sum, p) => sum + (p.spread_pnl_pct ?? p.pnl_pct ?? 0), 0);
  const headerCls = totalPnl >= 0 ? 'text-green' : 'text-red';

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--spacing-md);">
      <h3 style="margin: 0;">Open Positions <span class="text-muted" style="font-size: 0.875rem;">(${positions.length})</span></h3>
      <div class="mono ${headerCls}" style="font-size: 1rem;">Total P&L: ${fmtPct(totalPnl)}</div>
    </div>
    <table class="data-table">
      <thead><tr>
        <th>Name</th><th>Legs</th>
        <th title="Entry price → Last traded price (single-leg trades only; basket spreads in detail view)">Entry → LTP</th>
        <th>Opened</th><th>P&L</th>
        <th title="Daily stop level — per-spread, from 1mo favorable-move history">Stop</th>
        <th title="Trailing stop level — locks in profit as peak ratchets up">Trail</th>
        <th title="Running peak P&L since entry">Peak</th>
        <th>Held</th><th>Source / Exit</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="legend-strip" style="margin-top: var(--spacing-md); padding: var(--spacing-sm) var(--spacing-md); background: var(--bg-alt, #1a1a1a); border-left: 3px solid var(--gold, #c9a864); font-size: 0.82rem; line-height: 1.55;">
      <div style="font-weight: 600; color: var(--gold, #c9a864); margin-bottom: 4px;">Reading this table</div>
      <div>
        <b>SPREAD</b> = regime-gated long/short basket trade (e.g. long Defence basket, short IT basket).
        <b>CORRELATION_BREAK</b> = Phase C signal: a stock diverged ≥ 2σ from what its regime peers did, and we fade the move (mean-reversion thesis). Exit mechanically at 14:30 IST or on stop.
        <b>Stop</b> = one-day worst-case; <b>Trail</b> = peak − give-back budget; <b>Peak</b> = highest P&L seen since entry.
        Hover any row for the break details (z-score, expected vs actual move).
      </div>
    </div>`;
}
