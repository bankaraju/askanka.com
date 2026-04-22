"""Test Feature Coincidence Scorer package skeleton."""


def test_package_imports():
    import pipeline.feature_scorer as fs
    assert hasattr(fs, "__version__")


def test_fit_universe_module_callable():
    from pipeline.feature_scorer import fit_universe
    assert callable(fit_universe.main)


def test_score_universe_module_callable():
    from pipeline.feature_scorer import score_universe
    assert callable(score_universe.main)
