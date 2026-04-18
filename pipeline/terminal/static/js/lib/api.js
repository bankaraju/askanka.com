const BASE = '/api';

export async function get(path) {
  const resp = await fetch(`${BASE}${path}`);
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
export async function getTA(ticker) { return get(`/ta/${ticker}`); }
export async function getNewsStock(ticker) { return get(`/news/${ticker}`); }
export async function getRiskGates() { return get('/risk-gates'); }
export async function getDigest() { return get('/research/digest'); }
