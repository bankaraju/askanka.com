import { get } from '../lib/api.js';

export async function render(container) {
  container.innerHTML = '<div class="skeleton skeleton--card"></div>';
  try {
    const data = await get('/news/macro');
    const items = data.items || [];
    if (items.length === 0) {
      container.innerHTML = '<div class="empty-state"><p>No news available</p></div>';
      return;
    }
    const newsHtml = items.slice(0, 50).map(item => {
      const headline = item.headline || item.title || JSON.stringify(item).slice(0, 100);
      const time = item.timestamp || item.date || '';
      const sentiment = item.sentiment || item.impact || '';
      const sentBadge = sentiment
        ? `<span class="badge badge--${sentiment === 'HIGH' || sentiment === 'negative' ? 'red' : sentiment === 'MEDIUM' ? 'amber' : 'blue'}">${sentiment}</span>`
        : '';
      return `<div style="padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--border);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
          <div style="font-size: 0.875rem;">${headline}</div>
          ${sentBadge}
        </div>
        <div class="text-muted" style="font-size: 0.6875rem; margin-top: 2px;">${time}</div>
      </div>`;
    }).join('');
    container.innerHTML = `<div class="card">${newsHtml}</div>`;
  } catch {
    container.innerHTML = '<div class="empty-state"><p>Failed to load news</p></div>';
  }
}

export function destroy() {}
