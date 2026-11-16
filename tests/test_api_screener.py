# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STOCKLENS_FAKE_DATA"] = "1"
os.environ["STOCKLENS_BACKEND"] = "api"

from fastapi.testclient import TestClient

from api.main import app
from api.services import screener
from utils.constants import SP500_TICKERS

client = TestClient(app)


def wait_ready(timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get("/api/screener/status").json()
        if s["status"] in ("ready", "error"):
            return s
        time.sleep(0.05)
    raise AssertionError("screener build did not finish")


class ScreenerTests(unittest.TestCase):
    def setUp(self):
        screener.reset()

    def test_first_request_starts_build_then_serves_rows(self):
        first = client.get("/api/screener").json()
        self.assertIn(first["status"], {"building", "ready"})
        wait_ready()
        body = client.get("/api/screener").json()
        self.assertEqual(body["status"], "ready")
        self.assertGreater(len(body["rows"]), 400)                # S&P 500 universe (fake data)
        self.assertLessEqual(len(body["rows"]), len(SP500_TICKERS))
        row = body["rows"][0]
        for key in ("ticker", "shortName", "sector", "marketCap", "marketCapB",
                    "dividendYieldPct", "trailingPE", "returnOnEquity"):
            self.assertIn(key, row)
        self.assertTrue(body["sectors"])
        self.assertEqual(body["done"], body["total"])

    def test_derived_columns(self):
        client.get("/api/screener"); wait_ready()
        rows = client.get("/api/screener").json()["rows"]
        r = next(x for x in rows if x["dividendYield"])
        self.assertAlmostEqual(r["dividendYieldPct"], round(r["dividendYield"] * 100, 2), places=6)
        self.assertAlmostEqual(r["marketCapB"], round(r["marketCap"] / 1e9, 2), places=6)
        self.assertGreaterEqual(r["pct_below_52w_high"], 0)

    def test_no_duplicate_build_while_running_or_fresh(self):
        self.assertTrue(screener.start(__import__("api.datasource", fromlist=["data"]).data))
        self.assertFalse(screener.start(__import__("api.datasource", fromlist=["data"]).data))   # already building
        wait_ready()
        self.assertFalse(screener.start(__import__("api.datasource", fromlist=["data"]).data))   # fresh cache

    def test_forced_refresh_is_throttled(self):
        client.get("/api/screener"); wait_ready()
        r = client.post("/api/screener/refresh").json()
        self.assertFalse(r["started"])                            # < 1 h since last build

    def test_error_state_when_nothing_fetched(self):
        class Dead:
            @staticmethod
            def get_ticker_info(_):
                return {}
        screener.start(Dead(), tickers=["AAA", "BBB"])
        end = time.time() + 5
        while time.time() < end and screener.snapshot(False)["status"] == "building":
            time.sleep(0.02)
        s = screener.snapshot(False)
        self.assertEqual(s["status"], "error"); self.assertIn("rate-limiting", s["error"])
        # A later request retries instead of staying stuck in error.
        self.assertTrue(screener.start(__import__("api.datasource", fromlist=["data"]).data, tickers=["AAPL", "MSFT"]))
        wait_ready()


if __name__ == "__main__":
    unittest.main()
