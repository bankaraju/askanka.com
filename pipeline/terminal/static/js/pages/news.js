import { get } from '../lib/api.js';
import { renderTabHeader, renderEmptyState } from '../components/tab-header.js';

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// Whitelist for sentiment CSS class fragment — never interpolate raw values into class names
const SENTIMENT_CLASS = {
  bullish: 'blue', positive: 'blue',
  bearish: 'red', negative: 'red', HIGH: 'red',
  neutral: 'muted', MEDIUM: 'amber',
};

const HEADER_PROPS = {
  title: 'News',
  subtitle: 'Corporate-action verdicts from EOD news classifier — HIGH_IMPACT and MODERATE rows with ADD/CUT recommendations.',
  cadence: 'Source: news_verdicts.json · Refreshes 16:20 IST daily (AnkaEODNews) + intraday at every 15-min cycle.',
};

export async function render(container) {
  container.innerHTML = renderTabHeader(HEADER_PROPS) + '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/news/macro');
    const items = data.items || [];
    const lastUpdated = data.generated_at || data.timestamp || null;
    const headerHtml = renderTabHeader({
      ...HEADER_PROPS,
      lastUpdated,
      status: items.length === 0 ? 'empty' : 'fresh',
    });
    if (items.length === 0) {
      container.innerHTML = headerHtml + renderEmptyState({
        title: 'No actionable news verdicts',
        reason: 'Yesterday\'s EOD classifier produced 0 rows that pass the HIGH_IMPACT+MODERATE × ADD/CUT filter. Backlog #37 (news_backtest impact classification audit) addresses why the classifier is grading every event NO_IMPACT.',
        nextUpdate: 'Next refresh: today 16:20 IST after AnkaEODNews completes.',
      });
      return;
    }
    const newsHtml = items.slice(0, 50).map(item => {
      const headline = item.headline || item.title || JSON.stringify(item).slice(0, 100);
      const time = item.timestamp || item.date || '';
      const sentiment = item.sentiment || item.impact || '';
      const sentBadge = sentiment
        ? `<span class="badge badge--${SENTIMENT_CLASS[sentiment] || 'muted'}">${_esc(sentiment)}</span>`
        : '';
      return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--border);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
          <div style="font-size: 0.875rem;">${_esc(headline)}</div>
          ${sentBadge}
        </div>
        <div class="text-muted" style="font-size: 0.6875rem; margin-top: 2px;">${_esc(time)}</div>
      </div>`;
    }).join('');
    container.innerHTML = headerHtml + `<div class="card">${newsHtml}</div>`;
  } catch (e) {
    container.innerHTML = renderTabHeader(HEADER_PROPS) + renderEmptyState({
      title: 'Failed to load news',
      reason: `API error: ${_esc(e.message || String(e))}`,
      nextUpdate: 'Check that the terminal server is running and news_verdicts.json exists.',
    });
  }
}

export function destroy() {}
