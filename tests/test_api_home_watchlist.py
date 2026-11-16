# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STOCKLENS_FAKE_DATA"] = "1"
os.environ["STOCKLENS_BACKEND"] = "api"

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from api.services.common import rsi_bucket, target_status
from api.services.home import top_movers, vix_regime
from api.services.watchlist import build_alerts

client = TestClient(app)


class CommonTests(unittest.TestCase):
    def test_target_status_thresholds(self):
        self.assertEqual(target_status(None, 100), (None, "no_data"))
        self.assertEqual(target_status(100, None), (None, "none"))
        self.assertEqual(target_status(100, 0), (None, "none"))
        self.assertEqual(target_status(110, 100)[1], "hit")
        self.assertEqual(target_status(100, 100)[1], "hit")          # equal counts as hit
        self.assertEqual(target_status(96, 100)[1], "near")          # -4%
        self.assertEqual(target_status(95, 100)[1], "near")          # exactly -5%
        self.assertEqual(target_status(94.9, 100)[1], "below")

    def test_rsi_bucket(self):
        self.assertEqual(rsi_bucket(None)["label"], None)
        self.assertEqual(rsi_bucket(70)["label"], "Overbought")
        self.assertEqual(rsi_bucket(30)["label"], "Oversold")
        self.assertEqual(rsi_bucket(50)["label"], "Neutral")


class HomeTests(unittest.TestCase):
    def test_vix_regime(self):
        self.assertEqual(vix_regime(None)["label"], "—")
        self.assertEqual(vix_regime(14.9)["label"], "Calm")
        self.assertEqual(vix_regime(15)["label"], "Normal")
        self.assertEqual(vix_regime(20)["label"], "Elevated")
        self.assertEqual(vix_regime(30)["label"], "Stressed")

    def test_top_movers_order(self):
        df = pd.DataFrame({"price": [1.0] * 6, "change_pct": [3, -2, 5, 0, -4, 1]},
                          index=list("ABCDEF"))
        m = top_movers(df, n=2)
        self.assertEqual([r["ticker"] for r in m["gainers"]], ["C", "A"])
        self.assertEqual([r["ticker"] for r in m["losers"]], ["E", "B"])  # most negative first

    def test_endpoint_shape(self):
        body = client.get("/api/home").json()
        self.assertEqual([m["symbol"] for m in body["macro"]], ["SPY", "^VIX", "^TNX"])
        self.assertEqual(len(body["sectors"]["tiles"]), 11)
        self.assertEqual(len(body["sectors"]["leaders"]), 3)
        self.assertEqual(len(body["movers"]["gainers"]), 5)
        self.assertGreaterEqual(body["movers"]["gainers"][0]["change_pct"],
                                body["movers"]["gainers"][-1]["change_pct"])
        self.assertIn(body["regime"]["label"], {"Calm", "Normal", "Elevated", "Stressed"})


class WatchlistTests(unittest.TestCase):
    def test_alert_grouping(self):
        rows = [
            {"ticker": "A", "status": "hit", "rsi": {"label": "Neutral"}, "days_to_earnings": None, "next_earnings": None},
            {"ticker": "B", "status": "near", "rsi": {"label": "Overbought"}, "days_to_earnings": 3, "next_earnings": "2026-01-04"},
            {"ticker": "C", "status": "below", "rsi": {"label": "Oversold"}, "days_to_earnings": 12, "next_earnings": "2026-01-13"},
            {"ticker": "D", "status": "none", "rsi": {"label": None}, "days_to_earnings": 0, "next_earnings": "2026-01-01"},
        ]
        a = build_alerts(rows)
        self.assertEqual(a["target_hit"], ["A"])
        self.assertEqual(a["near_target"], ["B"])
        self.assertEqual(a["overbought"], ["B"])
        self.assertEqual(a["oversold"], ["C"])
        self.assertEqual([e["ticker"] for e in a["earnings_soon"]], ["B", "D"])  # 0..7 days inclusive

    def test_status_endpoint(self):
        today = dt.date.today().isoformat()
        body = client.post("/api/watchlist/status", json={"items": [
            {"ticker": "aapl", "target_price": 1.0, "added_date": today, "notes": "core"},
            {"ticker": "MSFT", "target_price": None, "added_date": "not-a-date"},
        ]}).json()
        rows = {r["ticker"]: r for r in body["rows"]}
        self.assertEqual(set(rows), {"AAPL", "MSFT"})
        self.assertEqual(rows["AAPL"]["status"], "hit")           # target of $1 is far below price
        self.assertEqual(rows["AAPL"]["notes"], "core")
        self.assertEqual(rows["MSFT"]["status"], "none")
        self.assertEqual(rows["MSFT"]["days_tracked"], 0)         # bad date falls back to today
        self.assertIsNotNone(rows["AAPL"]["rsi"]["value"])
        self.assertIsNotNone(rows["AAPL"]["range_52w"])
        self.assertIn("AAPL", body["alerts"]["target_hit"])

    def test_empty_and_invalid(self):
        self.assertEqual(client.post("/api/watchlist/status", json={"items": []}).json()["rows"], [])
        self.assertEqual(client.post("/api/watchlist/status", json={"items": [{"ticker": "bad ticker"}]}).status_code, 422)

    def test_validate_endpoint(self):
        ok = client.post("/api/watchlist/validate", json={"ticker": "aapl"}).json()
        self.assertTrue(ok["valid"]); self.assertEqual(ok["ticker"], "AAPL")
        self.assertFalse(client.post("/api/watchlist/validate", json={"ticker": "ZZZ9"}).json()["valid"])

    def test_quotes_endpoint(self):
        body = client.post("/api/quotes", json={"tickers": ["AAPL", "MSFT", "ZZZ9"]}).json()
        self.assertEqual([q["ticker"] for q in body["quotes"]], ["AAPL", "MSFT"])


if __name__ == "__main__":
    unittest.main()
