# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STOCKLENS_FAKE_DATA"] = "1"
os.environ["STOCKLENS_BACKEND"] = "api"

import numpy as np
from fastapi.testclient import TestClient

from api.main import app
from api.services.portfolio import (diversification_level, equal_weights,
                                    inverse_vol_weights, sector_concentration)

client = TestClient(app)
BODY = {"tickers": ["AAPL", "MSFT", "KO"], "weights": [40, 35, 25], "horizon": "1y", "rf": 0.05}


class HelperTests(unittest.TestCase):
    def test_equal_weights_remainder_on_last(self):
        self.assertEqual(equal_weights(3), [33.3, 33.3, 33.4])
        self.assertEqual(equal_weights(4), [25.0] * 4)
        self.assertAlmostEqual(sum(equal_weights(7)), 100.0, places=6)

    def test_inverse_vol_weights(self):
        w = inverse_vol_weights([0.1, 0.2, 0.4])
        self.assertAlmostEqual(sum(w), 100.0, places=6)
        self.assertGreater(w[0], w[1]); self.assertGreater(w[1], w[2])   # lower vol -> bigger weight

    def test_levels(self):
        self.assertEqual(diversification_level(0.25), "well")
        self.assertEqual(diversification_level(0.10), "moderate")
        self.assertEqual(diversification_level(0.0999), "concentrated")
        rows = [{"sector": "Tech", "weight": 60.0}]
        self.assertEqual(sector_concentration(rows)["level"], "high")
        self.assertEqual(sector_concentration([{"sector": "X", "weight": 40.0}])["level"], "medium")
        self.assertEqual(sector_concentration([{"sector": "X", "weight": 39.9}])["level"], "low")


class PortfolioEndpointTests(unittest.TestCase):
    def setUp(self):
        r = client.post("/api/portfolio", json=BODY)
        self.assertEqual(r.status_code, 200, r.text)
        self.body = r.json()

    def test_risk_contributions_sum_to_100(self):
        total = sum(c["risk_contribution"] for c in self.body["contributions"])
        self.assertAlmostEqual(total, 100.0, delta=0.2)   # rounded to 2dp per holding

    def test_diversification_math(self):
        s = self.body["summary"]
        self.assertGreaterEqual(s["undiversified_vol"], s["ann_vol"] - 1e-9)   # diversification never hurts
        self.assertAlmostEqual(s["diversification_benefit"], s["undiversified_vol"] - s["ann_vol"], places=6)
        self.assertTrue(0 <= s["diversification_ratio"] <= 1)

    def test_cumulative_series_aligned_and_spy_rebased(self):
        c = self.body["cumulative"]
        n = len(c["dates"])
        self.assertEqual(len(c["portfolio"]), n)
        self.assertEqual(set(c["holdings"]), {"AAPL", "MSFT", "KO"})
        self.assertTrue(all(len(v) == n for v in c["holdings"].values()))
        self.assertEqual(len(c["spy"]), n)                      # bug fix: same length as portfolio
        # SPY starts the same way the portfolio does: 1 + first return, not a longer history.
        self.assertTrue(0.5 < c["spy"][0] < 1.5)

    def test_beta_of_spy_is_one(self):
        r = client.post("/api/portfolio", json={**BODY, "tickers": ["SPY", "XLK"], "weights": [100, 0]})
        # weights 100/0 on SPY means the portfolio IS SPY: beta ~ 1, correlation ~ 1
        b = r.json()["benchmark"]
        self.assertAlmostEqual(b["beta"], 1.0, places=6)
        self.assertAlmostEqual(b["correlation"], 1.0, places=6)
        self.assertAlmostEqual(b["excess_return"], 0.0, delta=0.5)

    def test_sectors_sum_to_100_and_sorted(self):
        rows = self.body["sectors"]["rows"]
        self.assertAlmostEqual(sum(r["weight"] for r in rows), 100.0, delta=0.2)
        self.assertEqual([r["weight"] for r in rows], sorted((r["weight"] for r in rows), reverse=True))

    def test_correlation_matrix_is_symmetric_with_unit_diagonal(self):
        m = np.array(self.body["correlation"]["matrix"])
        np.testing.assert_allclose(m, m.T, atol=1e-9)
        np.testing.assert_allclose(np.diag(m), 1.0, atol=1e-9)

    def test_alternatives_present(self):
        alts = self.body["alternatives"]
        self.assertEqual([a["ticker"] for a in alts], ["AAPL", "MSFT", "KO"])
        self.assertAlmostEqual(sum(a["equal"] for a in alts), 100.0, places=6)
        self.assertAlmostEqual(sum(a["inverse_vol"] for a in alts), 100.0, places=6)

    def test_holdings_table(self):
        self.assertEqual([h["ticker"] for h in self.body["holdings"]], ["AAPL", "MSFT", "KO"])
        self.assertEqual(self.body["holdings"][0]["weight"], 40.0)


class PortfolioValidationTests(unittest.TestCase):
    def post(self, **over):
        return client.post("/api/portfolio", json={**BODY, **over})

    def test_weights_must_sum_to_100(self):
        r = self.post(weights=[40, 35, 20])
        self.assertEqual(r.status_code, 422); self.assertIn("100", r.json()["detail"])
        self.assertEqual(self.post(weights=[40, 35, 25.4]).status_code, 200)   # within +/-0.5

    def test_bad_inputs(self):
        self.assertEqual(self.post(tickers=["AAPL"], weights=[100]).status_code, 422)
        self.assertEqual(self.post(tickers=["AAPL", "aapl", "KO"]).status_code, 422)   # duplicates
        self.assertEqual(self.post(tickers=["AAPL", "ZZZ9", "KO"]).status_code, 422)   # no data
        self.assertIn("ZZZ9", self.post(tickers=["AAPL", "ZZZ9", "KO"]).json()["detail"])
        self.assertEqual(self.post(horizon="7y").status_code, 422)
        self.assertEqual(self.post(rf=0.5).status_code, 422)
        self.assertEqual(self.post(weights=[-10, 60, 50]).status_code, 422)
        self.assertEqual(self.post(tickers=[f"T{i}" for i in range(16)], weights=[1] * 16).status_code, 422)


if __name__ == "__main__":
    unittest.main()
