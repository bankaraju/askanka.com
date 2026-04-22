import importlib


def test_package_imports():
    mod = importlib.import_module("pipeline.ta_scorer")
    assert mod.__version__ == "0.1.0"


def test_fit_universe_callable():
    from pipeline.ta_scorer import fit_universe
    assert callable(fit_universe.main)


def test_score_universe_callable():
    from pipeline.ta_scorer import score_universe
    assert callable(score_universe.main)
