"""Extract raw financial metrics from screener_financials.json + indianapi_stock.json."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Core metrics we expect to populate (used for coverage_pct denominator)
_CORE_METRICS = [
    "ROE",
    "ROCE",
    "EBITDA_Margin",
    "Revenue_Growth_3Y",
    "Debt_to_Equity",
    "CFO_PAT",
]


def _parse_screener_num(val: Any) -> float | None:
    """Parse screener numeric strings to float.

    Handles:
    - ``"1,07,476"``  → 107476.0
    - ``"18%"``       → 18.0
    - ``"16.6"``      → 16.6
    - ``""``          → None
    - ``None``        → None
    - ``"-2,411"``    → -2411.0
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # Strip trailing %
    s = s.rstrip("%").strip()
    # Strip commas (Indian number formatting)
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _find_row(rows: list[dict], label: str) -> dict | None:
    """Return the first row whose ``""`` key matches *label* exactly."""
    for row in rows:
        if row.get("") == label:
            return row
    return None


def _year_columns(row: dict, exclude_ttm: bool = True) -> list[str]:
    """Return sorted Mar YYYY column keys present in *row*, optionally excluding TTM."""
    cols = []
    for k in row:
        if k == "" or k == "TTM":
            continue
        if k.startswith("Mar ") or k.startswith("Sep "):
            # Use only Mar year-end cols for consistency
            if k.startswith("Mar "):
                cols.append(k)
    # Sort chronologically
    def _year_key(col: str) -> int:
        parts = col.split()
        if len(parts) >= 2:
            digits = "".join(ch for ch in parts[1] if ch.isdigit())
            if digits:
                return int(digits[:4])
        return 0
    cols.sort(key=_year_key)
    return cols


def _latest_value(row: dict) -> float | None:
    """Return the value from the most recent Mar YYYY column (not TTM)."""
    cols = _year_columns(row)
    if not cols:
        return None
    # Walk from latest backwards until we get a non-None value
    for col in reversed(cols):
        v = _parse_screener_num(row.get(col))
        if v is not None:
            return v
    return None


def _cagr_3y(row: dict) -> float | None:
    """Compute 3-year CAGR from the row using the two most-recent Mar values 3 years apart."""
    cols = _year_columns(row)
    if len(cols) < 4:
        return None
    # latest and 3 years ago
    latest_col = None
    base_col = None
    # Find the last col with a valid value
    for col in reversed(cols):
        if _parse_screener_num(row.get(col)) is not None:
            if latest_col is None:
                latest_col = col
            elif int(latest_col.split()[1]) - int(col.split()[1]) >= 3:
                base_col = col
                break

    if latest_col is None or base_col is None:
        return None

    v_latest = _parse_screener_num(row[latest_col])
    v_base = _parse_screener_num(row[base_col])
    if v_latest is None or v_base is None or v_base == 0:
        return None

    years = int(latest_col.split()[1]) - int(base_col.split()[1])
    if years <= 0:
        return None

    try:
        if v_base < 0 and v_latest < 0:
            # Both negative — revenue shrinkage, treat as negative growth
            cagr = (abs(v_latest) / abs(v_base)) ** (1 / years) - 1
            return round(-cagr * 100, 2)
        if v_base <= 0:
            return None
        cagr = (v_latest / v_base) ** (1 / years) - 1
        return round(cagr * 100, 2)
    except (ZeroDivisionError, ValueError):
        return None


def _row_history(row: dict) -> list[float]:
    """Return all non-None values from Mar YYYY columns in chronological order."""
    cols = _year_columns(row)
    result = []
    for col in cols:
        v = _parse_screener_num(row.get(col))
        if v is not None:
            result.append(v)
    return result


def _indianapi_value(key_metrics: dict, category: str, key: str) -> float | None:
    """Extract a value from indianapi keyMetrics by category + key name."""
    items = key_metrics.get(category, [])
    for item in items:
        if item.get("key") == key:
            v = item.get("value")
            if v is None:
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
    return None


