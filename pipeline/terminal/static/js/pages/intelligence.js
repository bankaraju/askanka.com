import { get } from '../lib/api.js';
import { renderLeverageCard, renderShadowStrip } from '../components/leverage-matrix.js';

let currentSubTab = 'trust-scores';

export async function render(container) {
  container.innerHTML = `
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="trust-scores">Trust Scores</button>
      <button class="subtab" data-subtab="news">News</button>
      <button class="subtab" data-subtab="research">Research</button>
      <button class="subtab" data-subtab="options">Options</button>
    </div>
    <div id="intel-content"></div>`;

  container.querySelectorAll('.subtab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.subtab').forEach(b => b.classList.remove('subtab--active'));
      btn.classList.add('subtab--active');
      loadSubTab(btn.dataset.subtab);
    });
  });

  await loadSubTab('trust-scores');
}

export function destroy() {}

async function loadSubTab(tab) {
  currentSubTab = tab;
  const el = document.getElementById('intel-content');
  if (!el) return;

  switch (tab) {
    case 'trust-scores': await renderTrustScores(el); break;
    case 'news': await renderNews(el); break;
    case 'research': await renderResearch(el); break;
    case 'options': await renderOptions(el); break;
  }
}

const GRADE_COLORS = {
  'A+': 'badge--green', 'A': 'badge--green',
  'B+': 'badge--blue', 'B': 'badge--blue',
  'C': 'badge--amber',
  'D': 'badge--red', 'F': 'badge--red',
  '?': 'badge--muted',
};

