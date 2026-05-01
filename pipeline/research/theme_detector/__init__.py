"""Theme Detector v1 — infrastructure layer.

NOT a hypothesis. NOT a trading rule. Output (`themes_<date>.json`) is
consumed as a frozen input by downstream hypotheses.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md
Audit: docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md
"""

DETECTOR_VERSION = "v1.0.1"
# v1.0.1 (2026-05-02): C5 earnings_breadth canonical-first
#   — Net Profit Surprise Qtr % from Trendlyne results_dashboard preferred,
#     proxy (Net Profit QoQ Growth %) used as fallback.
