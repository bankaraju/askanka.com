// URL-encoded filter chips. State is read from window.location.hash query string
// (after #) so filtered views are deep-linkable. onChange fires after each toggle.
//
// Usage:
//   render(container, {
//     groups: [
//       { key: 'source', label: 'Source', options: ['static_config', 'regime_engine'] },
//       { key: 'conviction', label: 'Conviction', options: ['HIGH', 'MEDIUM', 'LOW'] },
//     ],
//   }, onChange);
//
// State helper:
//   getState() → { source: ['static_config'], conviction: ['HIGH'] }

export function getState() {
  const hash = window.location.hash.slice(1);
  if (!hash) return {};
  const params = new URLSearchParams(hash);
  const out = {};
  for (const [k, v] of params.entries()) {
    out[k] = v ? v.split(',').filter(Boolean) : [];
  }
  return out;
}

function setState(state) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) {
    if (v && v.length > 0) params.set(k, v.join(','));
  }
  const next = params.toString();
  const newHash = next ? `#${next}` : '';
  if (window.location.hash !== newHash) {
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}${newHash}`);
  }
}

export function render(container, config, onChange) {
  const state = getState();
  for (const g of config.groups) {
    if (!state[g.key]) state[g.key] = [];
  }

  function chipHtml(groupKey, opt) {
    const selected = state[groupKey].includes(opt);
    return `<button class="filter-chip ${selected ? 'filter-chip--active' : ''}"
      data-group="${groupKey}" data-val="${opt}">${opt}</button>`;
  }

  container.innerHTML = config.groups.map(g => `
    <div class="filter-chip-group">
      <span class="filter-chip-label">${g.label}</span>
      ${g.options.map(o => chipHtml(g.key, o)).join('')}
    </div>`).join('');

  container.querySelectorAll('.filter-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.dataset.group;
      const val = btn.dataset.val;
      const current = state[group] || [];
      if (current.includes(val)) {
        state[group] = current.filter(v => v !== val);
      } else {
        state[group] = [...current, val];
      }
      setState(state);
      btn.classList.toggle('filter-chip--active');
      onChange(state);
    });
  });
}
