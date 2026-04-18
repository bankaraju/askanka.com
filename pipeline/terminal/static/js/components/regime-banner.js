const REGIME_CLASSES = {
  'EUPHORIA': 'regime-euphoria',
  'RISK-ON': 'regime-risk-on',
  'NEUTRAL': 'regime-neutral',
  'CAUTION': 'regime-caution',
  'RISK-OFF': 'regime-risk-off',
};

export function render(container, data) {
  const cls = REGIME_CLASSES[data.zone] || 'regime-neutral';
  const stability = data.stable
    ? `STABLE — ${data.consecutive_days} consecutive days`
    : `UNSTABLE — ${data.consecutive_days} day, unconfirmed`;

  container.innerHTML = `
    <div class="card" style="border-left: 4px solid; margin-bottom: var(--spacing-lg);" id="regime-banner">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <div>
          <span class="topbar__regime-badge ${cls}" style="font-size: 1rem; padding: 6px 16px;">
            ${data.zone || 'UNKNOWN'}
          </span>
          <span class="text-muted" style="margin-left: 12px; font-size: 0.8125rem;">
            ${stability}
          </span>
        </div>
        <div style="text-align: right;">
          <span class="text-muted" style="font-size: 0.75rem;">
            MSI: <span class="mono">${(data.msi_score || 0).toFixed(1)}</span>
            (${data.msi_regime || 'N/A'})
          </span>
          <br>
          <span class="text-muted" style="font-size: 0.6875rem;">
            Updated: ${data.updated_at ? new Date(data.updated_at).toLocaleTimeString('en-IN') : '--'}
          </span>
        </div>
      </div>
    </div>`;

  const topBadge = document.getElementById('regime-badge');
  if (topBadge) {
    topBadge.textContent = data.zone || 'UNKNOWN';
    topBadge.className = `topbar__regime-badge ${cls}`;
  }
  const topStability = document.getElementById('regime-stability');
  if (topStability) topStability.textContent = stability;
}
