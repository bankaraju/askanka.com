// Shared tab-header — every page renders one of these at the top so the user
// always knows: what tab this is, what it shows, when it last refreshed, and
// when the next refresh is due.
//
// Usage:
//   import { renderTabHeader } from '../components/tab-header.js';
//   container.innerHTML = renderTabHeader({
//     title: 'News',
//     subtitle: 'Corporate-action verdicts from EOD news classifier',
//     cadence: 'Refreshes daily at 16:20 IST after AnkaEODNews',
//     lastUpdated: someIsoString,         // optional; renders age
//     status: 'fresh' | 'stale' | 'empty' // optional; colors the chip
//   }) + ...

function _esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _ageHuman(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const s = (Date.now() - t) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h ago`;
  return `${(s / 86400).toFixed(1)}d ago`;
}

export function renderTabHeader({ title, subtitle, cadence, lastUpdated, status }) {
  const age = _ageHuman(lastUpdated);
  const chipCls = status === 'stale' ? 'tab-header__chip--stale'
    : status === 'empty' ? 'tab-header__chip--empty'
    : 'tab-header__chip--fresh';
  const chip = age
    ? `<span class="tab-header__chip ${chipCls}">${_esc(age)}</span>`
    : '';
  return `
    <div class="tab-header">
      <div class="tab-header__row">
        <h2 class="tab-header__title">${_esc(title || '')}</h2>
        ${chip}
      </div>
      ${subtitle ? `<p class="tab-header__sub">${_esc(subtitle)}</p>` : ''}
      ${cadence ? `<p class="tab-header__cadence">${_esc(cadence)}</p>` : ''}
    </div>
  `;
}

// Helpful empty-state with a "why this is empty + when to expect data" block.
// Use when a tab's data file exists but contains zero rows after filtering.
export function renderEmptyState({ title, reason, nextUpdate, link }) {
  const linkHtml = link
    ? `<p class="empty-state__link"><a href="${_esc(link.href)}">${_esc(link.label || 'See more')}</a></p>`
    : '';
  return `
    <div class="empty-state empty-state--clarified">
      <p class="empty-state__title">${_esc(title || 'No data')}</p>
      ${reason ? `<p class="empty-state__sub">${_esc(reason)}</p>` : ''}
      ${nextUpdate ? `<p class="empty-state__sub">${_esc(nextUpdate)}</p>` : ''}
      ${linkHtml}
    </div>
  `;
}
