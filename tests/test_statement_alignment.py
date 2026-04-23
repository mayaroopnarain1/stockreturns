# -*- coding: utf-8 -*-
"""
Regression tests for the column-mismatch crash on Stock Analysis.

The EDGAR provider historically returned statements with mismatched period
axes: balance sheets carry a comparative-year instant (both prior-year and
current-year snapshots are tagged as fp=FY in a 10-K filing) that the income
and cashflow statements don't have. utils/financials.py functions like
dupont_roe combine series across statements; when pandas takes the union of
indices, ``df.columns = _period_labels(stmts)`` raises ValueError because
the label count doesn't match the DataFrame shape.

Two fixes: (1) the EDGAR provider now aligns all three statements to a
common period-end axis (shared contract with yfinance), (2) financials.py
falls back to stringifying its own column values if the statement labels
don't match in length. Either alone prevents the crash; both together are
defence in depth.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from utils.financials import (
    accruals_analysis,
    dupont_roe,
    earnings_quality,
    fcf_conversion,
    margin_decomposition,
    revenue_quality,
    roic_analysis,
)
from utils.providers import edgar_provider


FIX = Path(__file__).parent / "fixtures" / "edgar"


def _payload_with_extra_balance_year() -> dict:
    """companyfacts where balance-sheet instants include an extra comparative
    year (2022) that the income/cashflow flows do not carry."""
    return {
        "cik": 999999,
        "entityName": "ColumnMismatch Corp",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [
                        {"end": "2023-12-31", "val": 1000, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 1100, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [
                        {"end": "2023-12-31", "val": 200, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 230, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
                # Assets include BOTH a 2022 (comparative) and 2023 and 2024
                # instants — this is what EDGAR returns for a real 10-K filer.
                "Assets": {
                    "units": {"USD": [
                        {"end": "2022-12-31", "val": 4500, "fy": 2022, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2023-12-31", "val": 5000, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 5500, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [
                        {"end": "2022-12-31", "val": 2700, "fy": 2022, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2023-12-31", "val": 3000, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 3300, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [
                        {"end": "2023-12-31", "val": 300, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 350, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [
                        {"end": "2023-12-31", "val": 80, "fy": 2023, "fp": "FY",
                         "form": "10-K", "filed": "2024-02-01"},
                        {"end": "2024-12-31", "val": 90, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2025-02-01"},
                    ]}
                },
            }
        },
    }


class StatementAlignmentTests(unittest.TestCase):
    """EDGAR provider should return income/balance/cashflow with the same columns."""

    def test_balance_comparative_year_is_trimmed_to_match_income(self):
        payload = _payload_with_extra_balance_year()
        with mock.patch.object(edgar_provider, "_fetch_companyfacts", return_value=payload):
            stmts = edgar_provider.get_financials("X", freq="annual")

        self.assertEqual(list(stmts["income"].columns), list(stmts["balance"].columns))
        self.assertEqual(list(stmts["income"].columns), list(stmts["cashflow"].columns))
        # Only the 2 periods present in all three statements survive.
        self.assertEqual(len(stmts["income"].columns), 2)


class FinancialsNoCrashTests(unittest.TestCase):
    """Every analytic in utils/financials.py must complete without raising.

    Even if the EDGAR provider fails to align statements for some reason,
    the _apply_labels fallback in financials.py must keep the page rendering.
    """

    def _mismatched_stmts(self) -> dict:
        """Statements deliberately NOT aligned — balance carries an extra column."""
        inc_cols = [pd.Timestamp("2023-12-31"), pd.Timestamp("2024-12-31")]
        bal_cols = [pd.Timestamp("2022-12-31")] + inc_cols
        income = pd.DataFrame(
            [[1000, 1100], [600, 650], [400, 450], [200, 230],
             [100, 110], [50, 55], [20, 22], [150, 175], [2.5, 2.9]],
            index=["Total Revenue", "Cost Of Revenue", "Gross Profit",
                   "Operating Income", "Pretax Income", "Tax Provision",
                   "Interest Expense", "Net Income", "Diluted EPS"],
            columns=inc_cols, dtype=float,
        )
        balance = pd.DataFrame(
            [[4500, 5000, 5500], [2700, 3000, 3300], [1500, 1700, 1900],
             [500, 600, 700], [1000, 1100, 1200], [800, 900, 1000]],
            index=["Total Assets", "Stockholders Equity", "Total Liabilities Net Minority Interest",
                   "Current Liabilities", "Current Assets", "Cash And Cash Equivalents"],
            columns=bal_cols, dtype=float,
        )
        cashflow = pd.DataFrame(
            [[300, 350], [-80, -90], [220, 260]],
            index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
            columns=inc_cols, dtype=float,
        )
        return {"income": income, "balance": balance, "cashflow": cashflow}

    def test_all_analytics_survive_mismatched_columns(self):
        stmts = self._mismatched_stmts()
        # None of these should raise.
        for fn in (dupont_roe, margin_decomposition, roic_analysis,
                   revenue_quality, earnings_quality, accruals_analysis,
                   fcf_conversion):
            result = fn(stmts)
            self.assertIsInstance(result, dict, f"{fn.__name__} did not return a dict")

    def test_aligned_stmts_still_use_statement_labels(self):
        """The common case — aligned columns — should still produce the
        yfinance-style date-formatted labels."""
        mism = self._mismatched_stmts()
        # Align by trimming balance to the shared columns.
        mism["balance"] = mism["balance"].loc[:, mism["income"].columns]
        out = dupont_roe(mism)
        self.assertEqual(list(out["df"].columns), ["2023-12-31", "2024-12-31"])


if __name__ == "__main__":
    unittest.main()