async function renderTrustScores(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  function _heatmapBg(score) {
    if (score == null) return '';
    if (score >= 80) return 'background: rgba(34,197,94,0.25)';
    if (score >= 60) return 'background: rgba(34,197,94,0.12)';
    if (score >= 40) return 'background: rgba(245,158,11,0.15)';
    if (score >= 20) return 'background: rgba(249,115,22,0.15)';
    return 'background: rgba(239,68,68,0.15)';
  }

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
          id,
          display_name: v.name || id,
          count: v.count || 0,
        }));

    if (stocks.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No trust scores available</p></div>';
      return;
    }

    sectors.sort((a, b) => (b.count || 0) - (a.count || 0));
    const sectorOptions = sectors.map(sec =>
      `<option value="${_esc(sec.id)}">${_esc(sec.display_name)} (${sec.count})</option>`
    ).join('');

    el.innerHTML = `
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
    let sortDir = -1; // -1 = desc

    const renderTable = () => {
      const tickerFilter = (document.getElementById('trust-search')?.value || '').toUpperCase();
      const sectorFilter = document.getElementById('trust-sector')?.value || '';

      let filtered = stocks.filter(s => {
        const matchTicker = !tickerFilter || (s.symbol || '').toUpperCase().includes(tickerFilter);
        const matchSector = !sectorFilter || (s.sector || '') === sectorFilter;
        return matchTicker && matchSector;
      });

      filtered = [...filtered].sort((a, b) => {
        let av = a[sortCol];
        let bv = b[sortCol];
        if (av == null) av = sortDir === -1 ? -Infinity : Infinity;
        if (bv == null) bv = sortDir === -1 ? -Infinity : Infinity;
        if (typeof av === 'string') return sortDir * av.localeCompare(bv);
        return sortDir * (av - bv);
      });

      document.getElementById('trust-count').textContent = `${filtered.length} / ${stocks.length} stocks`;

      const colDefs = [
        { key: 'symbol',            label: 'Ticker' },
        { key: 'display_name',      label: 'Sector' },
        { key: 'sector_grade',      label: 'Grade' },
        { key: 'composite_score',   label: 'Composite' },
        { key: 'financial_score',   label: 'Fin' },
        { key: 'management_score',  label: 'Mgmt' },
        { key: 'sector_rank',       label: 'Rank' },
        { key: 'grade_reason',      label: 'Remark' },
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

        return `<tr class="clickable" data-ticker="${_esc(s.symbol)}">
          <td style="font-family: var(--font-mono); font-weight:600;">${_esc(s.symbol)}</td>
          <td class="text-muted" style="font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:120px;" title="${_esc(s.display_name || s.sector || '')}">${_esc(sectorDisplay)}</td>
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

      // Sort header click
      document.querySelectorAll('#trust-table-wrap th.sortable').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
          const col = th.dataset.col;
          if (sortCol === col) {
            sortDir *= -1;
          } else {
            sortCol = col;
            sortDir = -1;
          }
          renderTable();
        });
      });

      // Row click — context panel
      document.querySelectorAll('#trust-table-wrap tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
          const panel = document.getElementById('context-panel');
          const title = document.getElementById('context-panel-title');
          const content = document.getElementById('context-panel-content');
          const ticker = row.dataset.ticker;
          if (!(panel && title && content)) return;

          const s = stocks.find(st => st.symbol === ticker);
          if (!s) return;

          title.textContent = ticker;
          const grade = s.sector_grade || s.trust_grade || '?';
          const badgeCls = GRADE_COLORS[grade] || 'badge--muted';
          const composite = s.composite_score ?? s.trust_score;
          const fin = s.financial_score;
          const mgmt = s.management_score;
          const conf = s.confidence || '';
          const confBadge = conf ? `<span class="badge badge--muted" style="margin-left:var(--spacing-xs);">${_esc(conf)}</span>` : '';
          const rankLine = (s.sector_rank != null && s.sector_total != null && s.display_name)
            ? `<div class="text-muted" style="font-size:0.8rem; margin-bottom:var(--spacing-sm);">Rank <strong>${s.sector_rank}/${s.sector_total}</strong> in ${_esc(s.display_name)}${s.sector_leader ? `. Leader: <strong>${_esc(s.sector_leader)}</strong>${s.sector_leader_composite != null ? ` (${s.sector_leader_composite})` : ''}.` : '.'}</div>`
            : '';
          const strengthHtml = s.biggest_strength
            ? `<div style="margin-top:var(--spacing-sm);"><span class="text-muted" style="font-size:0.75rem;">STRENGTH</span><div style="font-size:0.8125rem; color:var(--color-green);">${_esc(s.biggest_strength)}</div></div>`
            : '';
          const redFlagHtml = s.biggest_red_flag
            ? `<div style="margin-top:var(--spacing-sm);"><span class="text-muted" style="font-size:0.75rem;">RED FLAG</span><div style="font-size:0.8125rem; color:var(--color-red);">${_esc(s.biggest_red_flag)}</div></div>`
            : '';
          const reasonHtml = (s.grade_reason || s.thesis)
            ? `<div style="margin-top:var(--spacing-sm);"><span class="text-muted" style="font-size:0.75rem;">GRADE REASON</span><div style="font-size:0.8125rem; line-height:1.6; margin-top:2px;">${_esc(s.grade_reason || s.thesis)}</div></div>`
            : '';

          content.innerHTML = `
            ${rankLine}
            <div class="card" style="margin-bottom: var(--spacing-md);">
              <div style="display:flex; align-items:center; gap:var(--spacing-sm); margin-bottom:var(--spacing-xs);">
                <span class="badge ${badgeCls}" style="font-size:1.1rem; padding: 4px 10px;">${_esc(grade)}</span>
                ${confBadge}
              </div>
              <div style="display:flex; gap:var(--spacing-md); flex-wrap:wrap; margin-top:var(--spacing-xs);">
                <div>
                  <div class="text-muted" style="font-size:0.7rem;">COMPOSITE</div>
                  <div class="mono" style="font-size:1.5rem; color:var(--accent-gold);">${composite != null ? composite : '--'}</div>
                </div>
                <div>
                  <div class="text-muted" style="font-size:0.7rem;">FINANCIAL</div>
                  <div class="mono" style="font-size:1.25rem;">${fin != null ? fin : '--'}</div>
                </div>
                <div>
                  <div class="text-muted" style="font-size:0.7rem;">MANAGEMENT</div>
                  <div class="mono" style="font-size:1.25rem;">${mgmt != null ? mgmt : '--'}</div>
                </div>
              </div>
            </div>
            ${reasonHtml}
            ${strengthHtml}
            ${redFlagHtml}
            <div id="oi-panel-${_esc(ticker)}" style="margin-top:var(--spacing-md);">
              <div class="text-muted" style="font-size:0.75rem;">Loading OI…</div>
            </div>`;

          panel.classList.add('context-panel--open');

          // Lazy-load live OI snapshot for this ticker
          (async () => {
            const mount = document.getElementById(`oi-panel-${ticker}`);
            if (!mount) return;
            try {
              const oi = await get(`/oi/${encodeURIComponent(ticker)}`);
              if (!oi || oi.found === false) {
                mount.innerHTML = '<div class="text-muted" style="font-size:0.75rem;">No OI snapshot (stock not in F&O scan universe).</div>';
                return;
              }
              mount.innerHTML = _renderOiPanel(oi);
            } catch (e) {
              mount.innerHTML = '<div class="text-muted" style="font-size:0.75rem;">OI fetch failed.</div>';
            }
          })();
        });
      });
    };

    renderTable();

    document.getElementById('trust-search').addEventListener('input', renderTable);
    document.getElementById('trust-sector').addEventListener('change', renderTable);

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load trust scores</p></div>';
  }
}

