"""
Tests for pipeline/technical_scanner.py
"""

import sys
from pathlib import Path

# Ensure pipeline directory is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from technical_scanner import compute_rsi, classify_signal


# ---------------------------------------------------------------------------
# compute_rsi tests
# ---------------------------------------------------------------------------

def test_rsi_all_gains():
    """15 strictly increasing closes → RSI should be > 95 (near 100)."""
    closes = [100.0 + i for i in range(16)]  # 16 prices = 15 changes, all gains
    rsi = compute_rsi(closes, period=14)
    assert rsi > 95, f"Expected RSI > 95 for all-gains, got {rsi}"


def test_rsi_all_losses():
    """15 strictly decreasing closes → RSI should be < 5 (near 0)."""
    closes = [100.0 - i for i in range(16)]  # 16 prices = 15 changes, all losses
    rsi = compute_rsi(closes, period=14)
    assert rsi < 5, f"Expected RSI < 5 for all-losses, got {rsi}"


def test_rsi_mixed():
    """Mixed up/down closes → RSI between 30 and 70."""
    closes = [100, 102, 101, 103, 102, 104, 103, 101, 102, 100, 101, 103, 102, 104, 103, 102]
    rsi = compute_rsi(closes, period=14)
    assert 30 <= rsi <= 70, f"Expected RSI between 30-70 for mixed, got {rsi}"


def test_rsi_insufficient_data():
    """Fewer than period+1 closes → returns 50.0."""
    closes = [100, 101, 102]  # only 3 prices, period=14 needs 15
    rsi = compute_rsi(closes, period=14)
    assert rsi == 50.0, f"Expected 50.0 for insufficient data, got {rsi}"


def test_rsi_exact_boundary():
    """Exactly period+1 closes should compute (not return 50.0)."""
    closes = [100.0 + i for i in range(15)]  # 15 prices = 14 changes, all gains
    rsi = compute_rsi(closes, period=14)
    assert rsi != 50.0, f"Expected actual RSI at boundary, got 50.0"
    assert rsi > 90, f"Expected high RSI for all-gains at boundary, got {rsi}"


# ---------------------------------------------------------------------------
# classify_signal tests
# ---------------------------------------------------------------------------

def test_classify_overbought():
    """RSI > 70 and vs_20dma > 3 → OVERBOUGHT."""
    signal = classify_signal(rsi=75.0, vs_20dma=5.0, trend_5d=1.0)
    assert signal == "OVERBOUGHT", f"Expected OVERBOUGHT, got {signal}"


def test_classify_oversold():
    """RSI < 30 and vs_20dma < -3 → OVERSOLD."""
    signal = classify_signal(rsi=25.0, vs_20dma=-5.0, trend_5d=-1.0)
    assert signal == "OVERSOLD", f"Expected OVERSOLD, got {signal}"


def test_classify_bullish():
    """RSI > 60 and trend_5d > 2 → BULLISH."""
    signal = classify_signal(rsi=65.0, vs_20dma=2.0, trend_5d=3.0)
    assert signal == "BULLISH", f"Expected BULLISH, got {signal}"


def test_classify_bearish():
    """RSI < 40 and trend_5d < -2 → BEARISH."""
    signal = classify_signal(rsi=35.0, vs_20dma=-1.0, trend_5d=-3.0)
    assert signal == "BEARISH", f"Expected BEARISH, got {signal}"


def test_classify_neutral():
    """Mid-range RSI/DMA/trend → NEUTRAL."""
    signal = classify_signal(rsi=50.0, vs_20dma=1.0, trend_5d=0.5)
    assert signal == "NEUTRAL", f"Expected NEUTRAL, got {signal}"


def test_classify_overbought_takes_priority_over_bullish():
    """RSI > 70 + vs_20dma > 3 + trend_5d > 2 → OVERBOUGHT (checked first)."""
    signal = classify_signal(rsi=80.0, vs_20dma=5.0, trend_5d=3.0)
    assert signal == "OVERBOUGHT", f"Expected OVERBOUGHT to take priority, got {signal}"


def test_classify_oversold_takes_priority_over_bearish():
    """RSI < 30 + vs_20dma < -3 + trend_5d < -2 → OVERSOLD (checked first)."""
    signal = classify_signal(rsi=20.0, vs_20dma=-5.0, trend_5d=-3.0)
    assert signal == "OVERSOLD", f"Expected OVERSOLD to take priority, got {signal}"


def test_classify_boundary_rsi_70_exact():
    """RSI exactly 70 is NOT > 70, so not OVERBOUGHT."""
    signal = classify_signal(rsi=70.0, vs_20dma=5.0, trend_5d=1.0)
    assert signal != "OVERBOUGHT", f"RSI=70 should NOT be OVERBOUGHT (needs > 70), got {signal}"


def test_classify_boundary_rsi_30_exact():
    """RSI exactly 30 is NOT < 30, so not OVERSOLD."""
    signal = classify_signal(rsi=30.0, vs_20dma=-5.0, trend_5d=-1.0)
    assert signal != "OVERSOLD", f"RSI=30 should NOT be OVERSOLD (needs < 30), got {signal}"
