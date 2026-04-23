# -*- coding: utf-8 -*-
"""Tests for utils.dividends compute functions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd

from utils.dividends import (
    dividend_cagr,
    dividend_history,
    dividend_streak,
    summarize,
    yield_stats,
)


def _rising_dps(n: int = 10, start: float = 1.00, g: float = 0.08) -> pd.Series:
    yrs = pd.date_range("2016-12-31", periods=n, freq="YE")
    return pd.Series([start * (1 + g) ** i for i in range(n)], index=yrs)


def _eps_stmts(yrs: pd.DatetimeIndex, vals: list[float]) -> dict:
    df = pd.DataFrame({ts: [v] for ts, v in zip(yrs, vals)}, index=["Diluted EPS"])
    return {"income": df, "balance": pd.DataFrame(), "cashflow": pd.DataFrame()}


class DividendHistoryTests(unittest.TestCase):
    def test_payout_ratio_and_yoy(self):
        dps = _rising_dps(n=5, start=1.00, g=0.10)
        eps = _eps_stmts(dps.index, [4.00, 4.20, 4.40, 4.50, 4.80])
        df = dividend_history(eps, dps)
        self.assertEqual(list(df.columns), ["DPS", "EPS", "PayoutRatio", "YoY"])
        self.assertTrue(np.isnan(df["YoY"].iloc[0]))  # first year has no YoY
        self.assertAlmostEqual(df["YoY"].iloc[1], 0.10, places=4)
        self.assertAlmostEqual(df["PayoutRatio"].iloc[0], 1.00 / 4.00, places=4)

    def test_handles_missing_eps(self):
        dps = _rising_dps(n=3)
        df = dividend_history({}, dps)  # no statements -> EPS is NaN
        self.assertTrue(df["EPS"].isna().all())
        self.assertTrue(df["PayoutRatio"].isna().all())

    def test_payout_clipped_for_loss_year(self):
        dps = pd.Series([1.00, 1.00], index=pd.date_range("2022-12-31", periods=2, freq="YE"))
        eps = _eps_stmts(dps.index, [4.00, 0.30])  # tiny EPS -> unclipped ratio ~3.3
        df = dividend_history(eps, dps)
        # Clipped to 2.0 upper bound.
        self.assertLessEqual(df["PayoutRatio"].iloc[-1], 2.0)


class DividendCAGRTests(unittest.TestCase):
    def test_cagr_matches_constructed_growth(self):
        dps = _rising_dps(n=6, start=1.00, g=0.08)  # 5-year span
        self.assertAlmostEqual(dividend_cagr(dps, 5), 0.08, places=4)

    def test_returns_nan_with_too_little_history(self):
        dps = _rising_dps(n=3)
        self.assertTrue(np.isnan(dividend_cagr(dps, 5)))

    def test_returns_nan_on_zero_start(self):
        yrs = pd.date_range("2016-12-31", periods=6, freq="YE")
        dps = pd.Series([0.0, 1.0, 1.1, 1.2, 1.3, 1.4], index=yrs)
        self.assertTrue(np.isnan(dividend_cagr(dps, 5)))


class DividendStreakTests(unittest.TestCase):
    def test_full_rising_streak(self):
        self.assertEqual(dividend_streak(_rising_dps(n=10)), 9)

    def test_breaks_on_cut(self):
        dps = _rising_dps(n=6)
        vals = dps.values.copy()
        vals[3] = vals[2] - 0.10  # cut in year 4
        dps = pd.Series(vals, index=dps.index)
        # From end going backwards: 5>=4 ✓, 4>=3 ✓, 3<2 ✗ → streak=2
        self.assertEqual(dividend_streak(dps), 2)

    def test_single_year_returns_zero(self):
        dps = pd.Series([1.0], index=pd.date_range("2024-12-31", periods=1, freq="YE"))
        self.assertEqual(dividend_streak(dps), 0)


class YieldStatsTests(unittest.TestCase):
    def test_current_yield_and_avg(self):
        dps = _rising_dps(n=6, start=1.00, g=0.08)
        close = pd.Series(
            [50, 55, 60, 65, 70, 75],
            index=pd.date_range("2016-12-30", periods=6, freq="YE"),
        )
        ys = yield_stats(100.0, dps, close, lookback_years=5)
        self.assertAlmostEqual(ys["current_yield"], dps.iloc[-1] / 100.0)
        self.assertEqual(ys["n_years"], 5)
        self.assertTrue(0 <= ys["percentile"] <= 1)

    def test_no_price_history_keeps_current_yield(self):
        dps = _rising_dps(n=3)
        ys = yield_stats(50.0, dps, None)
        self.assertAlmostEqual(ys["current_yield"], dps.iloc[-1] / 50.0)
        self.assertTrue(np.isnan(ys["avg_yield"]))

    def test_missing_inputs_return_nan(self):
        ys = yield_stats(None, pd.Series(dtype=float), None)
        self.assertTrue(np.isnan(ys["current_yield"]))
        self.assertEqual(ys["n_years"], 0)


class SummarizeTests(unittest.TestCase):
    def test_empty_inputs_return_empty_history(self):
        out = summarize({}, pd.Series(dtype=float), None, None)
        self.assertTrue(out["history"].empty)
        self.assertEqual(out["streak"], 0)
        self.assertTrue(np.isnan(out["latest_payout"]))

    def test_end_to_end_structure(self):
        dps = _rising_dps(n=6)
        stmts = _eps_stmts(dps.index, [4.0, 4.2, 4.4, 4.5, 4.8, 5.0])
        close = pd.Series(
            [50, 55, 60, 65, 70, 75],
            index=pd.date_range("2016-12-30", periods=6, freq="YE"),
        )
        out = summarize(stmts, dps, 100.0, close)
        self.assertEqual(
            set(out.keys()),
            {"history", "cagr_3y", "cagr_5y", "cagr_10y", "streak", "latest_payout", "yield"},
        )
        self.assertFalse(out["history"].empty)
        self.assertGreater(out["streak"], 0)


if __name__ == "__main__":
    unittest.main()
