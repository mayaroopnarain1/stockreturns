# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STOCKLENS_FAKE_DATA"] = "1"
os.environ["STOCKLENS_BACKEND"] = "api"

from fastapi.testclient import TestClient

from api.deps import RateLimiter, clean_ticker, clean_tickers
from api.main import app

client = TestClient(app)


class AppTests(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["fake_data"])

    def test_meta_contains_presets_and_descriptions(self):
        r = client.get("/api/meta")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("trailingPE", body["filter_presets"])
        first = body["filter_presets"]["trailingPE"][0]
        self.assertEqual(first, {"label": "Any", "min": None, "max": None})
        self.assertIn("Balanced", body["profiles"])
        self.assertTrue(body["metric_desc"])
        self.assertEqual(len(body["sector_etf"]), 11)

    def test_api_responses_not_cached(self):
        self.assertEqual(client.get("/api/health").headers.get("cache-control"), "no-store")


class ValidationTests(unittest.TestCase):
    def test_ticker_cleaning(self):
        self.assertEqual(clean_ticker(" brk.b "), "BRK.B")
        self.assertEqual(clean_ticker("^vix"), "^VIX")
        for bad in ["", "A B", "../etc", "TOOLONGTICKER1", "<script>"]:
            with self.assertRaises(Exception):
                clean_ticker(bad)

    def test_ticker_list_limits_and_dedupe(self):
        self.assertEqual(clean_tickers(["aapl", "AAPL", "msft"], limit=5), ["AAPL", "MSFT"])
        with self.assertRaises(Exception):
            clean_tickers(["A"], limit=5, minimum=2)
        with self.assertRaises(Exception):
            clean_tickers(list("ABCDEF"), limit=5)

    def test_rate_limiter(self):
        rl = RateLimiter(limit=3, window=60)
        self.assertEqual([rl.allow("ip") for _ in range(4)], [True, True, True, False])
        self.assertTrue(rl.allow("other"))


if __name__ == "__main__":
    unittest.main()
