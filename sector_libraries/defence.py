"""
Defence & Aerospace Sector: Forensic Ratio Framework

These ratios are designed to see through percentage-of-completion accounting,
inflated order books, and government contractor agency problems.

The key question: Can they DELIVER what they've BOOKED?
"""

import json
from pathlib import Path


RATIO_FRAMEWORK = {
    # ── Order Book Reality (5 ratios) ──────────────────────────────
    "order_book_to_revenue": {
        "formula": "Order Book / Annual Revenue",
        "unit": "years",
        "what_it_reveals": "Backlog in years. >5 years = execution risk. >8 years = fantasy.",
        "healthy": "3-5 years",
        "red_flag": ">7 years",
    },
    "order_book_to_production_capacity": {
        "formula": "Order Book / (Units Produced * Avg Revenue Per Unit)",
        "unit": "years",
        "what_it_reveals": "How long to clear backlog at CURRENT production rates. The real number.",
        "healthy": "<5 years",
        "red_flag": ">8 years — order book is unexecutable",
    },
    "order_inflow_to_execution": {
        "formula": "New Orders Received / Revenue Recognized",
        "unit": "ratio",
        "what_it_reveals": ">1.5 means booking faster than delivering. Backlog growing = future problem.",
        "healthy": "0.8-1.2",
        "red_flag": ">1.5 — booking far faster than executing",
    },
    "order_book_growth_vs_capacity_growth": {
        "formula": "Order Book CAGR / Production Capacity CAGR",
        "unit": "ratio",
        "what_it_reveals": "If order book grows but capacity doesn't, it's a headline game.",
        "healthy": "Both growing at similar rates",
        "red_flag": "Order book growing, capacity flat or declining",
    },
    "executable_order_book_pct": {
        "formula": "(Production Capacity * 5 years * Avg Rev/Unit) / Order Book * 100",
        "unit": "%",
        "what_it_reveals": "What % of order book can actually be delivered in 5 years.",
        "healthy": ">60%",
        "red_flag": "<40% — most of order book is undeliverable",
    },

    # ── Production & Delivery (4 ratios) ───────────────────────────
    "revenue_per_unit_delivered": {
        "formula": "Revenue / Units Delivered",
        "unit": "Cr per unit",
        "what_it_reveals": "Rising without mix change = PoC revenue inflation.",
        "healthy": "Stable or rising with product mix shift",
        "red_flag": "Rising sharply without new higher-value products",
    },
    "revenue_per_employee": {
        "formula": "Revenue / Total Employees",
        "unit": "Cr per employee",
        "what_it_reveals": "Rising with declining employees = outsourcing, not productivity.",
        "healthy": "Rising with stable/growing workforce",
        "red_flag": "Rising while employees decline",
    },
    "capex_to_order_book": {
        "formula": "Annual Capex / Order Book * 100",
        "unit": "%",
        "what_it_reveals": "Are they investing enough to execute the order book? <1% = under-investing.",
        "healthy": "1-3%",
        "red_flag": "<0.5% — not investing to deliver",
    },
    "capex_intensity": {
        "formula": "Capex / Revenue * 100",
        "unit": "%",
        "what_it_reveals": "For a manufacturer, <5% capex intensity = becoming a service company.",
        "healthy": "5-10%",
        "red_flag": "<3% — not investing in manufacturing",
    },

    # ── Accounting Forensics (4 ratios) ────────────────────────────
    "advances_to_revenue": {
        "formula": "Customer Advances / Revenue * 100",
        "unit": "%",
        "what_it_reveals": "High advances = collecting money before delivery. PoC warning.",
        "healthy": "<30%",
        "red_flag": ">50% — collecting far ahead of delivery",
    },
    "unbilled_revenue_to_revenue": {
        "formula": "Unbilled Revenue / Revenue * 100",
        "unit": "%",
        "what_it_reveals": "Revenue recognized but not yet billed = aggressive PoC accounting.",
        "healthy": "<10%",
        "red_flag": ">20% — aggressive revenue recognition",
    },
    "receivables_days": {
        "formula": "Trade Receivables / (Revenue/365)",
        "unit": "days",
        "what_it_reveals": "Government companies collect slowly. >180 days = cash flow risk.",
        "healthy": "<120 days",
        "red_flag": ">180 days",
    },
    "ocf_to_pat": {
        "formula": "Operating Cash Flow / Net Profit",
        "unit": "ratio",
        "what_it_reveals": "<0.7 = profits are on paper, not in cash. PoC artifact.",
        "healthy": ">0.8",
        "red_flag": "<0.5 — paper profits",
    },

    # ── Export & Diversification (2 ratios) ────────────────────────
    "export_revenue_pct": {
        "formula": "Export Revenue / Total Revenue * 100",
        "unit": "%",
        "what_it_reveals": "International competitiveness. Flat over years = no real export capability.",
        "healthy": ">10% for diversification",
        "red_flag": "<2% after years of export promises",
    },
    "customer_concentration": {
        "formula": "Revenue from Top Customer (Govt) / Total Revenue * 100",
        "unit": "%",
        "what_it_reveals": ">90% = monopoly supplier to single customer. Zero pricing power.",
        "healthy": "<70%",
        "red_flag": ">90% — complete dependency",
    },
}


