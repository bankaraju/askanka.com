// pipeline/terminal/static/js/components/analysis/lay_language.js
// Translate walk-forward model stats into human-readable phrases.
// Backlog #91 (Track A #13 lay-language mandate). Subscribers are traders,
// not data scientists — "mean AUC 0.57 · min 0.36" reads as noise. Replace
// with phrasing that conveys edge strength + worst-quarter behaviour.

// AUC = 0.50 is random; 1.00 is perfect ranking. The bands below are
// chosen to match the FCS health bands (GREEN ≥ 0.55, AMBER ≥ 0.52).

function _edgeWord(meanAuc) {
  if (!Number.isFinite(meanAuc)) return null;
  if (meanAuc < 0.50) return 'edge negative';
  if (meanAuc < 0.52) return 'barely beats coin flip';
  if (meanAuc < 0.55) return 'modest edge';
  if (meanAuc < 0.60) return 'decent edge';
  return 'strong edge';
}

function _worstQuarterWord(minFoldAuc) {
  if (!Number.isFinite(minFoldAuc)) return null;
  if (minFoldAuc >= 0.50) return 'edge held every quarter';
  if (minFoldAuc >= 0.45) return 'weak quarters present';
  return 'lost money in some quarters';
}

// Returns a list of short, readable phrases for the health detail line.
// Replaces the old `mean AUC 0.57 · min 0.36 · 6 folds` rendering.
export function modelEdgePhrases({ mean_auc, min_fold_auc, n_folds } = {}) {
  const out = [];
  const edge = _edgeWord(mean_auc);
  if (edge) out.push(edge);
  const wq = _worstQuarterWord(min_fold_auc);
  if (wq) out.push(wq);
  if (Number.isFinite(n_folds) && n_folds > 0) {
    out.push(`${n_folds} quarters tested`);
  }
  return out;
}
