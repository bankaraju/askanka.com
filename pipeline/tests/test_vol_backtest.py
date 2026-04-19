"""
Tests for pipeline/vol_backtest.py — retrospective vol model validation.

Run: pytest pipeline/tests/test_vol_backtest.py -v
"""
import csv
import tempfile
from pathlib import Path


def _write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Date", "Close", "High", "Low", "Open", "Volume"])
        w.writeheader()
        w.writerows(rows)


def _make_prices(base=100.0, n=60, daily_pct=0.01):
    import random
    random.seed(42)
    rows = []
    price = base
    for i in range(n):
        move = price * daily_pct * random.choice([1, -1])
        new_price = price + move
        rows.append({
            "Date": f"2026-01-{i+1:02d}",
            "Close": round(new_price, 4),
            "High": round(max(price, new_price) * 1.001, 4),
            "Low": round(min(price, new_price) * 0.999, 4),
            "Open": round(price, 4),
            "Volume": 100000,
        })
        price = new_price
    return rows


class TestBacktestSingleStock:
    def test_returns_observations(self):
        from pipeline.vol_backtest import backtest_single_stock
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "TEST.csv"
            _write_csv(csv_path, _make_prices(n=60))
            result = backtest_single_stock(csv_path)
            assert result["ticker"] == "TEST"
            assert result["observations"] > 0
            assert "mape_pct" in result
            assert "hit_rate" in result
            assert "vol_scalar" in result

    def test_no_lookahead(self):
        from pipeline.vol_backtest import backtest_single_stock
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "TEST.csv"
            _write_csv(csv_path, _make_prices(n=60))
            result = backtest_single_stock(csv_path)
            for sample in result.get("daily_samples", []):
                assert "date" in sample
                assert "expected_move_pct" in sample
                assert "actual_move_pct" in sample
                assert sample["expected_move_pct"] > 0
                assert sample["actual_move_pct"] >= 0

    def test_too_few_rows_returns_empty(self):
        from pipeline.vol_backtest import backtest_single_stock
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "TINY.csv"
            _write_csv(csv_path, _make_prices(n=10))
            result = backtest_single_stock(csv_path)
            assert result["observations"] == 0

    def test_constant_prices_zero_expected_move(self):
        from pipeline.vol_backtest import backtest_single_stock
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "FLAT.csv"
            rows = [{"Date": f"2026-01-{i+1:02d}", "Close": 100.0,
                      "High": 100.0, "Low": 100.0, "Open": 100.0, "Volume": 0}
                    for i in range(60)]
            _write_csv(csv_path, rows)
            result = backtest_single_stock(csv_path)
            for s in result.get("daily_samples", []):
                assert s["expected_move_pct"] < 0.01


class TestRunFullBacktest:
    def test_aggregate_metrics(self):
        from pipeline.vol_backtest import run_full_backtest
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td)
            for ticker in ["AAA", "BBB", "CCC"]:
                _write_csv(cache_dir / f"{ticker}.csv", _make_prices(n=60))
            result = run_full_backtest(cache_dir)
            assert result["stocks_tested"] == 3
            assert result["total_observations"] > 0
            assert "aggregate" in result
            agg = result["aggregate"]
            assert "mape_pct" in agg
            assert "sigma_band_hit_rate" in agg
            assert "vol_scalar" in agg
            assert 0.0 < agg["sigma_band_hit_rate"] < 1.0
            assert agg["vol_scalar"] is not None
            assert 0.1 < agg["vol_scalar"] < 5.0

    def test_per_stock_present(self):
        from pipeline.vol_backtest import run_full_backtest
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td)
            for ticker in ["XX", "YY"]:
                _write_csv(cache_dir / f"{ticker}.csv", _make_prices(n=60))
            result = run_full_backtest(cache_dir)
            tickers = [s["ticker"] for s in result["per_stock"]]
            assert "XX" in tickers
            assert "YY" in tickers

    def test_empty_dir(self):
        from pipeline.vol_backtest import run_full_backtest
        with tempfile.TemporaryDirectory() as td:
            result = run_full_backtest(Path(td))
            assert result["stocks_tested"] == 0
            assert result["total_observations"] == 0
