# pipeline/tests/autoresearch/overshoot_compliance/test_package.py
import importlib


def test_package_imports():
    mod = importlib.import_module("pipeline.autoresearch.overshoot_compliance")
    assert mod.__version__ == "0.1.0"
    assert mod.HYPOTHESIS_ID == "H-2026-04-23-001"


def test_runner_main_is_callable():
    from pipeline.autoresearch.overshoot_compliance import runner
    assert callable(runner.main)
