"""Grep-style smoke tests for Phase C Paired Shadow JS component.

Mirrors the pattern from test_scanner_pattern_js.py.
"""
from pathlib import Path

COMPONENT_PATH = Path(
    "pipeline/terminal/static/js/components/phase-c-paired-shadow.js"
)
OPTIONS_JS_PATH = Path("pipeline/terminal/static/js/pages/options.js")


def test_component_file_exists():
    """The component module exists at the expected path."""
    assert COMPONENT_PATH.exists(), (
        f"Missing: {COMPONENT_PATH} -- phase-c-paired-shadow.js was not created"
    )


def test_component_exports_render_function():
    """Component exports renderPhaseCPairedShadowCard."""
    text = COMPONENT_PATH.read_text(encoding="utf-8")
    assert "export function renderPhaseCPairedShadowCard" in text


def test_component_references_endpoint():
    """Component contains the literal endpoint path (at least in a comment)."""
    text = COMPONENT_PATH.read_text(encoding="utf-8")
    assert "phase-c-options-shadow" in text


def test_options_js_imports_component():
    """options.js imports the new component."""
    text = OPTIONS_JS_PATH.read_text(encoding="utf-8")
    assert "phase-c-paired-shadow" in text
    assert "renderPhaseCPairedShadowCard" in text


def test_options_js_fetches_endpoint():
    """options.js Promise.all block fetches the new endpoint."""
    text = OPTIONS_JS_PATH.read_text(encoding="utf-8")
    assert "/research/phase-c-options-shadow" in text
