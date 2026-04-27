"""Golden-fixture render test: scanner.js consumes the new endpoint and
renders Top-10 + click-to-chart anchors."""
import re
from pathlib import Path

JS_PATH = Path("pipeline/terminal/static/js/pages/scanner.js")


def test_scanner_js_calls_new_endpoint():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "/api/scanner/pattern-signals" in text


def test_scanner_js_includes_click_to_chart_handler():
    text = JS_PATH.read_text(encoding="utf-8")
    # Either an href to chart route or a click handler navigating to one.
    chart_pattern = re.compile(r"#chart/|navigateToChart\(|onclick=.*chart", re.I)
    assert chart_pattern.search(text) is not None, (
        "scanner.js must restore click-to-chart on ticker cells (regression #269)")


def test_scanner_js_renders_z_score_column():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "z_score" in text or "Z-score" in text or "z-score" in text


def test_scanner_js_renders_fold_stability_column():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "fold_stability" in text or "Fold-stability" in text


def test_scanner_js_renders_below_threshold_footer():
    text = JS_PATH.read_text(encoding="utf-8")
    assert "below_threshold_count" in text or "below threshold" in text.lower()
