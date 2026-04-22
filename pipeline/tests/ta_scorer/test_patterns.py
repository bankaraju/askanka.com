from pipeline.ta_scorer import patterns


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def test_doji_true_for_tiny_body():
    # Body 0.05% of range
    assert patterns.is_doji(_bar(100.0, 101.0, 99.0, 100.05)) is True


def test_doji_false_for_big_body():
    assert patterns.is_doji(_bar(100.0, 101.0, 99.0, 100.8)) is False


def test_hammer_true_long_lower_shadow_small_body():
    # body top 100-100.2, lower shadow to 98, upper shadow negligible
    assert patterns.is_hammer(_bar(100.0, 100.25, 98.0, 100.2)) is True


def test_hammer_false_long_upper_shadow():
    assert patterns.is_hammer(_bar(100.0, 102.0, 99.8, 100.2)) is False


def test_shooting_star_true_long_upper_shadow():
    assert patterns.is_shooting_star(_bar(100.0, 102.5, 99.9, 100.1)) is True


def test_bullish_engulfing_true():
    prev = _bar(100.0, 100.5, 99.0, 99.2)   # red
    cur = _bar(99.0, 101.0, 98.9, 100.8)    # green, engulfs prev body
    assert patterns.is_bullish_engulfing(prev, cur) is True


def test_bullish_engulfing_false_when_not_engulfed():
    prev = _bar(100.0, 100.5, 99.0, 99.2)
    cur = _bar(99.5, 100.0, 99.3, 99.8)
    assert patterns.is_bullish_engulfing(prev, cur) is False


def test_bearish_engulfing_true():
    prev = _bar(100.0, 101.0, 99.8, 100.8)  # green
    cur = _bar(101.0, 101.2, 99.0, 99.2)    # red, engulfs prev body
    assert patterns.is_bearish_engulfing(prev, cur) is True


def test_shooting_star_false_long_lower_shadow():
    # Long lower shadow, small upper — should NOT be shooting-star
    assert patterns.is_shooting_star(_bar(100.0, 100.2, 98.0, 99.9)) is False


def test_bearish_engulfing_false_when_not_engulfed():
    prev = _bar(100.0, 101.0, 99.8, 100.8)   # green
    cur = _bar(100.9, 101.2, 100.5, 100.7)   # red, does NOT engulf prev body
    assert patterns.is_bearish_engulfing(prev, cur) is False