class MetricExtractor:
    """Extract raw financial metrics for a stock from screener + indianapi artifacts."""

    def __init__(self, artifacts_dir: Path):
        self._artifacts = Path(artifacts_dir)

    def extract(self, symbol: str) -> dict:
        """Extract all available metrics for *symbol*. Returns a flat dict."""
        stock_dir = self._artifacts / symbol
        screener_path = stock_dir / "screener_financials.json"
        indianapi_path = stock_dir / "indianapi_stock.json"

        has_screener = screener_path.exists()
        has_indianapi = indianapi_path.exists()

        result: dict[str, Any] = {
            "has_screener": has_screener,
            "has_indianapi": has_indianapi,
            "is_bank": False,
            # Core metrics — None until populated
            "ROE": None,
            "ROCE": None,
            "EBITDA_Margin": None,
            "Revenue_Growth_3Y": None,
            "Debt_to_Equity": None,
            "CFO_PAT": None,
            # Bank-specific
            "NIM_proxy": None,
            "Cost_to_Income": None,
            # History lists
            "ROE_history": [],
            "Margin_history": [],
            # IndianAPI supplements
            "ROA_indianapi": None,
            "Revenue_Growth_5Y_indianapi": None,
            # Coverage
            "coverage_pct": 0.0,
        }

        if not has_screener:
            return result

        # ------------------------------------------------------------------
        # Load screener data
        # ------------------------------------------------------------------
        try:
            screener = json.loads(screener_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load screener for %s: %s", symbol, exc)
            return result

        profit_loss: list[dict] = screener.get("profit_loss", [])
        balance_sheet: list[dict] = screener.get("balance_sheet", [])
        cash_flow: list[dict] = screener.get("cash_flow", [])
        ratios: list[dict] = screener.get("ratios", [])
        about: dict = screener.get("about", {})

        # Detect bank vs non-bank
        is_bank = any(row.get("") == "Revenue+" for row in profit_loss)
        result["is_bank"] = is_bank

        # ------------------------------------------------------------------
        # About section: ROE, ROCE (pre-computed ratios)
        # ------------------------------------------------------------------
        roe_about = _parse_screener_num(about.get("ROE"))
        roce_about = _parse_screener_num(about.get("ROCE"))
        result["ROE"] = roe_about
        result["ROCE"] = roce_about

        # ------------------------------------------------------------------
        # EBITDA Margin / Financing Margin
        # ------------------------------------------------------------------
        if is_bank:
            margin_row = _find_row(profit_loss, "Financing Margin %")
        else:
            margin_row = _find_row(profit_loss, "OPM %")

        if margin_row is not None:
            result["EBITDA_Margin"] = _latest_value(margin_row)
            result["Margin_history"] = _row_history(margin_row)

        # ------------------------------------------------------------------
        # Revenue Growth 3Y CAGR
        # ------------------------------------------------------------------
        rev_label = "Revenue+" if is_bank else "Sales+"
        revenue_row = _find_row(profit_loss, rev_label)
        if revenue_row is not None:
            result["Revenue_Growth_3Y"] = _cagr_3y(revenue_row)

        # ------------------------------------------------------------------
        # Debt-to-Equity
        # ------------------------------------------------------------------
        if is_bank:
            borrowing_row = _find_row(balance_sheet, "Borrowing")
        else:
            borrowing_row = _find_row(balance_sheet, "Borrowings+")

        equity_row = _find_row(balance_sheet, "Equity Capital")
        reserves_row = _find_row(balance_sheet, "Reserves")

        if borrowing_row and equity_row and reserves_row:
            borrowing = _latest_value(borrowing_row)
            equity = _latest_value(equity_row)
            reserves = _latest_value(reserves_row)
            if borrowing is not None and equity is not None and reserves is not None:
                denominator = equity + reserves
                if denominator != 0:
                    result["Debt_to_Equity"] = round(borrowing / denominator, 4)

        # ------------------------------------------------------------------
        # CFO / PAT
        # ------------------------------------------------------------------
        cfo_row = _find_row(cash_flow, "Cash from Operating Activity+")
        net_profit_row = _find_row(profit_loss, "Net Profit+")

        if cfo_row and net_profit_row:
            # Use the same latest year for both
            cfo_cols = _year_columns(cfo_row)
            np_cols = _year_columns(net_profit_row)
            # Find latest common year
            common = sorted(set(cfo_cols) & set(np_cols), key=lambda c: int(c.split()[1]))
            if common:
                latest_common = common[-1]
                cfo = _parse_screener_num(cfo_row.get(latest_common))
                pat = _parse_screener_num(net_profit_row.get(latest_common))
                if cfo is not None and pat is not None and pat != 0:
                    result["CFO_PAT"] = round(cfo / pat, 4)

        # ------------------------------------------------------------------
        # Bank-specific: NIM proxy + Cost-to-Income
        # ------------------------------------------------------------------
        if is_bank:
            revenue_row_bank = _find_row(profit_loss, "Revenue+")
            interest_row = _find_row(profit_loss, "Interest")
            expenses_row = _find_row(profit_loss, "Expenses+")
            total_assets_row = _find_row(balance_sheet, "Total Assets")

            if revenue_row_bank and interest_row and total_assets_row:
                rev = _latest_value(revenue_row_bank)
                interest = _latest_value(interest_row)
                total_assets = _latest_value(total_assets_row)
                if rev is not None and interest is not None and total_assets is not None and total_assets != 0:
                    result["NIM_proxy"] = round((rev - interest) / total_assets, 6)

            if expenses_row and revenue_row_bank:
                exp = _latest_value(expenses_row)
                rev2 = _latest_value(revenue_row_bank)
                if exp is not None and rev2 is not None and rev2 != 0:
                    result["Cost_to_Income"] = round(exp / rev2, 4)

        # ------------------------------------------------------------------
        # ROE history from ratios section
        # ------------------------------------------------------------------
        roe_ratio_row = _find_row(ratios, "ROE %")
        if roe_ratio_row is not None:
            result["ROE_history"] = _row_history(roe_ratio_row)
        elif roe_about is not None:
            # Fallback: single-point from about
            result["ROE_history"] = [roe_about]

        # ------------------------------------------------------------------
        # IndianAPI supplement
        # ------------------------------------------------------------------
        if has_indianapi:
            try:
                indianapi = json.loads(indianapi_path.read_text(encoding="utf-8"))
                km = indianapi.get("keyMetrics", {})

                # ROA — return on average assets
                result["ROA_indianapi"] = _indianapi_value(km, "mgmtEffectiveness", "returnOnAverageAssets")

                # 5Y revenue growth
                result["Revenue_Growth_5Y_indianapi"] = _indianapi_value(km, "growth", "revenueGrowthRate5Year")

            except Exception as exc:
                log.warning("Failed to load indianapi for %s: %s", symbol, exc)

        # ------------------------------------------------------------------
        # Coverage pct
        # ------------------------------------------------------------------
        core_populated = sum(1 for m in _CORE_METRICS if result.get(m) is not None)
        result["coverage_pct"] = round(core_populated / len(_CORE_METRICS) * 100, 1)

        return result
