export function renderGrid(container, cards) {
  const html = cards.map(card => `
    <div class="kpi-card">
      <div class="kpi-card__label">${card.label}</div>
      <div class="kpi-card__value ${card.colorClass || ''}">${card.value}</div>
      <div class="kpi-card__sub">${card.sub || ''}</div>
    </div>
  `).join('');

  container.innerHTML = `<div class="kpi-grid">${html}</div>`;
}
