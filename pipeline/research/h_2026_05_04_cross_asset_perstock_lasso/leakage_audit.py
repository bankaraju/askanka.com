"""Section 16.6 amplified leakage audit. Triggers when n_qualifying in [26,80].

Three diagnostic rebuilds:
  A. Label-shift permutation control (shuffle labels within each (stock, fold))
  B. Date-shift PIT control (extra +1 IST trading day shift on ETF block)
  C. Feature-block ablation (zero out ETF PCs, fit TA-only)

Writes leakage_audit.json with three n_qualifying counts; verdict module reads it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def run_audit_a_label_permutation() -> int:
    """Re-fit with labels shuffled within each (stock, fold). Expected: ~5% pass under null."""
    # Implementation: import runner.main, monkey-patch label generator with permutation
    import importlib
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    rng = np.random.default_rng(0)
    orig_label = r._label

    def shuffled_label(bars, threshold_pct):
        y_long, y_short = orig_label(bars, threshold_pct)
        return pd.Series(rng.permutation(y_long.values), index=y_long.index), \
               pd.Series(rng.permutation(y_short.values), index=y_short.index)

    r._label = shuffled_label
    # Write to a separate manifest
    audit_dir = OUT_DIR / "audit_a_label_perm"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        r._label = orig_label
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def run_audit_b_date_shift() -> int:
    """Re-fit with ETF block additionally shifted by +1 IST trading day (forward leakage)."""
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    from pipeline.autoresearch import etf_v3_loader
    orig_build = etf_v3_loader.build_panel

    def shifted_build(*, t1_anchor=True):
        panel = orig_build(t1_anchor=t1_anchor)
        # Additional +1 forward shift introduces look-ahead
        return panel.shift(-1)

    etf_v3_loader.build_panel = shifted_build
    audit_dir = OUT_DIR / "audit_b_date_shift"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        etf_v3_loader.build_panel = orig_build
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def run_audit_c_ablation() -> int:
    """Re-fit with ETF block zeroed (TA + IND macro + DOW only)."""
    # The cleanest implementation is to patch apply_pca to return zeros
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model as p
    import pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner as r
    orig_apply = p.apply_pca

    def zero_pca(X, model):
        z = orig_apply(X, model)
        return pd.DataFrame(np.zeros_like(z.values), index=z.index, columns=z.columns)

    p.apply_pca = zero_pca
    r.apply_pca = zero_pca  # runner imported it directly
    audit_dir = OUT_DIR / "audit_c_ablation"
    audit_dir.mkdir(parents=True, exist_ok=True)
    orig_out = r.OUT_DIR
    r.OUT_DIR = audit_dir
    try:
        r.main(pd.Timestamp("2025-10-31"))
    finally:
        r.OUT_DIR = orig_out
        p.apply_pca = orig_apply
        r.apply_pca = orig_apply
    manifest = json.loads((audit_dir / "manifest.json").read_text())
    return manifest["n_qualifying"]


def main() -> int:
    manifest = json.loads((OUT_DIR / "manifest.json").read_text())
    n_qual = manifest["n_qualifying"]
    n_cells = manifest["n_cells_fit"]

    print(f"[leakage_audit] base n_qualifying={n_qual}, n_cells_fit={n_cells}")
    n_a = run_audit_a_label_permutation()
    n_b = run_audit_b_date_shift()
    n_c = run_audit_c_ablation()

    out = {
        "base_n_qualifying": n_qual,
        "n_cells_fit": n_cells,
        "audit_a_label_perm": n_a,
        "audit_b_date_shift": n_b,
        "audit_c_ablation": n_c,
        "audit_a_pass": n_a <= 30,                    # spec section 16.6.A
        "audit_b_pass": n_b <= n_qual,                # spec section 16.6.B
        "audit_c_pass_no_redundancy": (n_c < 0.5 * n_qual),  # spec section 16.6.C: TA-only should be much smaller
    }
    (OUT_DIR / "leakage_audit.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    return 0 if all([out["audit_a_pass"], out["audit_b_pass"], out["audit_c_pass_no_redundancy"]]) else 1


if __name__ == "__main__":
    sys.exit(main())
