"""Node-driven tests for lay_language.js (#91 lay-language mandate).

Tests modelEdgePhrases() — translates walk-forward stats into readable
phrases. Validates the band thresholds and graceful handling of nulls.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = REPO_ROOT / "pipeline/terminal/static/js/components/analysis/lay_language.js"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")
    return node


def _run_harness(body: str) -> dict:
    script = _PRELUDE + "\n" + body
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, dir=str(REPO_ROOT)) as f:
        f.write(script)
        temp_path = f.name
    try:
        proc = subprocess.run(
            [_node(), temp_path],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"Node harness failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise AssertionError(f"no JSON in harness stdout:\n{proc.stdout}")


_PRELUDE = r"""
import { pathToFileURL } from 'node:url';
const modUrl = pathToFileURL(process.cwd() + '/pipeline/terminal/static/js/components/analysis/lay_language.js').href;
globalThis.lay = await import(modUrl);
"""


def test_strong_edge_with_robust_quarters():
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: 0.62, min_fold_auc: 0.55, n_folds: 6 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == [
        "strong edge",
        "edge held every quarter",
        "6 quarters tested",
    ]


def test_decent_edge_with_weak_worst_quarter():
    # mean_auc=0.57 → "decent edge", min_fold=0.36 → "lost money in some quarters"
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: 0.57, min_fold_auc: 0.36, n_folds: 6 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == [
        "decent edge",
        "lost money in some quarters",
        "6 quarters tested",
    ]


def test_modest_edge_borderline_quarter():
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: 0.53, min_fold_auc: 0.46 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == ["modest edge", "weak quarters present"]


def test_barely_beats_random():
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: 0.51, min_fold_auc: 0.50 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == ["barely beats coin flip", "edge held every quarter"]


def test_negative_edge():
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: 0.48, min_fold_auc: 0.42, n_folds: 4 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == [
        "edge negative",
        "lost money in some quarters",
        "4 quarters tested",
    ]


def test_handles_missing_fields():
    result = _run_harness(r"""
const out1 = lay.modelEdgePhrases({});
const out2 = lay.modelEdgePhrases();
const out3 = lay.modelEdgePhrases({ n_folds: 4 });
console.log(JSON.stringify({ a: out1, b: out2, c: out3 }));
""")
    assert result["a"] == []
    assert result["b"] == []
    # n_folds alone isn't enough — without an edge stat we'd be lying about
    # quarterly sample, but the module still emits the count line.
    assert result["c"] == ["4 quarters tested"]


def test_ignores_non_finite_inputs():
    result = _run_harness(r"""
const out = lay.modelEdgePhrases({ mean_auc: Infinity, min_fold_auc: NaN, n_folds: -3 });
console.log(JSON.stringify({ phrases: out }));
""")
    assert result["phrases"] == []


def test_syntax_smoke():
    proc = subprocess.run(
        [_node(), "--check", str(COMPONENT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"syntax error: {proc.stderr}"
