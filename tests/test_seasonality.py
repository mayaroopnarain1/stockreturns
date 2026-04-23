# -*- coding: utf-8 -*-
"""Unit tests for utils.metrics.monthly_seasonality."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd

from utils.metrics import MONTH_ABBR, monthly_seasonality


def _synthetic_prices(years: int = 12, seed: int = 0, jan_bias: float = 0.001) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2013-01-01", periods=252 * years, freq="B")
    rets = rng.normal(0, 0.005, size=len(idx))
    # Add a deterministic January lift so we can assert on it.
    rets[idx.month == 1] += jan_bias
    return 100.0 * (1 + pd.Series(rets, index=idx)).cumprod()


class MonthlySeasonalityTests(unittest.TestCase):
    def test_detects_injected_january_bias(self):
        prices = _synthetic_prices(jan_bias=0.001)
        result = monthly_seasonality(prices, lookback_years=10)
        stats = result["stats"]
        self.assertEqual(result["n_years"], 10)
        # January should be materially higher than the non-Jan average.
        jan_mean = stats.loc[1, "mean"]
        other_mean = stats.drop(index=1)["mean"].mean()
        self.assertGreater(jan_mean, other_mean + 0.005)

    def test_stats_shape_and_bounds(self):
        prices = _synthetic_prices()
        stats = monthly_seasonality(prices, lookback_years=10)["stats"]
        self.assertEqual(list(stats.index), list(range(1, 13)))
        self.assertEqual(
            set(stats.columns),
            {"mean", "median", "hit_rate", "best", "worst", "n"},
        )
        self.assertTrue(((stats["hit_rate"] >= 0) & (stats["hit_rate"] <= 1)).all())
        self.assertTrue((stats["n"] > 0).all())
        self.assertTrue((stats["best"] >= stats["worst"]).all())

    def test_empty_input_returns_empty_shape(self):
        result = monthly_seasonality(pd.Series(dtype=float))
        self.assertEqual(result["n_years"], 0)
        self.assertIsNone(result["start"])
        # Stats frame has the expected 12-row shape with NaNs.
        self.assertEqual(len(result["stats"]), 12)
        self.assertTrue(result["stats"]["n"].isna().all())

    def test_short_series_below_12_months(self):
        # Two weeks of data — below the 12-month minimum.
        idx = pd.date_range("2024-01-01", periods=10, freq="B")
        s = pd.Series(range(10), index=idx, dtype=float)
        result = monthly_seasonality(s, lookback_years=10)
        self.assertEqual(result["n_years"], 0)
        self.assertTrue(result["stats"]["n"].isna().all())

    def test_tz_aware_index_is_normalized(self):
        prices = _synthetic_prices(years=3)
        prices.index = prices.index.tz_localize("UTC")
        result = monthly_seasonality(prices, lookback_years=10)
        self.assertGreater(result["n_years"], 0)
        self.assertIsNotNone(result["start"])
        self.assertIsNone(getattr(result["start"], "tzinfo", None))

    def test_month_abbr_covers_twelve_months(self):
        self.assertEqual(len(MONTH_ABBR), 12)
        self.assertEqual(MONTH_ABBR[0], "Jan")
        self.assertEqual(MONTH_ABBR[-1], "Dec")


if __name__ == "__main__":
    unittest.main()
