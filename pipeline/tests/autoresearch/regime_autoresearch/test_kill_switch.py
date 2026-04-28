"""Hook refuses new strategy file without registry entry; allows with one."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path("pipeline/scripts/hooks/pre-commit-strategy-gate.sh")
PATTERNS = Path("pipeline/scripts/hooks/strategy_patterns.txt")
REGISTRY = Path("docs/superpowers/hypothesis-registry.jsonl")


def _provision_patterns_file(repo: Path) -> None:
    """Real-mode tests run the hook inside a fresh tmp repo. The hook reads
    the trading-rule patterns from $REPO/pipeline/scripts/hooks/strategy_patterns.txt,
    so the test repo needs the same file laid out at the same relative path."""
    dest = repo / "pipeline" / "scripts" / "hooks" / "strategy_patterns.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(PATTERNS.resolve().read_bytes())


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


def _clean_env() -> dict:
    """Minimal env for invoking bash/git without HOOK_TEST_MODE leaking in."""
    import os
    keep = ("PATH", "SYSTEMROOT", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
            "HOME", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "PATHEXT",
            "COMSPEC", "WINDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    # Disable any global git hooks/config that might interfere
    env["GIT_CONFIG_GLOBAL"] = str(Path(env.get("TEMP", ".")) / "nonexistent_gitconfig")
    env["GIT_CONFIG_SYSTEM"] = str(Path(env.get("TEMP", ".")) / "nonexistent_gitconfig")
    return env


def test_hook_refuses_real_staged_strategy_file_without_registry(tmp_path):
    """Real-mode scanner: stage a *_strategy.py without registry → refuse."""
    if shutil.which("bash") is None:
        pytest.skip("requires bash")

    env = _clean_env()
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, env=env, check=True)

    (repo / "foo_strategy.py").write_text("# fake strategy\n", encoding="utf-8")
    subprocess.run(["git", "add", "foo_strategy.py"], cwd=repo, env=env, check=True)

    hook_copy = repo / "pre-commit-strategy-gate.sh"
    hook_copy.write_bytes(HOOK.resolve().read_bytes())
    _provision_patterns_file(repo)

    result = subprocess.run(
        ["bash", str(hook_copy)],
        cwd=repo,
        env=env,
        capture_output=True,
    )
    assert result.returncode != 0, f"expected refusal, got rc=0; stderr={result.stderr!r}"
    assert b"registry" in result.stderr.lower() or b"hypothesis-registry" in result.stderr


def test_hook_allows_real_staged_strategy_file_with_registry(tmp_path):
    """Real-mode scanner: stage *_strategy.py + registry entry → allow."""
    if shutil.which("bash") is None:
        pytest.skip("requires bash")

    env = _clean_env()
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, env=env, check=True)

    (repo / "foo_strategy.py").write_text("# fake strategy\n", encoding="utf-8")
    reg_path = repo / "docs" / "superpowers" / "hypothesis-registry.jsonl"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text('{"id": "H-TEST-001"}\n', encoding="utf-8")

    subprocess.run(["git", "add", "foo_strategy.py", str(reg_path)],
                   cwd=repo, env=env, check=True)

    hook_copy = repo / "pre-commit-strategy-gate.sh"
    hook_copy.write_bytes(HOOK.resolve().read_bytes())
    _provision_patterns_file(repo)

    result = subprocess.run(
        ["bash", str(hook_copy)],
        cwd=repo,
        env=env,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"expected allow, got rc={result.returncode}; "
        f"stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
