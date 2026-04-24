"""Hook refuses new strategy file without registry entry; allows with one."""
from __future__ import annotations

import subprocess
from pathlib import Path

HOOK = Path("pipeline/scripts/hooks/pre-commit-strategy-gate.sh")
REGISTRY = Path("docs/superpowers/hypothesis-registry.jsonl")


def test_hook_script_exists():
    assert HOOK.exists(), f"missing: {HOOK}"


def test_hook_refuses_without_registry():
    """HOOK_TEST_MODE=refuse forces the early-exit refusal branch."""
    import os
    env = {**os.environ, "HOOK_TEST_MODE": "refuse"}
    result = subprocess.run(["bash", str(HOOK)], capture_output=True, env=env)
    assert result.returncode != 0
    assert b"registry" in result.stderr


def test_hook_allows_with_registry():
    """HOOK_TEST_MODE=allow forces the early-exit allow branch."""
    import os
    env = {**os.environ, "HOOK_TEST_MODE": "allow"}
    result = subprocess.run(["bash", str(HOOK)], capture_output=True, env=env)
    assert result.returncode == 0
