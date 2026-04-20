// URL-encoded filter chips. State is read from window.location.hash query string
// (after #) so filtered views are deep-linkable. onChange fires after each toggle.
//
// Usage:
//   render(container, {
//     groups: [
//       { key: 'source', label: 'Source', options: ['static_config', 'regime_engine'] },
//       { key: 'conviction', label: 'Conviction', options: ['HIGH', 'MEDIUM', 'LOW'] },
//     ],
//   }, onChange, 'trading');
//
// State helper:
//   getState('trading') → { source: ['static_config'], conviction: ['HIGH'] }
//
// Namespace: each page passes a namespace string (e.g. 'trading', 'scanner').
// Hash keys are stored as `namespace.key=value` so multiple pages can coexist
// in the same URL hash without colliding. Keys belonging to OTHER namespaces
// are preserved when one page writes its own state.

function _esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

export function getState(namespace = '') {
  const prefix = namespace ? `${namespace}.` : '';
  const hash = window.location.hash.slice(1);
  if (!hash) return {};
  const params = new URLSearchParams(hash);
  const out = {};
  for (const [k, v] of params.entries()) {
    if (prefix && !k.startsWith(prefix)) continue;
    const bareKey = prefix ? k.slice(prefix.length) : k;
    out[bareKey] = v ? v.split(',').filter(Boolean) : [];
  }
  return out;
}

function setState(state, namespace = '') {
  const prefix = namespace ? `${namespace}.` : '';
  // Read current hash and preserve keys belonging to OTHER namespaces.
  const hash = window.location.hash.slice(1);
  const params = new URLSearchParams(hash);

  // Remove all keys belonging to this namespace.
  for (const k of [...params.keys()]) {
    if (prefix ? k.startsWith(prefix) : !k.includes('.')) {
      params.delete(k);
    }
  }

  // Write this namespace's new state.
  for (const [k, v] of Object.entries(state)) {
    if (v && v.length > 0) {
      params.set(`${prefix}${k}`, v.join(','));
    }
  }

  const next = params.toString();
  const newHash = next ? `#${next}` : '';
  if (window.location.hash !== newHash) {
    history.replaceState(null, '', `${window.location.pathname}${window.location.search}${newHash}`);
  }
}

export function render(container, config, onChange, namespace = '') {
  const state = getState(namespace);
  for (const g of config.groups) {
    if (!state[g.key]) state[g.key] = [];
  }

  function chipHtml(groupKey, opt) {
    const selected = state[groupKey].includes(opt);
    return `<button class="filter-chip ${selected ? 'filter-chip--active' : ''}"
      data-group="${_esc(groupKey)}" data-val="${_esc(opt)}">${_esc(opt)}</button>`;
  }

  container.innerHTML = config.groups.map(g => `
    <div class="filter-chip-group">
      <span class="filter-chip-label">${_esc(g.label)}</span>
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
      setState({ ...state }, namespace);
      btn.classList.toggle('filter-chip--active');
      onChange({ ...state });
    });
  });
}
