"""
Tests for pipeline/oi_scanner.py — OI Scanner: PCR, anomaly detection.

Run:
    cd C:/Users/Claude_Anka/askanka.com/pipeline
    python -m pytest tests/test_oi_scanner.py -v
"""

import sys
from pathlib import Path

# Ensure pipeline/ is on the path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from oi_scanner import compute_pcr, classify_pcr, detect_oi_anomaly


# ─────────────────────────────────────────────────────────────────────────────
# compute_pcr
# ─────────────────────────────────────────────────────────────────────────────

def test_pcr_basic():
    """120000 puts / 100000 calls = 1.2"""
    result = compute_pcr(120000, 100000)
    assert abs(result - 1.2) < 1e-9, f"Expected 1.2, got {result}"


def test_pcr_zero_calls():
    """Zero call OI → return 0, no division error."""
    result = compute_pcr(50000, 0)
    assert result == 0, f"Expected 0 when call_oi=0, got {result}"


def test_pcr_zero_puts():
    """Zero put OI → ratio is 0.0"""
    result = compute_pcr(0, 100000)
    assert result == 0.0, f"Expected 0.0 when put_oi=0, got {result}"


def test_pcr_equal():
    """Equal puts and calls → PCR = 1.0"""
    result = compute_pcr(75000, 75000)
    assert abs(result - 1.0) < 1e-9, f"Expected 1.0 for equal OI, got {result}"


def test_pcr_high_put_skew():
    """Heavy put side → PCR > 1 (bullish per convention)"""
    result = compute_pcr(200000, 100000)
    assert abs(result - 2.0) < 1e-9, f"Expected 2.0, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# classify_pcr
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_pcr_bullish():
    """PCR > 1.3 → BULLISH"""
    assert classify_pcr(1.5) == "BULLISH"
    assert classify_pcr(1.31) == "BULLISH"


def test_classify_pcr_mild_bull():
    """PCR in (1.0, 1.3] → MILD_BULL"""
    assert classify_pcr(1.1) == "MILD_BULL"
    assert classify_pcr(1.0001) == "MILD_BULL"
    assert classify_pcr(1.3) == "MILD_BULL"


def test_classify_pcr_neutral():
    """PCR in (0.7, 1.0] → NEUTRAL"""
    assert classify_pcr(0.8) == "NEUTRAL"
    assert classify_pcr(1.0) == "NEUTRAL"
    assert classify_pcr(0.71) == "NEUTRAL"


def test_classify_pcr_mild_bear():
    """PCR in (0.5, 0.7] → MILD_BEAR"""
    assert classify_pcr(0.6) == "MILD_BEAR"
    assert classify_pcr(0.51) == "MILD_BEAR"
    assert classify_pcr(0.7) == "MILD_BEAR"


def test_classify_pcr_bearish():
    """PCR <= 0.5 → BEARISH"""
    assert classify_pcr(0.5) == "BEARISH"
    assert classify_pcr(0.3) == "BEARISH"
    assert classify_pcr(0.0) == "BEARISH"


def test_classify_pcr_all_five_classes():
    """Verify all 5 classifications are reachable."""
    classes = {
        classify_pcr(0.2),   # BEARISH
        classify_pcr(0.6),   # MILD_BEAR
        classify_pcr(0.85),  # NEUTRAL
        classify_pcr(1.2),   # MILD_BULL
        classify_pcr(1.5),   # BULLISH
    }
    assert classes == {"BEARISH", "MILD_BEAR", "NEUTRAL", "MILD_BULL", "BULLISH"}


# ─────────────────────────────────────────────────────────────────────────────
# detect_oi_anomaly
# ─────────────────────────────────────────────────────────────────────────────

def test_detect_oi_anomaly_spike_detected():
    """OI change is 3x average → anomaly = True"""
    assert detect_oi_anomaly(300_000, 100_000) is True


def test_detect_oi_anomaly_normal_not_detected():
    """OI change is 1.5x average (below 2x threshold) → anomaly = False"""
    assert detect_oi_anomaly(150_000, 100_000) is False


def test_detect_oi_anomaly_exactly_2x():
    """OI change exactly 2x average → NOT an anomaly (strictly greater)"""
    assert detect_oi_anomaly(200_000, 100_000) is False


def test_detect_oi_anomaly_zero_avg():
    """avg_daily_change <= 0 → return False (guard against divide-by-zero)"""
    assert detect_oi_anomaly(999_999, 0) is False
    assert detect_oi_anomaly(999_999, -1) is False


def test_detect_oi_anomaly_negative_oi_change():
    """Negative OI change (large unwinding) also triggers anomaly via abs()"""
    assert detect_oi_anomaly(-300_000, 100_000) is True


def test_detect_oi_anomaly_small_spike():
    """Small absolute change even if > 2x still detected"""
    assert detect_oi_anomaly(3, 1) is True


def test_detect_oi_anomaly_zero_change():
    """Zero OI change → no anomaly regardless of average"""
    assert detect_oi_anomaly(0, 100_000) is False
