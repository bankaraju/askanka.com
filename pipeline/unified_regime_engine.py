"""
Anka Research — Unified Regime Engine
ONE engine that takes ALL inputs and produces ONE regime call.
Everything downstream follows this call — spreads, instruments,
articles, Telegram, website. No contradictions.

Inputs:
  1. Global ETF Composite (31 ETFs, optimised weights)
  2. Options PCR (nearest expiry, all strikes)
  3. India VIX
  4. FII/DII institutional flows
  5. Crude oil change
  6. Fragility model score
  7. Pinning state (Thursday)

Output:
  - Zone: RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA
  - Score: -100 to +100
  - Confidence: 0-100%
  - Recommended spreads with holding period
  - Instrument type (stock / futures / options / straddle)
  - Position management (hold / tighten / exit)
  - Article tone
  - Days in current zone

Usage:
    engine = UnifiedRegimeEngine()
    regime = engine.compute()
    print(regime.zone, regime.score, regime.recommended_spreads)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field

log = logging.getLogger("anka.regime_engine")

IST = timezone(timedelta(hours=5, minutes=30))
PIPELINE_DIR = Path(__file__).parent
DATA_DIR = PIPELINE_DIR / "data"
AUTORESEARCH_DIR = PIPELINE_DIR / "autoresearch"

sys.path.insert(0, str(PIPELINE_DIR))
from dotenv import load_dotenv
load_dotenv(PIPELINE_DIR / ".env")


@dataclass
class RegimeCall:
    """The unified regime output. Everything downstream reads this."""
    zone: str = "NEUTRAL"
    score: float = 0.0
    confidence: int = 50
    days_in_zone: int = 1
    zone_trend: str = "stable"  # strengthening / weakening / stable

    # What to trade
    recommended_spreads: list = field(default_factory=list)
    holding_period: int = 5
    position_size: float = 1.0  # 1.0 = full, 0.75, 0.5
    stop_multiplier: float = 1.0  # 1.0 = normal, 1.25 = wider, 1.5 = widest

    # How to trade
    instrument: str = "stock"  # stock / futures / options / straddle
    pinning_active: bool = False
    straddle_opportunity: bool = False

    # Position management for existing trades
    existing_action: str = "hold"  # hold / tighten / exit
    existing_reason: str = ""

    # Content tone
    article_tone: str = "balanced"  # aggressive / balanced / cautious / defensive

    # Components (for transparency)
    etf_signal: float = 0.0
    pcr: float = 1.0
    vix: float = 20.0
    fii_dii: float = 0.0
    crude_change: float = 0.0
    fragility: float = 0.0

    # Metadata
    timestamp: str = ""
    data_quality: int = 100


# Zone thresholds from calm_zone_analysis.json (backtested)
CALM_CENTER = 0.0953
CALM_BAND = 3.8974
ZONE_THRESHOLDS = {
    "RISK-OFF": CALM_CENTER - 2 * CALM_BAND,      # -7.70
    "CAUTION": CALM_CENTER - CALM_BAND,             # -3.80
    "NEUTRAL_LOW": CALM_CENTER - CALM_BAND,         # -3.80
    "NEUTRAL_HIGH": CALM_CENTER + CALM_BAND,        # +3.99
    "RISK-ON": CALM_CENTER + CALM_BAND,             # +3.99
    "EUPHORIA": CALM_CENTER + 2 * CALM_BAND,        # +7.89
}

# Optimal spread recommendations per zone (from regime_to_trades.py)
ZONE_SPREADS = {
    "RISK-OFF": [
        {"name": "Pharma vs Banks", "win_1d": 70, "win_5d": 60, "best_period": 1},
        {"name": "Banks vs IT", "win_3d": 65, "win_5d": 65, "best_period": 3},
    ],
    "CAUTION": [
        {"name": "Upstream vs Downstream", "win_3d": 62, "best_period": 3},
        {"name": "Pharma vs Banks", "win_5d": 56, "best_period": 5},
    ],
    "NEUTRAL": [
        {"name": "Defence vs IT", "win_5d": 59, "avg_5d": 1.03, "best_period": 5},
        {"name": "Banks vs IT", "win_3d": 54, "best_period": 3},
    ],
    "RISK-ON": [
        {"name": "Pharma vs Banks", "win_1d": 61, "win_3d": 61, "best_period": 3},
        {"name": "Defence vs IT", "win_5d": 52, "best_period": 5},
    ],
    "EUPHORIA": [
        {"name": "Defence vs IT", "win_1d": 73, "win_5d": 60, "avg_5d": 3.02, "best_period": 5},
        {"name": "Pharma vs Banks", "win_5d": 80, "best_period": 5},
    ],
}

# Regime history for tracking zone persistence
REGIME_HISTORY_FILE = DATA_DIR / "regime_history.json"


class UnifiedRegimeEngine:
    """The single source of truth for market regime."""

    def __init__(self):
        self.etf_weights = self._load_etf_weights()
        self.regime_history = self._load_regime_history()

    def _load_etf_weights(self) -> dict:
        path = AUTORESEARCH_DIR / "etf_optimal_weights.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")).get("optimal_weights", {})
        return {}

    def _load_regime_history(self) -> list:
        if REGIME_HISTORY_FILE.exists():
            try:
                return json.loads(REGIME_HISTORY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return []

    def _save_regime_history(self, call: RegimeCall):
        self.regime_history.append({
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "time": datetime.now(IST).strftime("%H:%M"),
            "zone": call.zone,
            "score": call.score,
            "confidence": call.confidence,
        })
        self.regime_history = self.regime_history[-100:]
        REGIME_HISTORY_FILE.write_text(
            json.dumps(self.regime_history, indent=2), encoding="utf-8")

    def compute(self) -> RegimeCall:
        """Compute the unified regime call from all inputs."""
        call = RegimeCall(timestamp=datetime.now(IST).isoformat())
        quality_issues = []

        # ── 1. Global ETF Composite ──
        etf_signal = self._compute_etf_signal()
        call.etf_signal = etf_signal
        if etf_signal is None:
            quality_issues.append("ETF signal unavailable")
            etf_signal = 0

        # ── 2. Options PCR ──
        try:
            from options_monitor import fetch_nifty_oi
            oi = fetch_nifty_oi()
            call.pcr = oi.get("pcr", 1.0)
        except Exception as e:
            quality_issues.append(f"PCR unavailable: {e}")
            call.pcr = 1.0

        # ── 3. India VIX ──
        try:
            from kite_client import fetch_ltp
            vix_data = fetch_ltp(["INDIA VIX"])
            call.vix = vix_data.get("INDIA VIX", 20)
        except Exception:
            quality_issues.append("VIX unavailable")
            call.vix = 20

        # ── 4. FII/DII Flows ──
        try:
            from macro_stress import _fetch_institutional_flow
            flows = _fetch_institutional_flow()
            call.fii_dii = flows.get("combined", 0)
        except Exception:
            quality_issues.append("FII/DII unavailable")

        # ── 5. Crude Oil ──
        try:
            from macro_stress import _fetch_crude_change_5d
            call.crude_change = _fetch_crude_change_5d() or 0
        except Exception:
            quality_issues.append("Crude unavailable")

        # ── 6. Fragility ──
        try:
            from run_signals import _get_fragility_score
            frag = _get_fragility_score()
            call.fragility = frag.get("fragility_score", 0)
        except Exception:
            pass  # Not critical

        # ── 7. Pinning (Thursday only) ──
        now = datetime.now(IST)
        is_thursday = now.weekday() == 3
        if is_thursday:
            try:
                from pinning_detector import detect_pins
                pins = detect_pins()
                active_pins = [p for p in pins if p["strength"] in ("PERFECT", "STRONG")]
                call.pinning_active = len(active_pins) > 0
            except Exception:
                pass

        # ── COMPUTE ZONE ──
        # Primary: ETF composite signal
        # Secondary: PCR, VIX, fragility adjust confidence
        score = etf_signal

        # PCR adjustment: if PCR strongly contradicts ETF signal, reduce confidence
        pcr_direction = 1 if call.pcr > 1.1 else -1 if call.pcr < 0.85 else 0
        etf_direction = 1 if score > 0 else -1 if score < 0 else 0

        # VIX adjustment: high VIX reduces confidence in RISK-ON
        vix_penalty = max(0, (call.vix - 20) * 2) if score > 0 else 0

        # Fragility adjustment
        frag_penalty = call.fragility / 100 * 20  # Max 20% confidence reduction

        # Compute zone from score
        if score < ZONE_THRESHOLDS["RISK-OFF"]:
            call.zone = "RISK-OFF"
            call.confidence = min(95, 70 + int(abs(score) * 2))
        elif score < ZONE_THRESHOLDS["CAUTION"]:
            call.zone = "CAUTION"
            call.confidence = 60
        elif score < ZONE_THRESHOLDS["NEUTRAL_HIGH"]:
            call.zone = "NEUTRAL"
            call.confidence = 50
        elif score < ZONE_THRESHOLDS["EUPHORIA"]:
            call.zone = "RISK-ON"
            call.confidence = min(90, 60 + int(score * 2))
        else:
            call.zone = "EUPHORIA"
            call.confidence = 85

        # Apply adjustments
        if pcr_direction != 0 and pcr_direction != etf_direction:
            call.confidence = max(20, call.confidence - 15)
        call.confidence = max(20, call.confidence - int(vix_penalty) - int(frag_penalty))

        call.score = round(score, 2)

        # ── ZONE PERSISTENCE ──
        days_in_zone = 1
        for entry in reversed(self.regime_history):
            if entry["zone"] == call.zone:
                days_in_zone += 1
            else:
                break
        call.days_in_zone = days_in_zone

        # Zone trend from last 3 entries
        if len(self.regime_history) >= 3:
            recent_scores = [e["score"] for e in self.regime_history[-3:]]
            slope = recent_scores[-1] - recent_scores[0]
            call.zone_trend = "strengthening" if slope > 1 else "weakening" if slope < -1 else "stable"

        # ── TRADE RECOMMENDATIONS ──
        call.recommended_spreads = ZONE_SPREADS.get(call.zone, ZONE_SPREADS["NEUTRAL"])
        call.holding_period = call.recommended_spreads[0].get("best_period", 5) if call.recommended_spreads else 5

        # Position sizing
        size_map = {"RISK-OFF": 0.25, "CAUTION": 0.5, "NEUTRAL": 1.0, "RISK-ON": 1.0, "EUPHORIA": 0.75}
        call.position_size = size_map.get(call.zone, 1.0)

        # Stop multiplier
        stop_map = {"RISK-OFF": 2.0, "CAUTION": 1.5, "NEUTRAL": 1.0, "RISK-ON": 1.0, "EUPHORIA": 1.25}
        call.stop_multiplier = stop_map.get(call.zone, 1.0)

        # Fragility overlay
        if call.fragility > 70:
            call.position_size *= 0.5
            call.stop_multiplier *= 1.5

        # ── INSTRUMENT SELECTION ──
        if call.zone == "RISK-OFF":
            call.instrument = "cash_or_puts"
        elif is_thursday and call.pinning_active and call.vix > 18:
            call.instrument = "straddle"
            call.straddle_opportunity = True
        elif call.zone == "CAUTION":
            call.instrument = "futures"  # Easier to exit
        else:
            call.instrument = "stock"

        # ── EXISTING POSITION MANAGEMENT ──
        if call.zone == "RISK-OFF":
            call.existing_action = "exit"
            call.existing_reason = "RISK-OFF regime — exit all long-biased positions"
        elif call.zone == "CAUTION":
            call.existing_action = "tighten"
            call.existing_reason = f"CAUTION regime — tighten stops by {int((call.stop_multiplier-1)*100)}%, reduce to {int(call.position_size*100)}% size"
        elif call.zone in ("RISK-ON", "EUPHORIA"):
            call.existing_action = "hold"
            call.existing_reason = f"{call.zone} — hold winners, add on dips"
        else:
            call.existing_action = "hold"
            call.existing_reason = "NEUTRAL — standard stops, normal trading"

        # ── ARTICLE TONE ──
        tone_map = {
            "RISK-OFF": "defensive",
            "CAUTION": "cautious",
            "NEUTRAL": "balanced",
            "RISK-ON": "aggressive",
            "EUPHORIA": "aggressive",
        }
        call.article_tone = tone_map.get(call.zone, "balanced")

        # ── DATA QUALITY ──
        call.data_quality = max(0, 100 - len(quality_issues) * 20)

        # ── SAVE HISTORY ──
        self._save_regime_history(call)

        return call

    def _compute_etf_signal(self) -> float:
        """Compute ETF composite signal from EODHD daily data."""
        if not self.etf_weights:
            return 0.0

        try:
            from eodhd_client import fetch_eod_series

            etf_map = {
                "defence": "ITA.US", "energy": "XLE.US", "financials": "XLF.US",
                "tech": "XLK.US", "healthcare": "XLV.US", "staples": "XLP.US",
                "industrials": "XLI.US", "em": "EEM.US", "brazil": "EWZ.US",
                "india_etf": "INDA.US", "china": "FXI.US", "japan": "EWJ.US",
                "developed": "EFA.US", "oil": "USO.US", "natgas": "UNG.US",
                "silver": "SLV.US", "agriculture": "DBA.US", "high_yield": "HYG.US",
                "ig_bond": "LQD.US", "treasury": "TLT.US", "mid_treasury": "IEF.US",
                "dollar": "UUP.US", "euro": "FXE.US", "yen": "FXY.US",
                "sp500": "SPY.US", "gold": "GLD.US", "vix": "VIX.INDX",
                "kbw_bank": "KBE.US", "regional_bank": "KRE.US",
                "airlines": "JETS.US", "innovation": "ARKK.US",
            }

            signal = 0.0
            loaded = 0
            for name, weight in self.etf_weights.items():
                sym = etf_map.get(name)
                if not sym:
                    continue
                try:
                    data = fetch_eod_series(sym, days=5)
                    if data and len(data) >= 2:
                        col = "adjusted_close" if "adjusted_close" in data[-1] else "close"
                        today = float(data[-1][col])
                        yesterday = float(data[-2][col])
                        ret = (today / yesterday - 1) * 100
                        signal += ret * weight
                        loaded += 1
                except Exception:
                    continue

            if loaded < 10:
                log.warning("Only %d/%d ETFs loaded for signal", loaded, len(self.etf_weights))

            return round(signal, 4)
        except Exception as e:
            log.error("ETF signal computation failed: %s", e)
            return 0.0


def format_regime_telegram(call: RegimeCall) -> str:
    """Format the unified regime call for Telegram."""
    zone_emoji = {
        "RISK-OFF": "🔴", "CAUTION": "🟡", "NEUTRAL": "⚪",
        "RISK-ON": "🟢", "EUPHORIA": "💰",
    }
    emoji = zone_emoji.get(call.zone, "⚪")

    lines = [
        "━" * 22,
        f"🌐 *GLOBAL REGIME ENGINE* — {emoji} {call.zone}",
        "━" * 22,
        "",
        f"*Score:* {call.score:+.2f} | *Confidence:* {call.confidence}%",
        f"*Days in zone:* {call.days_in_zone} | *Trend:* {call.zone_trend}",
        f"*Data quality:* {call.data_quality}%",
        "",
        f"*Components:*",
        f"  ETF Signal: {call.etf_signal:+.2f} | VIX: {call.vix:.1f} | PCR: {call.pcr:.2f}",
        f"  FII/DII: {call.fii_dii:+,.0f}cr | Crude 5d: {call.crude_change:+.1f}%",
        f"  Fragility: {call.fragility:.0f}/100",
        "",
        f"*Trade:*",
        f"  Instrument: {call.instrument}",
        f"  Size: {call.position_size*100:.0f}% | Stops: {call.stop_multiplier:.1f}x",
        f"  Hold: {call.holding_period} days",
    ]

    if call.recommended_spreads:
        lines.append("")
        lines.append("*Recommended Spreads:*")
        for sp in call.recommended_spreads[:3]:
            name = sp.get("name", "?")
            best_p = sp.get("best_period", "?")
            best_w = sp.get(f"win_{best_p}d", sp.get("win_5d", sp.get("win_3d", sp.get("win_1d", "?"))))
            lines.append(f"  📌 *{name}* — {best_w}% win over {best_p}d")

    if call.straddle_opportunity:
        lines.append("")
        lines.append("🎯 *PINNING ACTIVE — straddle opportunity at pin strike*")

    lines.extend([
        "",
        f"*Open positions:* {call.existing_action.upper()}",
        f"  _{call.existing_reason}_",
        "",
        "_Anka Research · Unified Regime Engine_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Computing unified regime...")
    engine = UnifiedRegimeEngine()
    call = engine.compute()

    print(f"\n{'='*50}")
    print(f"ZONE: {call.zone}")
    print(f"Score: {call.score:+.2f} | Confidence: {call.confidence}%")
    print(f"Days in zone: {call.days_in_zone} | Trend: {call.zone_trend}")
    print(f"Instrument: {call.instrument} | Size: {call.position_size*100:.0f}%")
    print(f"Existing positions: {call.existing_action} — {call.existing_reason}")
    print(f"Article tone: {call.article_tone}")
    print(f"{'='*50}")

    msg = format_regime_telegram(call)
    print(f"\n{msg}")

    # Send to Telegram
    from telegram_bot import send_message
    send_message(msg)
    print("\nSent to Telegram!")
