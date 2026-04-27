// Renders the Open Positions table for Dashboard.
// Shows entry, current, P&L, stop, target, exit triggers, days held, source signal.

import { renderBadge as renderAttractBadge } from './attractiveness-badge.js';

export function render(container, positions) {
  if (!positions || positions.length === 0) {
    container.innerHTML = `
      <div class="empty-state"><p>No open positions</p>
      <p class="text-muted">When a signal fires and executes, it will appear here.</p></div>`;
    return;
  }

  // Track A #8: wrap each ticker with <a.ticker-link data-ticker=X> so the
  // app-level delegated click handler can open a chart drawer regardless
  // of where the ticker is rendered (legs cell, Entry→LTP, break-detail).
  function tickerLink(t) {
    if (!t) return '';
    const up = String(t).toUpperCase();
    return `<a class="ticker-link" data-ticker="${up}" href="#" role="button">${up}</a>`;
  }

  function legsHtml(item) {
    const longList  = (item.long_legs  || []).map(l => tickerLink(l.ticker || l));
    const shortList = (item.short_legs || []).map(l => tickerLink(l.ticker || l));
    const longs = longList.join(', ');
    const shorts = shortList.join(', ');
    if (longs && !shorts) return `<span class="text-green"><b>LONG</b> ${longs}</span>`;
    if (shorts && !longs) return `<span class="text-red"><b>SHORT</b> ${shorts}</span>`;
    return `<span class="text-green">L: ${longs}</span><br><span class="text-red">S: ${shorts}</span>`;
  }

  function fmtPrice(v) {
    if (v == null) return '--';
    return Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // Render one leg as "TICKER ₹entry → ₹current (+x.xx%)".
  // Short legs get an S prefix + red tint so the side is unambiguous.
  // Live-ticker attributes are emitted for every ticker (single-leg AND
  // per-leg of a basket), so live-ticker.js can patch each LTP span in
  // place between backend snapshots.
  function legPriceLine(leg, side) {
    if (!leg || typeof leg !== 'object') {
      // String-only leg (legacy shape) — show ticker, no prices
      const t = typeof leg === 'string' ? leg : '';
      const tag = side === 'short' ? 'S' : 'L';
      const cls = side === 'short' ? 'text-red' : 'text-green';
      return t ? `<span class="${cls}"><b>${tag}</b> ${tickerLink(t)}</span>` : '';
    }
    const ticker = leg.ticker || '';
    const dir = leg.pnl_pct != null ? pnlClass(leg.pnl_pct) : '';
    const entryAttr = leg.entry != null ? leg.entry : '';
    const liveAttrs = ticker
      ? ` data-live-ltp-ticker="${ticker}" data-live-ltp-entry="${entryAttr}" data-live-ltp-side="${side}"`
      : '';
    const tag = side === 'short' ? 'S' : 'L';
    const tagCls = side === 'short' ? 'text-red' : 'text-green';
    const pnlTxt = leg.pnl_pct != null ? ` <span class="${dir}">${fmtPct(leg.pnl_pct)}</span>` : '';
    return `<span class="mono"><span class="${tagCls}"><b>${tag}</b> ${tickerLink(ticker)}</span> ₹${fmtPrice(leg.entry)} → <span class="${dir}"${liveAttrs}>₹${fmtPrice(leg.current)}</span>${pnlTxt}</span>`;
  }

  // Single-leg trades (Phase C breaks etc.) get entry → LTP inline on one
  // row. Multi-leg baskets (e.g. Sovereign Shield Alpha) render every leg
  // stacked with <br> so the entry + LTP + per-leg P&L is visible without
  // a detail-view round-trip.
  function priceCell(item) {
    const longs = item.long_legs || [];
    const shorts = item.short_legs || [];
    const total = longs.length + shorts.length;
    if (total === 0) return '--';
    if (total === 1) {
      const leg = longs[0] || shorts[0];
      const side = longs.length === 1 ? 'long' : 'short';
      if (!leg || typeof leg !== 'object') return '--';
      // Single-leg: keep the original compact form (no TICKER prefix — legs column has it)
      const dir = leg.pnl_pct != null ? pnlClass(leg.pnl_pct) : '';
      const ticker = leg.ticker || '';
      const entryAttr = leg.entry != null ? leg.entry : '';
      const liveAttrs = ticker
        ? ` data-live-ltp-ticker="${ticker}" data-live-ltp-entry="${entryAttr}" data-live-ltp-side="${side}"`
        : '';
      return `<span class="mono">₹${fmtPrice(leg.entry)} → <span class="${dir}"${liveAttrs}>₹${fmtPrice(leg.current)}</span></span>`;
    }
    // Multi-leg: one line per leg
    const lines = [];
    for (const l of longs) lines.push(legPriceLine(l, 'long'));
    for (const s of shorts) lines.push(legPriceLine(s, 'short'));
    return lines.filter(Boolean).join('<br>');
  }

  // Ticker for the P&L cell pairing (single-leg only). Multi-leg: no ticker.
  function rowTicker(item) {
    const longs = item.long_legs || [];
    const shorts = item.short_legs || [];
    if (longs.length + shorts.length !== 1) return '';
    const leg = longs[0] || shorts[0];
    return leg && typeof leg === 'object' ? (leg.ticker || '') : '';
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
    'CORRELATION_BREAK': 'Phase C (EXPLORATORY — research-tier, 0.5 unit): stock moved significantly differently than regime peers expected (|z| ≥ 2σ from regime-conditional mean). OPPORTUNITY classification = trade in peer-implied direction (follow-peer-cohort conviction). Mechanical 5-day horizon; intraday exit at 14:30 for the F3 forward shadow. Compliance FAIL on H-2026-04-23-001 (2026-04-23) — kept for forward scorecarding, not signal-grade.',
    'PHASE_C': 'Phase C: regime-conditional stock divergence signal. See CORRELATION_BREAK.',
    'SIGNAL': 'Legacy spread signal.',
  };
  // Render a sub-row attached under a CORRELATION_BREAK position row.
  // Column count is 10 (see headerRow below); colspan must match so the
  // panel doesn't misalign with the data cells above. Lay-language is the
  // mandate — a layman should understand the thesis without jargon.
  function breakDetailSubrow(bd) {
    if (!bd) return '';
    const sym = bd.symbol || '';
    const z = bd.z_score;
    const absZ = (z != null && Number.isFinite(z)) ? Math.abs(z) : null;
    const zTxt = absZ != null ? `${absZ.toFixed(2)}σ` : '—';
    const classif = bd.classification || '';
    const regime = bd.regime || '';
    const expected = bd.expected_1d;
    const actual = bd.actual_return;
    const oi = bd.oi_anomaly ? ' + OI anomaly' : '';

    const rarity = (absZ == null) ? 'uncertain rarity'
      : (absZ >= 3 ? 'very rare (≥3σ, ~1-in-370 days)'
      : (absZ >= 2 ? 'rare (≥2σ, ~1-in-22 days)'
      : 'mild (<2σ — noise floor)'));

    // Lag vs overshoot detection: engine classify_break() conflates both cases
    // into OPPORTUNITY. The UI names which sub-case applies so the viewer
    // understands the actual trade, not a romanticised mean-reversion story.
    // Thresholds mirror classify_break's 0.3× lag test; overshoot = 1.5×+.
    const absExp = (expected != null) ? Math.abs(expected) : null;
    const absAct = (actual != null) ? Math.abs(actual) : null;
    const sameDir = (expected != null && actual != null)
      ? ((expected >= 0 && actual >= 0) || (expected < 0 && actual < 0))
      : null;
    const isOvershoot = (sameDir === true && absExp != null && absAct != null
                         && absExp > 0 && absAct > absExp * 1.5);
    const isLag = (absExp != null && absAct != null
                   && absExp > 0 && absAct < absExp * 0.3);

    // Thesis text reflects what reverse_regime_breaks.py:403 actually does:
    //   direction = "LONG" if expected_return > 0 else "SHORT"
    // That's FOLLOW-the-peer-direction (regime-trend), not fade. Until the
    // engine is re-specced (task #107), the UI must describe follow, and flag
    // which sub-case (lag or overshoot) we're seeing.
    // OPPORTUNITY_LAG / OPPORTUNITY_OVERSHOOT were introduced in Task 7 (#107).
    // Legacy bare OPPORTUNITY is treated identically to OPPORTUNITY_LAG for
    // historical records read-back.
    let thesisPhrase = '';
    if (classif === 'OPPORTUNITY_LAG') {
      thesisPhrase = [
        'Peers moved; stock lagged. FOLLOW thesis (aligned with backtest FADE).',
        'Target: 5-day drift mean of regime-conditional returns. Stop: 1.5σ against entry.',
      ].join(' ');
    } else if (classif === 'OPPORTUNITY_OVERSHOOT') {
      thesisPhrase = 'Peers moved; stock overshot. Live engine thesis opposite to backtest FADE — research-only, no paper trade opened.';
    } else if (classif === 'OPPORTUNITY') {
      // Legacy bare OPPORTUNITY: use heuristic sub-case detection on the raw numbers
      // (engine did not yet emit the split classification). Preserve overshoot/lag wording
      // so historical records are still readable.
      const subcase = isOvershoot
        ? 'Stock has already moved further than peers expected (overshoot).'
        : (isLag
            ? "Stock hasn't moved as much as peers expected (lag — catch-up play)."
            : '');
      thesisPhrase = [
        'Thesis: trade in the peer-implied direction, following peer-cohort conviction.',
        subcase,
        'Target: 5-day drift mean of regime-conditional returns. Stop: 1.5σ against entry.',
      ].filter(Boolean).join(' ');
    } else if (classif === 'REGIME_LAG') {
      thesisPhrase = "Thesis: stock lags peers. Enter in peer direction expecting catch-up.";
    } else if (classif === 'DEGENERATE') {
      thesisPhrase = 'Both expected and residual magnitudes < 0.1% — classification ambiguous.';
    }

    const expActualLine = (expected != null && actual != null)
      ? `Peers expected <b>${fmtPct(expected)}</b> in ${regime}, actual was <b>${fmtPct(actual)}</b>.`
      : (expected != null
          ? `Peers expected <b>${fmtPct(expected)}</b> in ${regime}.`
          : '');

    const badgeCls = classif === 'OPPORTUNITY_OVERSHOOT' ? 'badge--muted'
      : (classif.startsWith('OPPORTUNITY') || classif === 'REGIME_LAG') ? 'badge--gold'
      : 'badge--muted';
    const badgeTitle = classif === 'OPPORTUNITY_OVERSHOOT'
      ? 'Research alert — live engine is opposite to backtest FADE. No shadow row opened. H-2026-04-23-003 will test if FADE is tradeable.'
      : classif.startsWith('OPPORTUNITY')
      ? 'LAG-geometry: live engine FOLLOW agrees with backtest FADE. Shadow row opened at 0.5 unit per H-2026-04-23-002.'
      : 'regime-conditional divergence classification — exploratory (research-tier)';
    const badgeLabel = classif === 'OPPORTUNITY_OVERSHOOT'
      ? 'OPPORTUNITY OVERSHOOT · RESEARCH-ONLY'
      : (classif === 'OPPORTUNITY_LAG' || classif === 'OPPORTUNITY')
      ? 'OPPORTUNITY LAG · EXPLORATORY'
      : `${classif.replace(/_/g, ' ')} · EXPLORATORY`;

    return `<tr class="break-detail-row" data-break-detail="${sym}">
      <td colspan="10" style="background: rgba(201, 168, 100, 0.04); border-top: 1px dashed var(--colour-muted, #555); padding: var(--spacing-xs) var(--spacing-md); font-size: 0.8rem; line-height: 1.5;">
        <span class="badge ${badgeCls}" title="${badgeTitle}">${badgeLabel}</span>
        <span class="text-muted" style="margin-left: 0.5rem;">z-score ${zTxt} (${rarity})${oi}</span>
        <span style="margin-left: 0.75rem;">${expActualLine}</span>
        ${thesisPhrase ? `<div class="text-muted" style="margin-top: 2px;">${thesisPhrase}</div>` : ''}
      </td>
    </tr>`;
  }

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

    // Track A #10 (2026-04-23): once peak_pnl > |daily_stop|, the trail is
    // armed and signal_tracker.py treats daily_stop as INERT (see line 702 —
    // daily_stop check only fires when `not trail_armed`). Show that in the
    // UI: a live 0.99% reading next to an 8% peak is misleading. Armed rows
    // render the Stop cell as an inert marker + tooltip; the true active
    // guardrail is the Trail cell.
    const trailArmed = (peakPnl != null && dailyStop != null
                         && peakPnl > Math.abs(dailyStop));
    const stop = dailyStop != null
      ? (trailArmed ? 'INERT' : fmtPct(dailyStop))
      : '--';
    // Muted dot when the stop came from the fallback path (ATR requested
    // for a Phase C break but unavailable → using spread-stats default,
    // which isn't volatility-calibrated for this ticker). Tooltip explains
    // the degradation so the viewer doesn't have to guess.
    const stopSource = p.stop_source ?? lvl.stop_source;
    const fallbackDot = stopSource === 'fallback'
      ? ' <span title="using fallback stop — ATR unavailable" style="color: var(--colour-muted, #888); font-size: 0.7em;">◦</span>'
      : '';
    // Mirror of the Stop INERT logic on line 261. The trail stop is
    // a computed peer (peak − give-back budget) the backend updates every
    // tick — but it only becomes the *active* guardrail once peak has
    // crossed |daily_stop|. Showing the pre-arm number reads like a live
    // stop level to the trader; it isn't. Render INERT until armed so the
    // Stop and Trail cells are never both showing live numbers at once.
    const trail = trailStop != null
      ? (trailArmed ? fmtPct(trailStop) : 'INERT')
      : '--';
    const peak = peakPnl != null ? fmtPct(peakPnl) : '--';
    const opened = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : '--');
    const computedDays = p.days_held != null ? p.days_held : daysHeld(p.open_date || p.open_timestamp);
    const days = computedDays != null ? `${computedDays}d` : '--';
    const source = p.source || p.source_signal || p.tier || '--';
    const exitTrigger = p.exit_trigger || (p.is_stale ? 'STALE' : '');
    const whyTooltip = (p.event_headline || '').replace(/"/g, '&quot;');
    // data-live-pnl-ticker pairs this P&L cell with the priceCell LTP span
    // so live-ticker.js can recompute +X.XX%/-X.XX% between snapshots
    // without rewriting live_status.json. Single-leg only.
    const pnlTicker = rowTicker(p);
    const pnlLiveAttr = pnlTicker ? ` data-live-pnl-ticker="${pnlTicker}"` : '';
    // Attractiveness trajectory badge — single-leg rows only (rowTicker
    // returns '' for multi-leg baskets, which short-circuits renderBadge).
    // p.attractiveness is attached upstream by pages/dashboard.js after the
    // /api/attractiveness fetch; absent → renderBadge returns '' and no
    // badge markup is emitted.
    const attractBadge = renderAttractBadge(pnlTicker, p.attractiveness);

    // Today's P&L: distinct from cumulative since entry. Reads p.todays_move
    // (computed by signal_tracker._compute_todays_spread_move from the EOD
    // prev-close snapshot). When snapshot is missing, backend silently
    // returns today==cumulative — flag positions where that's clearly wrong
    // (opened on a prior date yet today equals cum). Day-1 positions where
    // today==cum is CORRECT (reference price is entry).
    const todayMove = p.todays_move;
    const todayTxt = todayMove != null ? fmtPct(todayMove) : '--';
    const openedOn = p.open_date || (p.open_timestamp ? p.open_timestamp.split('T')[0] : null);
    const todayIso = new Date().toISOString().slice(0, 10);
    const openedBeforeToday = openedOn && openedOn !== todayIso;
    const snapshotStale = openedBeforeToday
      && todayMove != null && pnl != null
      && Math.abs(todayMove - pnl) < 0.005;
    const todayWarn = snapshotStale
      ? ' <span title="snapshot missing — today == cumulative since entry. Pipeline issue: _prev_close_long not persisting." style="color: var(--colour-amber, #d4a84b);">⚠</span>'
      : '';
    const todayTip = snapshotStale
      ? "Today's move (stale: backend prev-close snapshot missing)."
      : (openedOn === todayIso
          ? "Today's move (Day 1 = move since entry)."
          : "Today's move vs yesterday's close.");

    // Track A #6: lay-language sub-row for CORRELATION_BREAK positions.
    // Explains the break in plain English: what peers did vs this stock,
    // how rare the divergence was, and the fade/follow thesis. Rendered
    // as a 2nd <tr> with colspan spanning the whole table so it appears
    // visually attached to the row above.
    const breakDetailRow = (p.break_detail && source === 'CORRELATION_BREAK')
      ? breakDetailSubrow(p.break_detail)
      : '';

    // Track A #9: spread_description (real name + playbook thesis) is the
    // tooltip target for the Name cell. Without it, "Strategy 641" /
    // "Sovereign Shield Alpha" tell the viewer nothing about what's inside.
    const descRaw = p.spread_description;
    const nameTitle = (typeof descRaw === 'string' && descRaw)
      ? ` title="${descRaw.replace(/"/g, '&quot;')}"`
      : '';

    return `<tr${whyTooltip ? ` title="${whyTooltip}"` : ''}>
      <td${nameTitle}>${p.spread_name || p.signal_id || '--'}</td>
      <td>${legsHtml(p)}</td>
      <td>${priceCell(p)}</td>
      <td class="mono">${opened}</td>
      <td class="mono ${pnlClass(pnl)}"${pnlLiveAttr}>${fmtPct(pnl)}${attractBadge ? ' ' + attractBadge : ''}</td>
      <td class="mono ${pnlClass(todayMove)}" title="${todayTip}">${todayTxt}${todayWarn}</td>
      <td class="mono ${trailArmed ? 'text-muted' : 'text-red'}" title="${trailArmed ? 'trail armed — daily stop inert. Active guardrail is the Trail column.' : 'Daily stop = -(avg_favorable × 0.50). Per-spread, from 1mo history.'}">${stop}${fallbackDot}</td>
      <td class="mono ${trailArmed ? pnlClass(trailStop) : 'text-muted'}" title="${trailArmed ? 'Active stop — ratcheted to peak minus give-back budget.' : 'Trail not armed yet — peak has not crossed |daily_stop|. Active guardrail is the Stop column.'}">${trail}</td>
      <td class="mono text-green" title="Running peak P&L since entry — trail stop ratchets off this.">${peak}</td>
      <td class="mono">${days}</td>
      <td>${sourceBadge(source, exitTrigger)}</td>
    </tr>${breakDetailRow}`;
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
        <th>Opened</th>
        <th title="Cumulative P&L since entry (unrealized). Multi-leg: weighted long+short legs.">P&L</th>
        <th title="Today's spread move (vs yesterday's close). Day-1 positions show move since entry. ⚠ = snapshot missing.">Today</th>
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
        <b>CORRELATION_BREAK</b> = Phase C signal: a stock diverged ≥ 2σ from what its regime peers did, and we trade in the peer-implied direction (follow-peer-cohort conviction). Exit mechanically at 14:30 IST or on stop.
        <b>Stop</b> = one-day worst-case; <b>Trail</b> = peak − give-back budget; <b>Peak</b> = highest P&L seen since entry.
        Hover any row for the break details (z-score, expected vs actual move).
      </div>
    </div>`;
}
