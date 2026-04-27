from pipeline.pattern_scanner import constants as C


def test_pattern_set_has_exactly_12():
    assert len(C.PATTERNS) == 12


def test_balanced_directions():
    longs = [p for p in C.PATTERNS if p.direction == "LONG"]
    shorts = [p for p in C.PATTERNS if p.direction == "SHORT"]
    assert len(longs) == 6
    assert len(shorts) == 6


def test_pattern_ids_unique():
    ids = [p.pattern_id for p in C.PATTERNS]
    assert len(ids) == len(set(ids))


def test_thresholds():
    assert C.WIN_THRESHOLD == 0.008
    assert C.MIN_N == 30
    assert C.MIN_FOLD_STABILITY == 0.5
    assert C.TOP_N == 10


def test_specific_patterns_present():
    ids = {p.pattern_id for p in C.PATTERNS}
    expected = {
        "BULLISH_HAMMER", "BULLISH_ENGULFING", "MORNING_STAR", "PIERCING_LINE",
        "SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR", "DARK_CLOUD_COVER",
        "BB_BREAKOUT", "BB_BREAKDOWN", "MACD_BULL_CROSS", "MACD_BEAR_CROSS",
    }
    assert ids == expected