async function renderNews(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get('/news/macro');
    const items = data.items || [];

    if (items.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No news available</p></div>';
      return;
    }

    const newsHtml = items.slice(0, 30).map(item => {
      const headline = item.headline || item.title || JSON.stringify(item).slice(0, 100);
      const time = item.timestamp || item.date || '';
      const sentiment = item.sentiment || item.impact || '';
      const sentBadge = sentiment
        ? `<span class="badge badge--${sentiment === 'HIGH' || sentiment === 'negative' ? 'red' : sentiment === 'MEDIUM' ? 'amber' : 'blue'}">${sentiment}</span>`
        : '';

      return `
        <div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--border);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
            <div style="font-size: 0.875rem;">${headline}</div>
            ${sentBadge}
          </div>
          <div class="text-muted" style="font-size: 0.6875rem; margin-top: 2px;">${time}</div>
        </div>`;
    }).join('');

    el.innerHTML = `<div class="card">${newsHtml}</div>`;

  } catch {
    el.innerHTML = '<div class="empty-state"><p>Failed to load news</p></div>';
  }
}

async function renderResearch(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const data = await get('/research/digest');

    const genTime = data.generated_at || '';
    const isStale = _isStale(genTime);

    el.innerHTML = `
      ${_digestHeader(genTime, isStale)}
      <div class="digest-grid">
        <div>
          <div class="digest-column-header">Thesis — The Claim</div>
          ${_regimeCard(data.regime_thesis)}
          ${_spreadCards(data.spread_theses)}
        </div>
        <div>
          <div class="digest-column-header">Evidence — The Proof</div>
          ${_breaksCard(data.correlation_breaks)}
          ${_backtestCard(data.backtest_validation)}
        </div>
      </div>`;

    _wireBreakClicks(el);
    _scheduleRefresh(el);

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load intelligence digest</p></div>';
  }
}

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ---- OI panel (live positioning data) ---------------------------------------
const PIN_COLORS = {
  STRONG_PIN: 'color:var(--color-red); font-weight:600;',
  MILD_PIN:   'color:var(--color-amber);',
  FAR:        'color:var(--text-muted);',
  UNRELIABLE: 'color:var(--text-muted); font-style:italic;',
};

const PCR_COLORS = {
  BULLISH:   'color:var(--color-green);',
  MILD_BULL: 'color:var(--color-green);',
  NEUTRAL:   'color:var(--text-muted);',
  MILD_BEAR: 'color:var(--color-amber);',
  BEARISH:   'color:var(--color-red);',
};

