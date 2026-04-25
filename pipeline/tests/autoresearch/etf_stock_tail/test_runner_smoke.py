"""End-to-end smoke against synthetic 3-ticker panel and small permutations."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.panel import PanelInputs
from pipeline.autoresearch.etf_stock_tail.runner import run


def _mk_etf_panel(start: str, n_days: int) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="D")
    rng = np.random.default_rng(0)
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        closes = 100.0 * np.cumprod(1 + rng.normal(0, 0.005, n_days))
        for d, c in zip(dates, closes):
            rows.append({"date": d, "etf": sym, "close": float(c)})
    return pd.DataFrame(rows)


def _mk_stock_bars_with_signal(start: str, n_days: int, etf_panel: pd.DataFrame, sym_index: int):
    rng = np.random.default_rng(1 + sym_index)
    dates = pd.date_range(start, periods=n_days, freq="D")
    base = rng.normal(0, 0.012, n_days)
    # Inject ETF-driven signal: brazil_ret_1d positive → next-day spike
    brazil = etf_panel[etf_panel["etf"] == "brazil"].sort_values("date")["close"].values
    brazil_ret = np.diff(brazil) / brazil[:-1]
    for i in range(1, n_days):
        if i - 1 < len(brazil_ret) and brazil_ret[i - 1] > 0.005:
            base[i] += 0.04   # up_tail signal
        elif i - 1 < len(brazil_ret) and brazil_ret[i - 1] < -0.005:
            base[i] -= 0.04
    closes = 100.0 * np.cumprod(1 + base)
    # Use random volume so stock_volume_z_20d is non-NaN (constant volume → std=0 → NaN feature).
    volume = np.abs(rng.normal(1e6, 2e5, n_days)) + 1.0
    return pd.DataFrame({"date": dates, "close": closes, "volume": volume})


def test_runner_smoke_writes_artifacts(tmp_path: Path):
    # n_days=700 leaves ticker S1/S2 just under MIN_TAIL_EXAMPLES_PER_SIDE=30 in train window
    # (verified: n_days=900 yields min(n_up,n_down)=[39,30,35] — all pass)
    n_days = 900
    etf_panel = _mk_etf_panel("2023-01-01", n_days)
    stock_bars = {
        f"S{idx}": _mk_stock_bars_with_signal("2023-01-01", n_days, etf_panel, idx)
        for idx in range(3)
    }
    universe = {d.strftime("%Y-%m-%d"): list(stock_bars.keys())
                for d in pd.date_range("2023-01-01", periods=n_days, freq="D")}
    sector_map = {f"S{idx}": idx % 5 for idx in range(3)}
    inputs = PanelInputs(etf_panel=etf_panel, stock_bars=stock_bars,
                         universe=universe, sector_map=sector_map)

    result = run(
        inputs=inputs, out_dir=tmp_path, smoke=True,
        n_permutations=200, run_fragility=False,
    )

    assert (tmp_path / "panel_build_manifest.json").exists()
    assert (tmp_path / "gate_checklist.json").exists()
    assert (tmp_path / "verdict.md").exists()
    assert (tmp_path / "permutations.json").exists()
    assert (tmp_path / "calibration.json").exists()
    assert result["decision"] in {"PASS", "FAIL"}
