const REGIME_CLASSES = {
  'EUPHORIA': 'regime-euphoria',
  'RISK-ON': 'regime-risk-on',
  'NEUTRAL': 'regime-neutral',
  'CAUTION': 'regime-caution',
  'RISK-OFF': 'regime-risk-off',
};

function _msiStaleDot(msiUpdatedAt) {
  if (!msiUpdatedAt) return '';
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata', hour12: false,
    hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date());
  const hh = Number(parts.find(p => p.type === 'hour').value);
  const mm = Number(parts.find(p => p.type === 'minute').value);
  const totalMin = hh * 60 + mm;
  const inMarket = totalMin >= 555 && totalMin < 930;  // 09:15–15:30
  if (!inMarket) return '';
  const ageMin = (Date.now() - new Date(msiUpdatedAt)) / 60000;
  if (ageMin < 30) return '';
  return ' <span title="MSI not refreshed in 30+ min" style="color: var(--colour-amber); font-size: 0.8em;">●</span>';
}

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
            (${data.msi_regime || 'N/A'})${_msiStaleDot(data.msi_updated_at)}
          </span>
          <br>
          <span class="text-muted" style="font-size: 0.6875rem;">
            MSI: ${data.msi_updated_at ? new Date(data.msi_updated_at).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit'}) : '--'}
            · Regime: ${data.updated_at ? new Date(data.updated_at).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit'}) : '--'}
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
