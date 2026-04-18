"""Tests for the Anka Terminal CLI entry point."""
import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.terminal", "--help"],
        capture_output=True, text=True, cwd="C:\\Users\\Claude_Anka\\askanka.com",
    )
    assert result.returncode == 0
    assert "Anka Terminal" in result.stdout


def test_cli_default_port():
    from pipeline.terminal.cli import parse_args
    args = parse_args([])
    assert args.port == 8501


def test_cli_custom_port():
    from pipeline.terminal.cli import parse_args
    args = parse_args(["--port", "9000"])
    assert args.port == 9000


def test_cli_no_open_flag():
    from pipeline.terminal.cli import parse_args
    args = parse_args(["--no-open"])
    assert args.no_open is True
