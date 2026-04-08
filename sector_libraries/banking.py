"""
Banking Sector: 23-Ratio Goldman-Style Framework

Covers NIM analysis, RBI stress tests, NPA forensics,
capital adequacy, and liability franchise quality.
"""


RATIO_FRAMEWORK = {
    # ── Profitability (5) ──
    "nim": {"formula": "(Interest Income - Interest Expense) / Avg Earning Assets", "benchmark": ">3.0%"},
    "roa": {"formula": "PAT / Avg Total Assets", "benchmark": ">1.0%"},
    "roe": {"formula": "PAT / Avg Equity", "benchmark": ">15%"},
    "cost_to_income": {"formula": "Operating Expenses / Total Income", "benchmark": "<45%"},
    "ppop_margin": {"formula": "Pre-Provision Operating Profit / Total Income", "benchmark": ">50%"},

    # ── Asset Quality / NPA Forensics (6) ──
    "gnpa_ratio": {"formula": "Gross NPA / Gross Advances", "benchmark": "<2.0%"},
    "nnpa_ratio": {"formula": "Net NPA / Net Advances", "benchmark": "<1.0%"},
    "provision_coverage": {"formula": "Provisions / Gross NPA", "benchmark": ">70%"},
    "slippage_ratio": {"formula": "Fresh NPA / Opening Std Advances", "benchmark": "<2.0%"},
    "credit_cost": {"formula": "Provisions / Avg Advances", "benchmark": "<1.0%"},
    "sma_2_ratio": {"formula": "SMA-2 (61-90 DPD) / Total Advances", "benchmark": "<0.5%"},

    # ── Capital Adequacy (3) ──
    "car": {"formula": "Capital / Risk Weighted Assets", "benchmark": ">12% (RBI min 11.5%)"},
    "cet1": {"formula": "CET1 Capital / RWA", "benchmark": ">8%"},
    "leverage_ratio": {"formula": "Tier 1 Capital / Total Exposure", "benchmark": ">4%"},

    # ── Liability Franchise (3) ──
    "casa_ratio": {"formula": "CASA Deposits / Total Deposits", "benchmark": ">40%"},
    "cost_of_deposits": {"formula": "Interest on Deposits / Avg Deposits", "benchmark": "<5.0%"},
    "credit_deposit": {"formula": "Advances / Deposits", "benchmark": "75-85%"},

    # ── Growth & Scale (3) ──
    "advance_growth": {"formula": "Advances YoY Growth %", "benchmark": ">15%"},
    "deposit_growth": {"formula": "Deposits YoY Growth %", "benchmark": ">12%"},
    "fee_income_ratio": {"formula": "Non-Interest Income / Total Income", "benchmark": ">25%"},

    # ── RBI Stress Sensitivity (3) ──
    "rbi_stress_gnpa": {"formula": "Projected GNPA under RBI adverse scenario", "benchmark": "from RBI FSR"},
    "rbi_stress_car": {"formula": "Projected CAR under RBI adverse scenario", "benchmark": ">9%"},
    "restructured_book": {"formula": "Restructured Advances / Total Advances", "benchmark": "<2%"},
}


def calculate(quarterly_filings: list, annual_reports: list) -> dict:
    """Calculate all 23 banking ratios from structured financial data.

    Returns dict of ratio_name → list of (period, value) tuples.
    """
    ratios = {}

    for ratio_name, spec in RATIO_FRAMEWORK.items():
        values = _compute_ratio(ratio_name, quarterly_filings, annual_reports)
        if values:
            ratios[ratio_name] = values

    return ratios


def _compute_ratio(name: str, quarterly: list, annual: list) -> list:
    """Compute a single ratio across all available periods."""
    # TODO: Extract fields from structured data and calculate
    return []


def get_forensic_flags(ratios: dict) -> list:
    """Banking-specific forensic red flags."""
    flags = []

    # GNPA trend deterioration
    gnpa = ratios.get("gnpa_ratio", [])
    if len(gnpa) >= 4:
        recent = [v for _, v in gnpa[-4:] if isinstance(v, (int, float))]
        if len(recent) >= 4 and recent[-1] > recent[0] * 1.2:
            flags.append("GNPA deteriorating: latest is 20%+ above 4Q ago")

    # Provision coverage dropping
    pcr = ratios.get("provision_coverage", [])
    if pcr:
        latest = pcr[-1][1] if isinstance(pcr[-1][1], (int, float)) else 0
        if latest < 65:
            flags.append(f"Provision coverage weak: {latest:.0f}% (benchmark >70%)")

    # SMA-2 spike (early warning of future NPAs)
    sma2 = ratios.get("sma_2_ratio", [])
    if sma2:
        latest = sma2[-1][1] if isinstance(sma2[-1][1], (int, float)) else 0
        if latest > 1.0:
            flags.append(f"SMA-2 elevated: {latest:.1f}% — future NPA risk")

    return flags
