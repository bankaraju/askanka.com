"""Layer-0 overnight gap predictor (live).

Applies the fitted linear model from data/gap_model.json to current yfinance
closes and outputs a predicted Nifty 50 open-gap in % with a severity
classification.

Model (fit on 4 years, 801 training rows, out-of-sample R² = 0.46):
  gap_pct = +0.09*NIKKEI + +0.16*KOSPI + -0.31*USDINR
            + -0.01*BRENT + +0.02*SPY + ~0*VIX_excess + 0.09

KOSPI and USDINR do the heavy lifting. Nikkei adds modestly. SPY and Brent
are near-noise at monthly scale. Severity thresholds are picked from the
empirical distribution of predicted gaps on the 4-year sample.

Writes: data/gap_risk.json for the morning scanner and website.
Also exposes ``predict()`` for pipeline-internal use.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PIPELINE_ROOT.parent / "data" / "gap_model.json"
OUTPUT_PATH = PIPELINE_ROOT.parent / "data" / "gap_risk.json"


DRIVERS = {
    "NIKKEI":   "^N225",
    "KOSPI":    "^KS11",
    "BRENT":    "BZ=F",
    "SPY":      "^GSPC",
    "USDINR":   "INR=X",
    "INDIAVIX": "^INDIAVIX",
}

# Severity thresholds in |predicted gap %|. Chosen so that HIGH roughly
# corresponds to the worst ~10% of predictions seen historically.
SEVERITY_LOW  = 0.35   # under this: normal night
SEVERITY_HIGH = 0.80   # above this: consider size reduction or flatten


def _latest_two_closes(symbol: str) -> Optional[tuple]:
    """Return (prev_close, latest_close) for the given yfinance symbol."""
    import yfinance as yf  # noqa: WPS433
    hist = yf.Ticker(symbol).history(period="10d")
    if hist.empty or len(hist) < 2:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-2]), float(closes.iloc[-1])


def _delta_pct(pair: Optional[tuple]) -> Optional[float]:
    if pair is None or pair[0] <= 0:
        return None
    return (pair[1] / pair[0] - 1) * 100


def predict() -> Dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"{MODEL_PATH} missing — run gap_predictor_fit.py first."
        )
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    coeffs = model["coefficients"]
    order  = model["feature_order"]

    # Fetch current driver levels
    deltas: Dict[str, Optional[float]] = {}
    for name, sym in DRIVERS.items():
        pair = _latest_two_closes(sym)
        deltas[name] = _delta_pct(pair)

    vix_level_pair = _latest_two_closes(DRIVERS["INDIAVIX"])
    vix_level = vix_level_pair[1] if vix_level_pair else None
    vix_excess = max(0.0, (vix_level or 15.0) - 15.0)

    # Assemble feature vector in model's expected order
    feat_map = {
        "NIKKEI":     deltas.get("NIKKEI"),
        "KOSPI":      deltas.get("KOSPI"),
        "BRENT":      deltas.get("BRENT"),
        "SPY":        deltas.get("SPY"),
        "USDINR":     deltas.get("USDINR"),
        "VIX_excess": vix_excess,
        "intercept":  1.0,
    }
    missing = [k for k in order if feat_map.get(k) is None]
    if missing:
        return {
            "updated_at": datetime.now().isoformat(),
            "error": f"missing features: {missing}",
            "predicted_gap_pct": None,
            "severity": "UNKNOWN",
        }

    predicted = sum(coeffs[k] * feat_map[k] for k in order)

    mag = abs(predicted)
    if mag < SEVERITY_LOW:
        severity = "LOW"
    elif mag < SEVERITY_HIGH:
        severity = "MEDIUM"
    else:
        severity = "HIGH"

    contributions = [
        {
            "driver": k,
            "value":  round(feat_map[k], 4) if isinstance(feat_map[k], (int, float)) else feat_map[k],
            "coeff":  round(coeffs[k], 4),
            "contribution_pct": round(coeffs[k] * feat_map[k], 4),
        }
        for k in order if k != "intercept"
    ]
    contributions.sort(key=lambda c: -abs(c["contribution_pct"]))

    return {
        "updated_at":        datetime.now().isoformat(),
        "predicted_gap_pct": round(predicted, 3),
        "direction":         "UP" if predicted > 0 else "DOWN" if predicted < 0 else "FLAT",
        "severity":          severity,
        "severity_thresholds": {"LOW<": SEVERITY_LOW, "HIGH>=": SEVERITY_HIGH},
        "model":             {
            "r2_out_of_sample":  model.get("r2_out_of_sample"),
            "mae_pct":           model.get("test_mae_pct"),
            "direction_accuracy_pct": model.get("test_direction_accuracy_pct"),
            "train_rows":        model.get("train_rows"),
        },
        "contributions":     contributions,
        "vix_level":         round(vix_level, 2) if vix_level else None,
    }


def run_live() -> Dict:
    result = predict()
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    pg = result.get("predicted_gap_pct")
    sev = result.get("severity")
    if pg is None:
        print(f"Gap predictor: error — {result.get('error')}")
    else:
        print(f"Predicted Nifty gap: {pg:+.3f}%  severity: {sev}  direction: {result['direction']}")
        print("Top contributions:")
        for c in result["contributions"][:5]:
            val = c["value"]
            val_s = f"{val:+.2f}%" if isinstance(val, (int, float)) else str(val)
            print(f"  {c['driver']:<12} d {val_s:<10} x coeff {c['coeff']:+.4f} = {c['contribution_pct']:+.3f}%")
    print(f"Wrote {OUTPUT_PATH}")
    return result


if __name__ == "__main__":
    run_live()
