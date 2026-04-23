# -*- coding: utf-8 -*-
"""
XBRL concept aliases and fact-series resolution.

Filers tag the same economic quantity with different US-GAAP concepts
(e.g. ``Revenues`` vs ``RevenueFromContractWithCustomerExcludingAssessedTax``).
For each canonical field, we try the alias list in order and return the first
series that resolves.

Each resolved series is a list of ``{"end", "val", "fy", "fp", "form",
"filed"}`` dicts, sorted oldest → newest, with amendments deduplicated (highest
``filed`` wins for a given (end, fp)).
"""

from __future__ import annotations

from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Canonical field -> ordered list of US-GAAP concept names to try.
# ---------------------------------------------------------------------------

CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    # Income statement
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ),
    "cost_of_revenue": (
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "tax_expense": (
        "IncomeTaxExpenseBenefit",
    ),
    "interest_expense": (
        "InterestExpense",
        "InterestExpenseDebt",
    ),
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
    ),
    "diluted_eps": (
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
    ),
    # Balance sheet (instant)
    "total_assets": ("Assets",),
    "current_assets": ("AssetsCurrent",),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ),
    "accounts_receivable": (
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
    ),
    "inventory": (
        "InventoryNet",
    ),
    "total_liabilities": ("Liabilities",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "long_term_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ),
    "short_term_debt": (
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
    ),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "shares_outstanding": (
        "CommonStockSharesOutstanding",
        "CommonStockSharesIssued",
    ),
    # Cash flow (duration)
    "operating_cf": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    # Dividends
    "dividends_per_share_declared": (
        "CommonStockDividendsPerShareDeclared",
    ),
    "dividends_per_share_cash_paid": (
        "CommonStockDividendsPerShareCashPaid",
    ),
}


# The yfinance-style row label we emit for each canonical field. Downstream
# ``utils/financials.py`` already matches on these labels case/whitespace-
# insensitively, so keeping these stable avoids touching that module.
YFINANCE_ROW_LABEL: dict[str, str] = {
    "revenue":             "Total Revenue",
    "cost_of_revenue":     "Cost Of Revenue",
    "gross_profit":        "Gross Profit",
    "operating_income":    "Operating Income",
    "pretax_income":       "Pretax Income",
    "tax_expense":         "Tax Provision",
    "interest_expense":    "Interest Expense",
    "net_income":          "Net Income",
    "diluted_eps":         "Diluted EPS",
    "total_assets":        "Total Assets",
    "current_assets":      "Current Assets",
    "cash":                "Cash And Cash Equivalents",
    "accounts_receivable": "Accounts Receivable",
    "inventory":           "Inventory",
    "total_liabilities":   "Total Liabilities Net Minority Interest",
    "current_liabilities": "Current Liabilities",
    "long_term_debt":      "Long Term Debt",
    "short_term_debt":     "Current Debt",
    "equity":              "Stockholders Equity",
    "shares_outstanding":  "Share Issued",
    "operating_cf":        "Operating Cash Flow",
    "capex":               "Capital Expenditure",
}


# Classification used to pick the right "units" branch and filing form filter.
_INSTANT_FIELDS = {
    "total_assets", "current_assets", "cash", "accounts_receivable", "inventory",
    "total_liabilities", "current_liabilities", "long_term_debt", "short_term_debt",
    "equity", "shares_outstanding",
}


def _preferred_units(field: str) -> tuple[str, ...]:
    if field == "shares_outstanding":
        return ("shares",)
    if field == "diluted_eps":
        return ("USD/shares",)
    if field in ("dividends_per_share_declared", "dividends_per_share_cash_paid"):
        return ("USD/shares",)
    return ("USD",)


def _dedupe_by_end_fp(rows: list[dict]) -> list[dict]:
    """Keep the highest ``filed`` per (end, fp) — amendments supersede originals."""
    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r.get("end", ""), r.get("fp", ""))
        prev = best.get(key)
        if prev is None or str(r.get("filed", "")) > str(prev.get("filed", "")):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r.get("end", ""), r.get("fp", "")))


def _is_annual_form(form: str | None) -> bool:
    return bool(form) and (form == "10-K" or form.startswith("10-K/"))  # 10-K, 10-K/A


def _is_quarterly_form(form: str | None) -> bool:
    return bool(form) and (
        form == "10-Q" or form.startswith("10-Q/")
        or form == "10-K" or form.startswith("10-K/")
    )


def _filter_by_freq(rows: Iterable[dict], freq: str) -> list[dict]:
    """``annual`` keeps only FY 10-K (and 10-K/A amendment) rows; ``quarterly``
    keeps Q1/Q2/Q3 from 10-Q plus FY from 10-K."""
    rows = list(rows)
    if freq == "annual":
        return [r for r in rows if r.get("fp") == "FY" and _is_annual_form(r.get("form"))]
    return [
        r for r in rows
        if _is_quarterly_form(r.get("form"))
        and r.get("fp") in ("Q1", "Q2", "Q3", "Q4", "FY")
    ]


def resolve_series(
    facts: dict[str, Any],
    field: str,
    freq: str = "annual",
) -> list[dict]:
    """Resolve a canonical field to a list of filed facts.

    ``facts`` is the top-level ``.facts`` object from a companyfacts response
    (i.e. ``response["facts"]``). Returns an empty list if no alias resolves.
    """
    aliases = CONCEPT_ALIASES.get(field, ())
    if not aliases:
        return []
    us_gaap = facts.get("us-gaap", {}) if isinstance(facts, dict) else {}
    preferred = _preferred_units(field)

    for concept in aliases:
        entry = us_gaap.get(concept)
        if not entry:
            continue
        units_map = entry.get("units", {})
        rows = None
        for u in preferred:
            if u in units_map and units_map[u]:
                rows = units_map[u]
                break
        if not rows:
            continue
        filtered = _filter_by_freq(rows, freq)
        if not filtered:
            continue
        return _dedupe_by_end_fp(filtered)
    return []