def calculate(screener_data: dict, narratives: list, symbol: str) -> dict:
    """Calculate defence forensic ratios from available data.

    Returns dict with computed ratios, forensic flags, and realistic valuation.
    """
    pl = screener_data.get("profit_loss", [])
    bs = screener_data.get("balance_sheet", [])
    cf = screener_data.get("cash_flow", [])
    about = screener_data.get("about", {})

    # Extract actuals from narratives (order book, production, exports, employees)
    yearly_data = {}
    for narr in narratives:
        year = narr.get("source_year", "")
        actuals = narr.get("actuals_reported", {})
        if actuals:
            yearly_data[year] = actuals

    # Parse Screener numeric values
    def parse_num(s):
        if not s or s == "":
            return None
        try:
            return float(str(s).replace(",", "").replace("%", "").replace("Rs ", "").replace("Cr", "").strip())
        except:
            return None

    def get_pl_row(label):
        for row in pl:
            if row.get("", "").strip().rstrip("+") == label.rstrip("+"):
                return row
        return {}

    # Get time series from Screener
    years = [f"Mar {y}" for y in range(2018, 2026)]
    revenue_series = {}
    for yr in years:
        val = parse_num(get_pl_row("Sales+").get(yr) or get_pl_row("Sales").get(yr))
        if val:
            revenue_series[yr] = val

    net_profit_series = {}
    for yr in years:
        val = parse_num(get_pl_row("Net Profit+").get(yr) or get_pl_row("Net Profit").get(yr))
        if val:
            net_profit_series[yr] = val

    # Build order book series from narratives
    order_book_series = {}
    production_series = {}
    employee_series = {}
    export_series = {}
    capex_series = {}

    for year_key, actuals in yearly_data.items():
        # Parse order book
        ob = actuals.get("order_book", "")
        ob_val = _parse_crores(ob)
        if ob_val:
            order_book_series[year_key] = ob_val

        # Parse employees
        emp = actuals.get("employees", "")
        emp_val = parse_num(str(emp).replace(",", ""))
        if emp_val:
            employee_series[year_key] = emp_val

        # Parse exports
        exp = actuals.get("export_revenue", "")
        exp_val = _parse_crores(exp)
        if exp_val:
            export_series[year_key] = exp_val

        # Parse capex
        cap = actuals.get("capex_spent", "")
        cap_val = _parse_crores(cap)
        if cap_val:
            capex_series[year_key] = cap_val

    # ── Calculate ratios ─────────────────────────────────────────
    computed = {}
    flags = []

    # Latest values
    latest_revenue = list(revenue_series.values())[-1] if revenue_series else None
    latest_order_book = list(order_book_series.values())[-1] if order_book_series else None
    latest_employees = list(employee_series.values())[-1] if employee_series else None
    latest_exports = list(export_series.values())[-1] if export_series else None
    latest_capex = list(capex_series.values())[-1] if capex_series else None

    # 1. Order Book to Revenue (years of backlog)
    if latest_order_book and latest_revenue and latest_revenue > 0:
        ob_to_rev = latest_order_book / latest_revenue
        computed["order_book_to_revenue"] = {
            "value": round(ob_to_rev, 1),
            "unit": "years",
            "interpretation": f"{ob_to_rev:.1f} years of backlog at current revenue run-rate",
            "flag": "RED" if ob_to_rev > 7 else "AMBER" if ob_to_rev > 5 else "GREEN",
        }
        if ob_to_rev > 7:
            flags.append(f"Order book is {ob_to_rev:.1f}x revenue — unexecutable at current rates")

    # 2. Revenue per employee
    if latest_revenue and latest_employees and latest_employees > 0:
        rev_per_emp = latest_revenue / latest_employees
        computed["revenue_per_employee"] = {
            "value": round(rev_per_emp, 2),
            "unit": "Cr per employee",
            "series": {k: round(revenue_series.get(f"Mar {k[-4:]}", 0) / v, 2)
                       for k, v in employee_series.items()
                       if v > 0 and f"Mar {k[-4:]}" in revenue_series} if employee_series else {},
        }

    # 3. Capex to Order Book
    if latest_capex and latest_order_book and latest_order_book > 0:
        capex_to_ob = latest_capex / latest_order_book * 100
        computed["capex_to_order_book"] = {
            "value": round(capex_to_ob, 2),
            "unit": "%",
            "interpretation": f"Investing {capex_to_ob:.2f}% of order book annually in capacity",
            "flag": "RED" if capex_to_ob < 0.5 else "AMBER" if capex_to_ob < 1.0 else "GREEN",
        }
        if capex_to_ob < 1.0:
            flags.append(f"Capex is only {capex_to_ob:.2f}% of order book — severe under-investment")

    # 4. Capex intensity
    if latest_capex and latest_revenue and latest_revenue > 0:
        capex_int = latest_capex / latest_revenue * 100
        computed["capex_intensity"] = {
            "value": round(capex_int, 1),
            "unit": "%",
            "interpretation": f"Spending {capex_int:.1f}% of revenue on capex",
            "flag": "RED" if capex_int < 3 else "AMBER" if capex_int < 5 else "GREEN",
        }

    # 5. Export credibility
    if export_series and latest_revenue:
        export_pcts = {}
        for k, v in export_series.items():
            fy = f"Mar {k[-4:]}" if k[-4:].isdigit() else ""
            rev = revenue_series.get(fy, latest_revenue)
            if rev > 0:
                export_pcts[k] = round(v / rev * 100, 2)
        computed["export_revenue_pct"] = {
            "value": round(latest_exports / latest_revenue * 100, 2) if latest_exports else 0,
            "unit": "%",
            "series": export_pcts,
            "interpretation": "Flat at ~1% for 8 years despite annual export promises" if all(v < 3 for v in export_pcts.values()) else "Showing some export traction",
            "flag": "RED" if all(v < 2 for v in export_pcts.values()) else "GREEN",
        }
        if all(v < 3 for v in export_pcts.values()):
            flags.append("Export revenue flat at ~1% for 8 years — guidance is recycled aspiration")

    # 6. Order Book Growth vs Revenue Growth (execution gap)
    if len(order_book_series) >= 2 and len(revenue_series) >= 2:
        ob_values = list(order_book_series.values())
        rev_values = list(revenue_series.values())
        ob_growth = (ob_values[-1] / ob_values[0]) ** (1 / (len(ob_values) - 1)) - 1 if ob_values[0] > 0 else 0
        rev_growth = (rev_values[-1] / rev_values[0]) ** (1 / (len(rev_values) - 1)) - 1 if rev_values[0] > 0 else 0
        gap = ob_growth - rev_growth
        computed["order_book_vs_revenue_growth"] = {
            "order_book_cagr": round(ob_growth * 100, 1),
            "revenue_cagr": round(rev_growth * 100, 1),
            "execution_gap": round(gap * 100, 1),
            "interpretation": f"Order book growing {ob_growth*100:.1f}% CAGR vs revenue {rev_growth*100:.1f}% — gap of {gap*100:.1f}pp",
            "flag": "RED" if gap > 0.10 else "AMBER" if gap > 0.05 else "GREEN",
        }
        if gap > 0.10:
            flags.append(f"Order book CAGR {ob_growth*100:.0f}% vs revenue CAGR {rev_growth*100:.0f}% — widening execution gap")

    # ── REALISTIC VALUATION ──────────────────────────────────────
    valuation = _realistic_valuation(
        latest_revenue, latest_order_book, latest_capex,
        net_profit_series, about, computed
    )

    return {
        "ratios": computed,
        "forensic_flags": flags,
        "flag_count": {"RED": sum(1 for r in computed.values() if isinstance(r, dict) and r.get("flag") == "RED"),
                       "AMBER": sum(1 for r in computed.values() if isinstance(r, dict) and r.get("flag") == "AMBER"),
                       "GREEN": sum(1 for r in computed.values() if isinstance(r, dict) and r.get("flag") == "GREEN")},
        "time_series": {
            "order_book": order_book_series,
            "revenue": revenue_series,
            "employees": employee_series,
            "exports": export_series,
            "capex": capex_series,
        },
        "realistic_valuation": valuation,
    }


