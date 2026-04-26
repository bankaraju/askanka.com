"""CLI to identify missing tickers and write tickers_added.csv."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.missing_tickers import (
    compute_missing,
    list_canonical_fno_tickers,
    list_replay_tickers,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Identify F&O tickers missing from replay")
    parser.add_argument("--canon", default="pipeline/data/canonical_fno_research_v3.json")
    parser.add_argument("--replay", default="pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet")
    parser.add_argument("--out", default="pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv")
    args = parser.parse_args()

    canon = list_canonical_fno_tickers(Path(args.canon))
    replay = list_replay_tickers(Path(args.replay))
    missing = compute_missing(canon, replay)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": missing}).to_csv(out_path, index=False)

    print(f"canonical: {len(canon)} tickers")
    print(f"replay:    {len(replay)} tickers")
    print(f"missing:   {len(missing)} tickers")
    print(f"wrote:     {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