function _renderOiExpiryBlock(label, block, ltp) {
  if (!block || !block.expiry) return '';
  const pin = block.pinning || {};
  const pinStyle = PIN_COLORS[pin.pin_label] || '';
  const pcrStyle = PCR_COLORS[block.sentiment] || '';
  const cw = (block.call_walls || []).slice(0, 3).map(w => `${w.strike}=${(w.oi/1000).toFixed(0)}K`).join(', ');
  const pw = (block.put_walls || []).slice(0, 3).map(w => `${w.strike}=${(w.oi/1000).toFixed(0)}K`).join(', ');
  const dteLabel = pin.days_to_expiry != null ? `${pin.days_to_expiry}d` : '--';
  return `
    <div style="border-left:2px solid var(--border-subtle); padding-left:var(--spacing-sm); margin-top:var(--spacing-xs);">
      <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:2px;">
        <span style="font-size:0.7rem; color:var(--text-muted); letter-spacing:0.05em;">${_esc(label.toUpperCase())}</span>
        <span class="mono" style="font-size:0.75rem; color:var(--text-muted);">${_esc(block.expiry)} · ${_esc(dteLabel)}</span>
      </div>
      <div style="display:flex; gap:var(--spacing-md); flex-wrap:wrap; font-size:0.8125rem;">
        <span>PCR <strong class="mono">${block.pcr != null ? block.pcr.toFixed(2) : '--'}</strong> <span style="${pcrStyle}">${_esc(block.sentiment || '')}</span></span>
        <span>Max pain <strong class="mono">${pin.pin_strike != null ? pin.pin_strike : '--'}</strong> <span style="${pinStyle}">${_esc(pin.pin_label || '')}</span>${pin.pin_distance_pct != null ? ` <span class="text-muted" style="font-size:0.75rem;">(${pin.pin_distance_pct > 0 ? '+' : ''}${pin.pin_distance_pct}%)</span>` : ''}</span>
      </div>
      <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
        <div>CE walls: <span class="mono">${_esc(cw) || '--'}</span></div>
        <div>PE walls: <span class="mono">${_esc(pw) || '--'}</span></div>
      </div>
    </div>`;
}

function _renderOiPanel(oi) {
  const ts = oi.timestamp ? new Date(oi.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '';
  const rollover = oi.rollover_ratio;
  let rolloverLine = '';
  if (rollover != null) {
    const rolloverColor = rollover > 0.5 ? 'color:var(--color-amber);' : 'color:var(--text-muted);';
    rolloverLine = `<div style="font-size:0.75rem; ${rolloverColor} margin-top:4px;">Rollover next/near: <strong class="mono">${rollover.toFixed(2)}</strong>${rollover > 0.5 ? ' — active roll' : ''}</div>`;
  }
  return `
    <div class="card" style="padding:var(--spacing-sm);">
      <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:var(--spacing-xs);">
        <span style="font-size:0.8125rem; font-weight:600; letter-spacing:0.03em;">POSITIONING (LIVE)</span>
        <span class="text-muted" style="font-size:0.7rem;">${_esc(ts)}</span>
      </div>
      ${_renderOiExpiryBlock('Near', oi.near, oi.ltp)}
      ${_renderOiExpiryBlock('Next', oi.next, oi.ltp)}
      ${rolloverLine}
    </div>`;
}

function _istHour() {
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false });
  return parseInt(h, 10);
}

function _isStale(isoTimestamp) {
  if (!isoTimestamp) return false;
  const hours = _istHour();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return false;
  const genDate = new Date(isoTimestamp);
  const ageMinutes = (Date.now() - genDate) / 60000;
  return ageMinutes > 30;
}

function _digestHeader(genTime, isStale) {
  const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
  const staleBadge = isStale
    ? ' <span class="badge badge--stale">STALE</span>'
    : '';
  return `
    <div class="digest-header">
      <h2 class="digest-header__title">Intelligence Digest</h2>
      <span class="digest-header__time">Last computed: ${timeStr}${staleBadge}</span>
    </div>`;
}

function _regimeCard(r) {
  if (!r) return '<div class="digest-card"><p class="text-muted">No regime data</p></div>';
  const groundBadge = r.grounding_ok === false
    ? '<span class="badge badge--red">GROUNDING FAILURE</span>' : '';
  return `
    <div class="digest-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div class="digest-card__title">Regime Thesis</div>
        ${groundBadge}
      </div>
      <div class="digest-card__subtitle">Why are we in ${r.zone}?</div>
      <div class="digest-row">
        <span class="digest-row__label">Zone</span>
        <span class="digest-row__value"><span class="badge badge--gold">${r.zone}</span></span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">Source</span>
        <span class="digest-row__value">${r.regime_source || '--'}</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">FII Net</span>
        <span class="digest-row__value ${r.fii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.fii_net)}cr</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">DII Net</span>
        <span class="digest-row__value ${r.dii_net >= 0 ? 'text-green' : 'text-red'}">₹${_fmt(r.dii_net)}cr</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">MSI Score</span>
        <span class="digest-row__value">${r.msi_score != null ? r.msi_score.toFixed(2) : '--'}</span>
      </div>
      <div class="digest-row">
        <span class="digest-row__label">Stability</span>
        <span class="digest-row__value">${r.stability_days}d ${r.stable ? '(locked)' : '(unstable)'}</span>
      </div>
      ${r.flip_triggers && r.flip_triggers.length > 0 ? `
        <div style="margin-top: var(--spacing-sm); font-size: 0.75rem; color: var(--text-muted);">
          <strong>Flip triggers:</strong> ${r.flip_triggers.join(' · ')}
        </div>` : ''}
    </div>`;
}

