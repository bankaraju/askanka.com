const BASE = '/api';

export async function get(path) {
  // cache:'no-store' on every call — chart/freshness endpoints were silently
  // serving 2-week-stale responses out of the HTTP cache because FastAPI
  // emits no validators by default. no-store is correct for a per-request
  // research terminal where every page has a "what's the latest" assumption.
  const resp = await fetch(`${BASE}${path}`, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`API ${path}: ${resp.status}`);
  return resp.json();
}

export async function getHealth() { return get('/health'); }
export async function getRegime() { return get('/regime'); }
export async function getSignals() { return get('/signals'); }
export async function getSpreads() { return get('/spreads'); }
export async function getTrustScores() { return get('/trust-scores'); }
export async function getTrackRecord() { return get('/track-record'); }
export async function getNewsMacro() { return get('/news/macro'); }
export async function getChart(ticker) { return get(`/charts/${ticker}`); }
export async function getTickerNarrative(ticker) { return get(`/ticker/${ticker}/narrative`); }
export async function getTA(ticker) { return get(`/ta/${ticker}`); }
export async function getNewsStock(ticker) { return get(`/news/${ticker}`); }
export async function getRiskGates() { return get('/risk-gates'); }
export async function getDigest() { return get('/research/digest'); }
export async function getOptionsShadow() { return get('/research/options-shadow'); }
