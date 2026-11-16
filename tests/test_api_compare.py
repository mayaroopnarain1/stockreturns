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
from api.services.compare import best_tickers, correlation_read, format_fundamental

client = TestClient(app)
BODY = {"tickers": ["AAPL", "MSFT", "GOOGL"], "horizon": "1y", "rf": 0.05, "benchmark": True,
        "profile": "Balanced"}


class HelperTests(unittest.TestCase):
    def test_format_fundamental(self):
        self.assertEqual(format_fundamental("marketCap", 2.5e12), "$2500.0B")
        self.assertEqual(format_fundamental("returnOnEquity", 0.1534), "15.3%")
        self.assertEqual(format_fundamental("debtToEquity", 151.6), "152")
        self.assertEqual(format_fundamental("trailingPE", 22.456), "22.46")
        self.assertEqual(format_fundamental("trailingPE", None), "—")
        self.assertEqual(format_fundamental("sector", "Technology"), "Technology")

    def test_best_direction(self):
        raw = {"A": 10.0, "B": 20.0, "C": None}
        self.assertEqual(best_tickers("P/E", raw), ["A"])            # lower is better
        self.assertEqual(best_tickers("ROE", raw), ["B"])            # higher is better
        self.assertEqual(best_tickers("D/E", {"A": 50, "B": 50}), ["A", "B"])   # ties both win
        self.assertEqual(best_tickers("Market Cap", raw), [])
        self.assertEqual(best_tickers("Sector", {"A": "Tech"}), [])
        self.assertEqual(best_tickers("P/E", {"A": None}), [])

    def test_correlation_read(self):
        self.assertEqual(correlation_read(0.8), "warning")
        self.assertEqual(correlation_read(0.6), "info")
        self.assertEqual(correlation_read(0.59), "success")


class CompareEndpointTests(unittest.TestCase):
    def setUp(self):
        r = client.post("/api/compare", json=BODY)
        self.assertEqual(r.status_code, 200, r.text)
        self.b = r.json()

    def test_verdicts_per_ticker(self):
        self.assertEqual(set(self.b["verdicts"]), {"AAPL", "MSFT", "GOOGL"})
        for v in self.b["verdicts"].values():
            self.assertIn(v["verdict"], {"Buy", "Hold", "Avoid"})
            self.assertTrue(v["thesis"])

    def test_normalized_series_start_at_one(self):
        p = self.b["performance"]
        for t, ys in p["series"].items():
            self.assertAlmostEqual(ys[0], 1.0, places=9, msg=t)
            self.assertEqual(len(ys), len(p["dates"]))
        self.assertIn("SPY", p["series"])

    def test_total_return_vs_spy(self):
        rows = {r["ticker"]: r for r in self.b["performance"]["total_return"]}
        spy = rows["SPY"]["value"]
        self.assertIsNone(rows["SPY"]["vs_spy"])
        self.assertAlmostEqual(rows["AAPL"]["vs_spy"], rows["AAPL"]["value"] - spy, places=9)

    def test_risk_table_has_all_rows_and_spy(self):
        r = self.b["risk"]
        self.assertEqual(len(r["labels"]), 10)
        self.assertEqual(r["tickers"], ["AAPL", "MSFT", "GOOGL", "SPY"])
        self.assertEqual(set(r["rows"]["SPY"]), set(r["labels"]))
        self.assertEqual(len(r["scatter"]), 4)

    def test_fundamentals_best_flags(self):
        rows = {f["label"]: f for f in self.b["fundamentals"]}
        self.assertEqual(len(rows), 14)
        pe = rows["P/E"]["values"]
        best = [t for t, v in pe.items() if v["best"]]
        self.assertEqual(len(best), 1)
        self.assertEqual(pe[best[0]]["raw"], min(v["raw"] for v in pe.values()))
        self.assertFalse(any(v["best"] for v in rows["Market Cap"]["values"].values()))

    def test_correlation(self):
        c = self.b["correlation"]
        m = np.array(c["matrix"])
        np.testing.assert_allclose(np.diag(m), 1.0, atol=1e-9)
        np.testing.assert_allclose(m, m.T, atol=1e-9)
        self.assertIn(c["level"], {"warning", "info", "success"})
        self.assertNotIn("SPY", [t for t in c["tickers"] if t != "SPY"])

    def test_no_benchmark(self):
        b = client.post("/api/compare", json={**BODY, "benchmark": False}).json()
        self.assertFalse(b["benchmark"]); self.assertNotIn("SPY", b["performance"]["series"])
        self.assertTrue(all(r["vs_spy"] is None for r in b["performance"]["total_return"]))


class CompareValidationTests(unittest.TestCase):
    def post(self, **o):
        return client.post("/api/compare", json={**BODY, **o})

    def test_errors(self):
        self.assertEqual(self.post(tickers=["AAPL"]).status_code, 422)
        self.assertEqual(self.post(tickers=list("ABCDEF")).status_code, 422)         # > 5
        self.assertEqual(self.post(profile="Nope").status_code, 422)
        self.assertEqual(self.post(tickers=["AAPL", "ZZZ9"]).status_code, 422)        # only 1 valid
        body = self.post(tickers=["AAPL", "MSFT", "ZZZ9"]).json()                      # 2 valid is fine
        self.assertEqual(body["errors"], ["ZZZ9"]); self.assertEqual(body["tickers"], ["AAPL", "MSFT"])


if __name__ == "__main__":
    unittest.main()