function _spreadCards(spreads) {
  if (!spreads || spreads.length === 0) {
    return '<div class="digest-card"><p class="text-muted">No active spreads</p></div>';
  }
  return spreads.map(s => {
    const badges = (s.caution_badges || []).map(b => {
      const cls = b.type === 'blocked' ? 'badge--blocked' : b.type === 'caution' ? 'badge--amber' : 'badge--muted';
      return `<span class="badge ${cls}" title="${b.detail || ''}">${b.label}</span>`;
    }).join(' ');

    const cardCls = s.caution_badges?.some(b => b.type === 'blocked') ? 'digest-card--blocked'
      : s.caution_badges?.length > 0 ? 'digest-card--caution' : '';

    const actionCls = s.action === 'ENTER' ? 'text-green' : s.action === 'EXIT' ? 'text-red' : 'text-secondary';

    return `
      <div class="digest-card ${cardCls}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div class="digest-card__title">${s.name}</div>
          <div>${badges}</div>
        </div>
        <div class="digest-card__subtitle">Spread thesis</div>
        <div class="digest-row">
          <span class="digest-row__label">Action</span>
          <span class="digest-row__value ${actionCls}">${s.action}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Conviction</span>
          <span class="digest-row__value">${s.conviction} (${s.score})</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Z-Score</span>
          <span class="digest-row__value">${s.z_score != null ? s.z_score.toFixed(2) + 'σ' : '--'}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Regime Fit</span>
          <span class="digest-row__value">${s.regime_fit ? '✓' : '✗'}</span>
        </div>
        <div class="digest-row">
          <span class="digest-row__label">Gate</span>
          <span class="digest-row__value">${s.gate_status}</span>
        </div>
      </div>`;
  }).join('');
}

