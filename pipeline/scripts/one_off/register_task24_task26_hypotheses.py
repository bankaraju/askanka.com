"""One-off: append 14 PRE_REGISTERED hypothesis entries (13 spread baskets + 1 PDR) to the registry.

Run once on 2026-04-30 to formalize Task #24 (13 INDIA_SPREAD_PAIRS) and
Task #26 (Banks x NBFC PDR sister to SECRSI) as PRE_REGISTERED.

After this run, the kill-switch can fire on any of these 13 with full
hypothesis traceability.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REGISTRY = REPO_ROOT / "docs" / "superpowers" / "hypothesis-registry.jsonl"

NOW_ISO = "2026-04-30T22:00:00+05:30"
SPEC_TASK24 = "docs/superpowers/specs/2026-04-30-india-spread-pairs-13-basket-backtest-design.md"
DATA_DISC = "docs/research/india_spread_pairs_backtest/data_discovery_2026-04-30.md"
SPEC_PDR = "docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md"

BASKETS = [
    {"name": "Upstream vs Downstream", "long": ["ONGC", "OIL"], "short": ["IOC", "BPCL"], "triggers": ["oil_up", "escalation", "hormuz", "sanctions", "trump_threat"]},
    {"name": "Defence vs IT", "long": ["HAL", "BEL", "BDL"], "short": ["TCS", "INFY", "WIPRO"], "triggers": ["escalation", "defense_spend", "sanctions", "trump_threat", "hormuz", "oil_positive"]},
    {"name": "Reliance vs OMCs", "long": ["RELIANCE"], "short": ["BPCL", "IOC"], "triggers": ["oil_up", "refining_margin", "escalation"]},
    {"name": "Coal vs OMCs", "long": ["COALINDIA"], "short": ["BPCL", "IOC"], "triggers": ["energy_crisis", "oil_up", "escalation", "hormuz", "oil_positive"]},
    {"name": "Pharma vs Cyclicals", "long": ["SUNPHARMA", "DRREDDY"], "short": ["TMPV", "M&M"], "triggers": ["escalation", "de_escalation", "diplomacy"]},
    {"name": "PSU Commodity vs Banks", "long": ["ONGC", "COALINDIA"], "short": ["HDFCBANK", "ICICIBANK"], "triggers": ["escalation", "sanctions", "hormuz"]},
    {"name": "Defence vs Auto", "long": ["HAL", "BEL"], "short": ["TMPV", "MARUTI"], "triggers": ["escalation", "defense_spend", "trump_threat"]},
    {"name": "PSU Energy vs Private", "long": ["ONGC", "COALINDIA", "OIL"], "short": ["RELIANCE", "ADANIENT"], "triggers": ["oil_up", "escalation", "hormuz"]},
    {"name": "Pharma vs Banks", "long": ["SUNPHARMA", "DRREDDY"], "short": ["HDFCBANK", "ICICIBANK"], "triggers": ["rbi_policy", "de_escalation", "diplomacy"]},
    {"name": "Banks vs IT", "long": ["HDFCBANK", "ICICIBANK"], "short": ["TCS", "INFY", "WIPRO"], "triggers": ["rbi_policy", "de_escalation", "diplomacy"]},
    {"name": "PSU NBFC vs Private Banks", "long": ["HUDCO", "NHPC"], "short": ["HDFCBANK", "ICICIBANK"], "triggers": ["rbi_policy", "nbfc_reform"]},
    {"name": "EV Plays vs ICE Auto", "long": ["TMPV", "M&M"], "short": ["MARUTI"], "triggers": ["ev_policy"]},
    {"name": "Infra Capex Beneficiaries", "long": ["ULTRACEMCO", "AMBUJACEM"], "short": ["ADANIENT"], "triggers": ["infra_capex", "tax_reform"]},
]

VERDICT_BAR_BASKET = {
    "post_cost_mean_bps_at_20bp": "> 0",
    "post_cost_mean_bps_at_30bp": "> 0",
    "t_stat": "> 2.0",
    "bh_fdr_pass": True,
    "bootstrap_stability_pct_min": 60,
    "hit_rate_pct_min": 55,
    "max_drawdown_pct_max": 25,
    "min_n_per_cell": 10,
}


def basket_entry(idx: int, b: dict) -> dict:
    hid = f"H-2026-04-30-spread-basket-{idx:03d}"
    return {
        "hypothesis_id": hid,
        "terminal_state": "PRE_REGISTERED",
        "registered_at": NOW_ISO,
        "registered_by": "Bharat Ankaraju",
        "spec_ref": SPEC_TASK24,
        "data_discovery_ref": DATA_DISC,
        "strategy_class": "news-conditioned-spread-basket-backtest",
        "basket_name": b["name"],
        "long_legs": b["long"],
        "short_legs": b["short"],
        "news_triggers_locked": b["triggers"],
        "claim_short": (
            f"Basket '{b['name']}' fires when any of the locked trigger keywords "
            f"classifies a headline; LONG {b['long']} SHORT {b['short']} earns "
            "post-cost mean > 0 with t > 2 and BH-FDR survive across "
            "(regime x hold) cells."
        ),
        "mode_a_window": ["2024-04-23", "2026-04-22"],
        "mode_a_description": "news-conditional, replays classifier on news_events_history.json",
        "mode_b_window": ["2021-04-23", "2026-04-22"],
        "mode_b_description": "trigger-agnostic structural test, every-day-fires",
        "hold_periods_days": [1, 3, 5],
        "cost_round_trip_bps": 20,
        "cost_sensitivity_bps": 30,
        "sizing": "equal_notional_per_leg_dollar_neutral",
        "stop_loss_pct_per_basket": -3.0,
        "time_stop": "exit at end of hold period",
        "multiplicity_correction": "BH-FDR-q-0.10-across-195-cells",
        "bootstrap_iterations": 200,
        "bootstrap_window_trading_days": 252,
        "verdict_bar": VERDICT_BAR_BASKET,
        "single_touch_locked": True,
        "data_primary_trigger": {
            "description": "news classifier output triggers",
            "computable_from": ["news_classifier"],
            "required": True,
            "note": "this hypothesis predates the data-primary architecture; news IS the primary trigger by design — that is what the backtest is testing",
        },
        "news_confirmation": {"required": False},
        "in_sample_status": "NO_PRIOR_BACKTEST_EXCEPT_LEGACY_3Y_NO_COST_UNIFIED_BACKTEST",
        "predecessor_hypothesis_id": None,
        "standards_version": "1.0_2026-04-23",
        "notes": (
            "One of 13 baskets in INDIA_SPREAD_PAIRS_DEPRECATED config block "
            "(pipeline/config.py:119). All 13 fire live in paper trading on "
            "news-keyword triggers. Task #24 5y backtest is the formal verdict "
            "that decides which baskets survive and which get killed under "
            "is_news_driven_killed(). Pre-registered AS-IS from live config, no "
            "parameter changes."
        ),
    }


def pdr_entry() -> dict:
    return {
        "hypothesis_id": "H-2026-04-30-PDR-BNK-NBFC",
        "terminal_state": "PRE_REGISTERED",
        "registered_at": NOW_ISO,
        "registered_by": "Bharat Ankaraju",
        "spec_ref": SPEC_PDR,
        "strategy_class": "intraday-pair-divergence-reversion",
        "claim_short": (
            "Banks x NBFC_HFC sector pair divergence > 1.0sigma at 11:00 IST -> "
            "open mean-reversion basket, close 14:25 IST -> post-S1 mean > 0, "
            "hit >= 55%, Sharpe >= 0.8 across forward holdout."
        ),
        "predecessor_hypothesis_id": "sector_pair_divergence_PDR-002_intraday_discovery",
        "predecessor_status": "CONSUMED_underpowered_directionally_consistent_n_9_t_1.32_post_+11.0bp",
        "in_sample_window": ["2026-02-19", "2026-04-30"],
        "holdout_window": ["2026-05-01", "2026-08-31"],
        "min_holdout_observations": 40,
        "auto_extend_to": "2026-12-31",
        "pair": ["Banks", "NBFC_HFC"],
        "divergence_threshold_k_sigma": 1.0,
        "sigma_rolling_window_trading_days": 60,
        "entry_time_ist": "11:00",
        "exit_time_ist": "14:25",
        "stop_rule": "ATR(14)*2.0 per leg",
        "sizing": "equal_notional_4_legs_dollar_neutral",
        "verdict_bar": {
            "post_cost_mean_bps": "> 0",
            "p_value": "< 0.05",
            "hit_rate_pct_min": 55,
            "sharpe_min": 0.8,
        },
        "alpha": 0.05,
        "multiplicity_correction": "none_single_hypothesis",
        "stat_test": "label_permutation_null_10000_perms",
        "single_touch_locked": True,
        "data_primary_trigger": {
            "description": "sector-pair divergence Z >= 1.0sigma at 11:00 IST",
            "computable_from": ["price"],
            "required": True,
        },
        "news_confirmation": {"required": False},
        "standards_version": "1.0_2026-04-23",
        "notes": (
            "Sister to SECRSI (H-2026-04-27-003). SECRSI = trend-continuation; "
            "PDR = mean-reversion. Designed as portfolio diversifier."
        ),
    }


def main() -> int:
    entries: list[dict] = []
    for idx, b in enumerate(BASKETS, start=1):
        entries.append(basket_entry(idx, b))
    entries.append(pdr_entry())

    # Idempotency check: skip writing if any of the IDs already in registry
    existing = set()
    if REGISTRY.exists():
        with REGISTRY.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if "hypothesis_id" in rec:
                        existing.add(rec["hypothesis_id"])
                except Exception:
                    continue

    new_entries = [e for e in entries if e["hypothesis_id"] not in existing]
    if not new_entries:
        print("All 14 entries already in registry — nothing to do.")
        return 0

    with REGISTRY.open("a", encoding="utf-8") as f:
        for e in new_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Appended {len(new_entries)} entries.")
    print(f"Skipped {len(entries) - len(new_entries)} (already present).")
    with REGISTRY.open("r", encoding="utf-8") as f:
        n = sum(1 for _ in f)
    print(f"Registry total lines now: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
