import { get } from '../lib/api.js';

let currentSubTab = 'trust-scores';

export async function render(container) {
  container.innerHTML = `
    <div class="main__subtabs">
      <button class="subtab subtab--active" data-subtab="trust-scores">Trust Scores</button>
      <button class="subtab" data-subtab="news">News</button>
      <button class="subtab" data-subtab="research">Research</button>
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

  try {
    const data = await get('/trust-scores');
    const stocks = data.stocks || [];

    if (stocks.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No trust scores available</p></div>';
      return;
    }

    el.innerHTML = `
      <div class="filter-bar">
        <input type="text" id="trust-search" class="filter-search" placeholder="Search ticker...">
        <span class="text-muted" style="font-size: 0.75rem;">${stocks.length} stocks scored</span>
      </div>
      <div id="trust-table-wrap"></div>`;

    const renderTable = (filter = '') => {
      const filtered = filter
        ? stocks.filter(s => (s.symbol || '').toUpperCase().includes(filter.toUpperCase()))
        : stocks;

      const sorted = [...filtered].sort((a, b) => {
        const gradeOrder = {'A+':0,'A':1,'B+':2,'B':3,'C':4,'D':5,'F':6,'?':7};
        return (gradeOrder[a.trust_grade] || 7) - (gradeOrder[b.trust_grade] || 7);
      });

      const rows = sorted.map(s => {
        const badgeCls = GRADE_COLORS[s.trust_grade] || 'badge--muted';
        return `<tr class="clickable" data-ticker="${s.symbol}">
          <td style="font-family: var(--font-body);">${s.symbol}</td>
          <td><span class="badge ${badgeCls}">${s.trust_grade || '?'}</span></td>
          <td class="mono">${s.trust_score != null ? s.trust_score : '--'}</td>
          <td class="text-muted" style="font-size: 0.75rem; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${s.thesis || '--'}</td>
        </tr>`;
      }).join('');

      document.getElementById('trust-table-wrap').innerHTML = `
        <table class="data-table">
          <thead><tr><th>Ticker</th><th>Grade</th><th>Score</th><th>Thesis</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`;

      document.querySelectorAll('#trust-table-wrap tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
          const panel = document.getElementById('context-panel');
          const title = document.getElementById('context-panel-title');
          const content = document.getElementById('context-panel-content');
          const ticker = row.dataset.ticker;
          if (panel && title && content) {
            title.textContent = ticker;
            const stock = stocks.find(s => s.symbol === ticker);
            content.innerHTML = `
              <div class="card" style="margin-bottom: var(--spacing-md);">
                <div class="text-muted" style="font-size: 0.75rem;">TRUST SCORE</div>
                <div class="mono" style="font-size: 2rem; color: var(--accent-gold);">${stock?.trust_grade || '?'}</div>
                <div class="mono" style="font-size: 1rem;">${stock?.trust_score ?? '--'}</div>
              </div>
              <div style="font-size: 0.8125rem; line-height: 1.6;">${stock?.thesis || 'No thesis available'}</div>`;
            panel.classList.add('context-panel--open');
          }
        });
      });
    };

    renderTable();
    document.getElementById('trust-search').addEventListener('input', (e) => renderTable(e.target.value));

  } catch {
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
    const data = await get('/research');
    const articles = data.articles || [];

    if (articles.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>No research articles available</p></div>';
      return;
    }

    const cards = articles.slice(0, 20).map((a, i) => {
      const isHero = i === 0;
      const borderStyle = isHero ? 'border: 1px solid var(--accent-gold);' : '';
      const category = a.category || a.type || 'RESEARCH';
      const catBadge = category === 'INVESTIGATION'
        ? '<span class="badge badge--red">INVESTIGATION</span>'
        : category === 'GEOPOLITICAL'
        ? '<span class="badge badge--amber">GEOPOLITICAL</span>'
        : '<span class="badge badge--blue">RESEARCH</span>';

      return `
        <div class="card" style="${borderStyle} margin-bottom: var(--spacing-md); cursor: pointer;"
             data-filename="${a.filename || ''}">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            ${catBadge}
            <span class="text-muted" style="font-size: 0.6875rem;">${a.date || a.published || ''}</span>
          </div>
          <h3 style="font-size: ${isHero ? '1.125rem' : '0.9375rem'}; margin-top: 4px;">${a.headline || a.title || 'Untitled'}</h3>
        </div>`;
    }).join('');

    el.innerHTML = cards;

  } catch {
    el.innerHTML = '<div class="empty-state"><p>Failed to load research</p></div>';
  }
}