function _breaksCard(breaks) {
  if (!breaks || breaks.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No breaks detected — stocks aligned with regime</p>
    </div>`;
  }
  const rows = breaks.map(b => {
    const dir = b.z_score < 0 ? '▼' : '▲';
    const cls = b.classification === 'CONFIRMED_WARNING' ? 'text-red'
      : b.classification === 'CONFIRMED_OPPORTUNITY' ? 'text-green' : 'text-secondary';
    return `
      <div class="digest-break-row" data-ticker="${b.ticker}">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="mono" style="font-size: 0.875rem;">${b.ticker}</span>
          <span class="mono ${cls}">${b.z_score > 0 ? '+' : ''}${b.z_score.toFixed(1)}σ ${dir}</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
          <span>OI: ${b.oi_confirmation}</span>
          <span class="badge ${b.classification === 'CONFIRMED_WARNING' ? 'badge--red' : b.classification === 'CONFIRMED_OPPORTUNITY' ? 'badge--green' : 'badge--muted'}">${b.classification.replace(/_/g, ' ')}</span>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="digest-card">
      <div class="digest-card__title">Correlation Breaks</div>
      <div class="digest-card__subtitle">What is behaving wrong? (click ticker to investigate)</div>
      ${rows}
    </div>`;
}

function _backtestCard(backtest) {
  if (!backtest || backtest.length === 0) {
    return `<div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <div class="digest-card__subtitle">Has this worked before?</div>
      <p class="text-muted" style="font-size: 0.8125rem;">No backtest data available for current regime</p>
    </div>`;
  }
  const rows = backtest.map(b => {
    const statusCls = b.status === 'WITHIN_CI' ? 'badge--green'
      : b.status === 'EDGE_CI' ? 'badge--amber' : 'badge--red';
    const winPct = (b.win_rate * 100).toFixed(0);
    return `
      <div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid rgba(30, 41, 59, 0.3);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 0.875rem;">${b.spread}</span>
          <span class="badge ${statusCls}">${b.status.replace(/_/g, ' ')}</span>
        </div>
        <div style="display: flex; gap: var(--spacing-lg); font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
          <span>Win: <span class="mono">${winPct}%</span></span>
          <span>Period: <span class="mono">${b.best_period}</span></span>
          <span>Avg: <span class="mono">${b.avg_return >= 0 ? '+' : ''}${(b.avg_return * 100).toFixed(2)}%</span></span>
        </div>
      </div>`;
  }).join('');
  return `
    <div class="digest-card">
      <div class="digest-card__title">Backtest Validation</div>
      <div class="digest-card__subtitle">Has this worked before?</div>
      ${rows}
    </div>`;
}

function _fmt(n) {
  if (n == null) return '--';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 1 });
}

function _wireBreakClicks(container) {
  container.querySelectorAll('.digest-break-row[data-ticker]').forEach(row => {
    row.addEventListener('click', async () => {
      const ticker = row.dataset.ticker;
      const panel = document.getElementById('context-panel');
      const title = document.getElementById('context-panel-title');
      const content = document.getElementById('context-panel-content');
      if (!panel || !title || !content) return;

      title.textContent = ticker;
      content.innerHTML = '<div class="skeleton skeleton--card"></div>';
      panel.classList.add('context-panel--open');

      try {
        const [trustData, newsData] = await Promise.all([
          get(`/trust-scores/${ticker}`),
          get(`/news/${ticker}`),
        ]);

        const gradeCls = {
          'A+': 'badge--green', 'A': 'badge--green',
          'B+': 'badge--blue', 'B': 'badge--blue',
          'C': 'badge--amber', 'D': 'badge--red', 'F': 'badge--red',
        }[trustData.trust_grade] || 'badge--muted';

        const newsHtml = (newsData.items || []).slice(0, 10).map(n => `
          <div style="padding: var(--spacing-xs) 0; border-bottom: 1px solid rgba(30,41,59,0.3); font-size: 0.8125rem;">
            ${_esc(n.headline || n.title || '--')}
            <div class="text-muted" style="font-size: 0.6875rem;">${_esc(n.timestamp || n.date || '')}</div>
          </div>`).join('');

        content.innerHTML = `
          <div class="card" style="margin-bottom: var(--spacing-md);">
            <div class="text-muted" style="font-size: 0.75rem;">TRUST SCORE</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-sm);">
              <span class="badge ${gradeCls}" style="font-size: 2rem;">${_esc(trustData.trust_grade || '?')}</span>
              <span class="mono">${trustData.trust_score ?? '--'}</span>
            </div>
            <div style="font-size: 0.8125rem; margin-top: var(--spacing-sm); line-height: 1.6;">${_esc(trustData.thesis || 'No thesis')}</div>
          </div>
          <div class="card">
            <div class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);">RECENT NEWS</div>
            ${newsHtml || '<p class="text-muted">No news</p>'}
          </div>`;
      } catch {
        content.innerHTML = '<div class="empty-state"><p>Failed to load context</p></div>';
      }
    });
  });
}

async function renderOptions(el) {
  el.innerHTML = '<div class="skeleton skeleton--card"></div>';

  try {
    const [digestData, shadows] = await Promise.all([
      get('/research/digest'),
      get('/research/options-shadow').catch(() => []),
    ]);

    const genTime = digestData.generated_at || '';
    const isStale = _isStale(genTime);
    const timeStr = genTime ? new Date(genTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '--';
    const staleBadge = isStale ? ' <span class="badge badge--stale">STALE</span>' : '';

    const matrices = digestData.leverage_matrices || [];

    const matrixCards = matrices.length > 0
      ? matrices.map(m => renderLeverageCard(m)).join('')
      : '<div class="digest-card"><p class="text-muted">No spreads with 65+ conviction — leverage matrix requires qualifying signals</p></div>';

    el.innerHTML = `
      <div class="digest-header">
        <h2 class="digest-header__title">Synthetic Options — Drift vs Rent</h2>
        <span class="digest-header__time">Vol data: ${timeStr}${staleBadge}</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--spacing-md);">
        ${matrixCards}
        ${renderShadowStrip(shadows)}
      </div>`;

    _wireOptionsTickers(el, matrices);

  } catch (err) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load options intelligence</p></div>';
  }
}

function _wireOptionsTickers(container, matrices) {
  container.querySelectorAll('.clickable-ticker[data-ticker]').forEach(span => {
    span.addEventListener('click', async () => {
      const ticker = span.dataset.ticker;
      const panel = document.getElementById('context-panel');
      const title = document.getElementById('context-panel-title');
      const content = document.getElementById('context-panel-content');
      if (!panel || !title || !content) return;

      title.textContent = ticker;
      content.innerHTML = '<div class="skeleton skeleton--card"></div>';
      panel.classList.add('context-panel--open');

      try {
        const [trustData, newsData] = await Promise.all([
          get(`/trust-scores/${ticker}`),
          get(`/news/${ticker}`),
        ]);

        const gradeCls = {
          'A+': 'badge--green', 'A': 'badge--green',
          'B+': 'badge--blue', 'B': 'badge--blue',
          'C': 'badge--amber', 'D': 'badge--red', 'F': 'badge--red',
        }[trustData.trust_grade] || 'badge--muted';

        const volBlock = (() => {
          if (!matrices || matrices.length === 0) return '';
          for (const m of matrices) {
            if (!m.grounding_ok) continue;
            if (m.long_side_vol != null) {
              return `
                <div class="card" style="margin-bottom: var(--spacing-md);">
                  <div class="text-muted" style="font-size: 0.75rem;">SYNTHETIC VOL</div>
                  <div style="display: flex; gap: var(--spacing-lg); margin-top: var(--spacing-xs);">
                    <div>
                      <div class="text-muted" style="font-size: 0.6875rem;">Long Side</div>
                      <div class="mono">${(m.long_side_vol * 100).toFixed(1)}%</div>
                    </div>
                    <div>
                      <div class="text-muted" style="font-size: 0.6875rem;">Short Side</div>
                      <div class="mono">${(m.short_side_vol * 100).toFixed(1)}%</div>
                    </div>
                  </div>
                </div>`;
            }
          }
          return '';
        })();

        const newsHtml = (newsData.items || []).slice(0, 10).map(n => `
          <div style="padding: var(--spacing-xs) 0; border-bottom: 1px solid rgba(30,41,59,0.3); font-size: 0.8125rem;">
            ${_esc(n.headline || n.title || '--')}
            <div class="text-muted" style="font-size: 0.6875rem;">${_esc(n.timestamp || n.date || '')}</div>
          </div>`).join('');

        content.innerHTML = `
          <div class="card" style="margin-bottom: var(--spacing-md);">
            <div class="text-muted" style="font-size: 0.75rem;">TRUST SCORE</div>
            <div style="display: flex; align-items: baseline; gap: var(--spacing-sm);">
              <span class="badge ${gradeCls}" style="font-size: 2rem;">${_esc(trustData.trust_grade || '?')}</span>
              <span class="mono">${trustData.trust_score ?? '--'}</span>
            </div>
            <div style="font-size: 0.8125rem; margin-top: var(--spacing-sm); line-height: 1.6;">${_esc(trustData.thesis || 'No thesis')}</div>
          </div>
          ${volBlock}
          <div class="card">
            <div class="text-muted" style="font-size: 0.75rem; margin-bottom: var(--spacing-sm);">RECENT NEWS</div>
            ${newsHtml || '<p class="text-muted">No news</p>'}
          </div>`;
      } catch {
        content.innerHTML = '<div class="empty-state"><p>Failed to load context</p></div>';
      }
    });
  });
}

let _refreshTimer = null;

function _scheduleRefresh(container) {
  if (_refreshTimer) clearInterval(_refreshTimer);
  const hours = _istHour();
  const inMarket = hours >= 9 && hours < 16;
  if (!inMarket) return;
  _refreshTimer = setInterval(() => {
    if (currentSubTab === 'research') {
      const el = document.getElementById('intel-content');
      if (el) renderResearch(el);
    }
  }, 5 * 60 * 1000);
}
