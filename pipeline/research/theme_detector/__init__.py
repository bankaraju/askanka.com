"""Theme Detector v1 — infrastructure layer.

NOT a hypothesis. NOT a trading rule. Output (`themes_<date>.json`) is
consumed as a frozen input by downstream hypotheses.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md
Audit: docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md
"""

DETECTOR_VERSION = "v1.0.2"
# v1.0.1 (2026-05-02): C5 earnings_breadth canonical-first
#   — Net Profit Surprise Qtr % from Trendlyne results_dashboard preferred,
#     proxy (Net Profit QoQ Growth %) used as fallback.
# v1.0.2 (2026-05-02): C2 cap_drift canonical-first
#   — 6-month delta in summed NIFTY-500 weight from reconstructed history
#     (anchored to today's NSE snapshot, walked back via close ratio × ffmc;
#     covers ~89.97% of canonical weight). Falls back to v1 rel-ret quarter
#     proxy when reconstruction lacks coverage or lookback.