def _parse_crores(text: str) -> float | None:
    """Parse various Indian currency formats to crores."""
    if not text:
        return None
    text = str(text).strip()
    # Handle lakh format (Rs 28,16,185 Lakh = 28161.85 Cr)
    if "lakh" in text.lower() or "lakhs" in text.lower():
        num = text.lower().replace("rs", "").replace("lakh", "").replace("lakhs", "").replace(",", "").replace("₹", "").strip()
        try:
            return float(num) / 100  # Lakh to Crore
        except:
            return None
    # Handle crore format
    text = text.replace("₹", "").replace("Rs", "").replace("Rs.", "").replace("Cr", "").replace("crores", "").replace("crore", "").replace(",", "").strip()
    try:
        return float(text)
    except:
        return None


def _realistic_valuation(revenue, order_book, capex, net_profit_series, about, ratios):
    """Calculate what HAL SHOULD be worth based on executable order book."""
    if not revenue or not order_book:
        return {"error": "Insufficient data"}

    current_pe = None
    try:
        current_pe = float(str(about.get("Stock P/E", "0")).replace(",", ""))
    except:
        pass

    current_mcap = None
    try:
        current_mcap = float(str(about.get("Market Cap", "0")).replace(",", ""))
    except:
        pass

    latest_pat = list(net_profit_series.values())[-1] if net_profit_series else None

    # Order book executability analysis
    ob_to_rev = order_book / revenue if revenue > 0 else 0

    # At current production rates, how much of order book is executable in 5 years?
    executable_5yr = min(revenue * 5 * 1.10, order_book)  # Assume 10% annual capacity growth (generous)
    executable_pct = executable_5yr / order_book * 100 if order_book > 0 else 0

    # What's the "realistic" revenue growth?
    # If order book is 6+ years, revenue growth is capped by production capacity, not demand
    if ob_to_rev > 6:
        realistic_growth = 8.0  # Capped by production, not demand
        growth_note = "Growth capped by production capacity, not demand. Order book is aspirational beyond 5 years."
    elif ob_to_rev > 4:
        realistic_growth = 12.0
        growth_note = "Moderate growth limited by execution capability."
    else:
        realistic_growth = 15.0
        growth_note = "Order book supports stated growth trajectory."

    # Fair PE based on realistic growth
    # PEG of 1.5 for government defence monopoly (should be lower due to agency risk)
    fair_pe = realistic_growth * 1.2  # PEG 1.2 for government company with agency issues

    # Discount for agency problem
    agency_discount = 0
    red_flags = sum(1 for r in ratios.values() if isinstance(r, dict) and r.get("flag") == "RED")
    if red_flags >= 3:
        agency_discount = 20
    elif red_flags >= 2:
        agency_discount = 10

    fair_pe_adjusted = fair_pe * (1 - agency_discount / 100)

    fair_value = None
    overvaluation_pct = None
    if latest_pat and latest_pat > 0:
        fair_value = latest_pat * fair_pe_adjusted
        if current_mcap and current_mcap > 0:
            overvaluation_pct = (current_mcap / fair_value - 1) * 100

    return {
        "order_book_years": round(ob_to_rev, 1),
        "executable_in_5yr_pct": round(executable_pct, 1),
        "executable_order_value": round(executable_5yr, 0),
        "unexecutable_order_value": round(max(0, order_book - executable_5yr), 0),
        "realistic_revenue_growth_pct": realistic_growth,
        "growth_note": growth_note,
        "fair_pe_before_discount": round(fair_pe, 1),
        "agency_discount_pct": agency_discount,
        "fair_pe_after_discount": round(fair_pe_adjusted, 1),
        "current_pe": current_pe,
        "fair_market_cap": round(fair_value, 0) if fair_value else None,
        "current_market_cap": current_mcap,
        "overvaluation_pct": round(overvaluation_pct, 1) if overvaluation_pct is not None else None,
        "verdict": (
            f"Market prices HAL at {current_pe:.0f}x PE. "
            f"Based on executable order book ({executable_pct:.0f}% of headline), "
            f"realistic growth ({realistic_growth:.0f}%), and agency discount ({agency_discount}%), "
            f"fair PE is {fair_pe_adjusted:.0f}x. "
            + (f"Stock is {overvaluation_pct:.0f}% overvalued." if overvaluation_pct and overvaluation_pct > 10
               else f"Stock is {overvaluation_pct:.0f}% undervalued." if overvaluation_pct and overvaluation_pct < -10
               else "Stock is fairly valued." if overvaluation_pct is not None
               else "Cannot determine valuation.")
        ),
    }
