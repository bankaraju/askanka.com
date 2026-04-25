"""Orchestrate the SP1 audit end to end. Idempotent — bar fetches are cached."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_shape_audit import (
    constants as C,
    fetcher,
    features,
    report,
    roster,
    simulator,
)

log = logging.getLogger("phase_c_shape_audit")


def _enrich_with_features_and_cf(
    roster_df: pd.DataFrame,
    bars_dir: Path,
) -> pd.DataFrame:
    rows_out: list[dict] = []
    for _, r in roster_df.iterrows():
        ticker = r["ticker"]
        trade_date = r["date"].date() if hasattr(r["date"], "date") else r["date"]
        record: dict = r.to_dict()

        try:
            bars = fetcher.fetch_minute_bars(
                ticker=ticker,
                trade_date=trade_date,
                bars_dir=bars_dir,
            )
        except Exception as exc:
            log.warning("Bar fetch failed for %s %s: %s", ticker, trade_date, exc)
            record["validation"] = "FETCH_FAILED"
            record["shape"] = "INVALID"
            record["cf_grid_avg_pnl_pct"] = np.nan
            record["cf_grid_avg_win"] = False
            record["cf_best_grid_pnl_pct"] = np.nan
            rows_out.append(record)
            continue

        feats = features.compute_shape_features(bars)
        record.update({k: v for k, v in feats.items() if k != "validation"})
        record["validation"] = feats["validation"]
        record["shape"] = features.classify_shape(feats)

        side = r.get("trade_rec")
        if feats["validation"] == "OK" and side in ("LONG", "SHORT"):
            grid = simulator.simulate_grid(bars=bars, side=side, entry_grid=C.ENTRY_GRID)
            cf_pnls: list[float] = []
            for key, leg in grid.items():
                record[f"cf_entry_{key.replace(':','')}_pnl_pct"] = leg["pnl_pct"]
                record[f"cf_entry_{key.replace(':','')}_exit_reason"] = leg["exit_reason"]
                record[f"cf_entry_{key.replace(':','')}_exit_minute"] = leg["exit_minute"]
                if leg["exit_reason"] != "NO_ENTRY":
                    cf_pnls.append(leg["pnl_pct"])
            if cf_pnls:
                record["cf_grid_avg_pnl_pct"] = float(np.mean(cf_pnls))
                record["cf_grid_avg_win"] = record["cf_grid_avg_pnl_pct"] > 0
                record["cf_best_grid_pnl_pct"] = float(np.max(cf_pnls))
            else:
                record["cf_grid_avg_pnl_pct"] = np.nan
                record["cf_grid_avg_win"] = False
                record["cf_best_grid_pnl_pct"] = np.nan
        else:
            record["cf_grid_avg_pnl_pct"] = np.nan
            record["cf_grid_avg_win"] = False
            record["cf_best_grid_pnl_pct"] = np.nan
        rows_out.append(record)
    return pd.DataFrame(rows_out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase C intraday shape audit (SP1)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="Window end date YYYY-MM-DD (default: today IST)")
    parser.add_argument("--days", type=int, default=C.WINDOW_DAYS,
                        help="Window length in calendar days")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit roster to first N rows (debugging)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    end_date = pd.Timestamp(args.end_date) if args.end_date else pd.Timestamp.now(tz=C.IST).normalize().tz_localize(None)
    start_date = end_date - pd.Timedelta(days=args.days)
    log.info("Window: %s -> %s", start_date.date(), end_date.date())

    roster_df = roster.build_roster(window_start=start_date, window_end=end_date)
    log.info("Roster: %d rows (actual=%d, missed=%d)",
             len(roster_df),
             int((roster_df["source"] == "actual").sum()),
             int((roster_df["source"] == "missed").sum()))

    if args.limit:
        roster_df = roster_df.head(args.limit)

    enriched = _enrich_with_features_and_cf(roster_df, bars_dir=C.BARS_DIR)

    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(C.TRADES_CSV, index=False)
    log.info("Wrote %s (%d rows)", C.TRADES_CSV, len(enriched))

    missed = enriched[enriched["source"] == "missed"]
    missed.to_csv(C.MISSED_CSV, index=False)
    log.info("Wrote %s (%d rows)", C.MISSED_CSV, len(missed))

    rep = report.build_report(enriched)
    body = report.render_markdown(rep, window_start=start_date, window_end=end_date)
    C.REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    C.REPORT_MD.write_text(body, encoding="utf-8")
    log.info("Wrote %s", C.REPORT_MD)
    log.info("Verdict: %s", rep["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
