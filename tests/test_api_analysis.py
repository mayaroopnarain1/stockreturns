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

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api import fake
from api.main import app
from api.services import screener
from api.services.analysis import score_band, tnx_label, vix_label
from utils.metrics import compute_return_metrics, rsi

client = TestClient(app)


def get(ticker, ep, **params):
    r = client.get(f"/api/analysis/{ticker}/{ep}", params=params)
    assert r.status_code == 200, (ep, r.status_code, r.text)
    return r.json()


class LabelTests(unittest.TestCase):
    def test_bands_and_labels(self):
        self.assertEqual([score_band(s) for s in (70, 69.9, 55, 45, 30, 29.9)],
                         ["Strong", "Solid", "Solid", "Fair", "Weak", "Poor"])
        self.assertEqual((vix_label(14.9), vix_label(25), vix_label(25.1)), ("Calm", "Moderate", "Elevated"))
        self.assertEqual((tnx_label(2.9), tnx_label(4), tnx_label(5.1)), ("Accommodative", "Neutral", "Restrictive"))


class OverviewTests(unittest.TestCase):
    def test_hero_matches_price_data(self):
        b = get("AAPL", "overview")
        close = fake.get_price_history("AAPL", "1y")["Close"]
        self.assertAlmostEqual(b["hero"]["price"], close.iloc[-1])
        self.assertAlmostEqual(b["hero"]["day_change_abs"], close.iloc[-1] - close.iloc[-2])
        self.assertEqual(len(b["dimensions"]), 4)
        self.assertTrue(all(d["band"] in {"Strong", "Solid", "Fair", "Weak", "Poor"} for d in b["dimensions"]))
        self.assertAlmostEqual(b["key_stats"]["total_return"],
                               compute_return_metrics(close, 0.05)["total_return"])

    def test_profile_changes_the_verdict_weights(self):
        bal = get("AAPL", "overview", profile="Balanced")["prescription"]
        val = get("AAPL", "overview", profile="Value")["prescription"]
        self.assertNotEqual(bal["weights"], val["weights"])
        self.assertEqual(val["profile"], "Value")

    def test_custom_range_and_errors(self):
        b = get("AAPL", "overview", horizon="custom", start="2025-01-02", end="2025-06-30")
        self.assertTrue(b["hero"]["price"] > 0)
        self.assertEqual(client.get("/api/analysis/AAPL/overview?horizon=custom&start=2025-06-30&end=2025-01-02").status_code, 422)
        self.assertEqual(client.get("/api/analysis/AAPL/overview?profile=Nope").status_code, 422)
        self.assertEqual(client.get("/api/analysis/ZZZ9/overview").status_code, 404)
        self.assertEqual(client.get("/api/analysis/bad%20ticker/overview").status_code, 422)
        self.assertEqual(client.get("/api/analysis/AAPL/overview?horizon=7y").status_code, 422)


class TechnicalsRiskTests(unittest.TestCase):
    def test_series_lengths_and_rsi_parity(self):
        b = get("MSFT", "technicals")
        n = len(b["dates"])
        for k, v in b["series"].items():
            self.assertEqual(len(v), n, k)
        close = fake.get_price_history("MSFT", "1y")["Close"]
        expected = rsi(close).dropna().iloc[-1]
        self.assertAlmostEqual([x for x in b["series"]["rsi"] if x is not None][-1], expected)
        self.assertIn(b["direction"], {"Bullish", "Bearish", "Neutral"})
        self.assertTrue(all(len(s) == 3 for s in b["signals"]))

    def test_short_history_is_flagged_not_crashed(self):
        b = get("MSFT", "technicals", horizon="custom", start="2026-10-01", end="2026-11-10")
        self.assertTrue(b["insufficient"])

    def test_risk_metrics_parity_and_histogram(self):
        b = get("KO", "risk", rf=0.03, rolling=21)
        close = fake.get_price_history("KO", "1y")["Close"]
        m = compute_return_metrics(close, 0.03)
        self.assertAlmostEqual(b["metrics"]["sharpe"], m["sharpe"])
        self.assertAlmostEqual(b["metrics"]["max_drawdown"], m["max_drawdown"])
        self.assertNotIn("daily_ret", b["metrics"])                       # series stripped
        h = b["histogram"]
        self.assertEqual(sum(h["counts"]), len(m["daily_ret_pct"]))      # every return binned once
        self.assertEqual(len(h["edges"]), 51)
        self.assertEqual(len(h["normal"]["x"]), 200)
        self.assertEqual(b["rolling_window"], 21)
        self.assertEqual(client.get("/api/analysis/KO/risk?rolling=45").status_code, 422)


class EventsTests(unittest.TestCase):
    def setUp(self):
        self.b = get("AAPL", "events", horizon="2y")

    def test_events_sit_on_trading_days_with_matching_price(self):
        price = dict(zip(self.b["price"]["x"], self.b["price"]["y"]))
        kinds = {e["type"] for e in self.b["events"]}
        self.assertIn("earnings", kinds)
        for e in self.b["events"]:
            self.assertIn(e["date"], price)
            self.assertAlmostEqual(e["price"], price[e["date"]])

    def test_outliers_respect_threshold(self):
        loose = get("AAPL", "events", horizon="5y", outlier_z=2.0)
        tight = get("AAPL", "events", horizon="5y", outlier_z=4.0)
        n = lambda b: sum(e["type"] == "outlier" for e in b["events"])
        self.assertGreaterEqual(n(loose), n(tight))
        self.assertTrue(all(abs(e["return_pct"]) > 0 for e in loose["events"] if e["type"] == "outlier"))

    def test_top_moves_sorted_by_magnitude(self):
        mags = [abs(m["return_pct"]) for m in self.b["top_moves"]]
        self.assertEqual(len(mags), 10)
        self.assertEqual(mags, sorted(mags, reverse=True))

    def test_dividend_markers_for_a_payer(self):
        payer = next(t for t in ("KO", "JNJ", "PG", "XOM", "T", "VZ") if not fake.get_dividends(t, "10y").empty)
        b = get(payer, "events", horizon="10y")
        divs = [e for e in b["events"] if e["type"] == "dividend"]
        self.assertGreaterEqual(len(divs), 5)
        self.assertTrue(all(e["label"].startswith("Dividend $") for e in divs))
        price = dict(zip(b["price"]["x"], b["price"]["y"]))
        self.assertTrue(all(abs(e["price"] - price[e["date"]]) < 1e-9 for e in divs))

    def test_next_earnings_is_future(self):
        ne = self.b["next_earnings"]
        self.assertGreaterEqual(ne["days_until"], 0)

    def test_relative_to_sector_starts_at_one(self):
        b = get("AAPL", "events", relative="true")
        self.assertTrue(b["relative"]); self.assertIn("/", b["label"])
        self.assertAlmostEqual(b["price"]["y"][0], 1.0, places=9)
        self.assertFalse(get("AAPL", "events")["relative"])

    def test_seasonality_structure(self):
        s = self.b["seasonality"]
        self.assertTrue(s["available"])
        names = [r["series"] for r in s["rows"]]
        self.assertEqual(names[0], "AAPL"); self.assertIn("SPY", names); self.assertEqual(names[-1], "AAPL − SPY")
        self.assertTrue(all(len(r["months"]) == 12 for r in s["rows"]))
        spy = next(r for r in s["rows"] if r["series"] == "SPY")["months"]
        me = s["rows"][0]["months"]; ex = s["rows"][-1]["months"]
        for a, b_, c in zip(me, spy, ex):
            self.assertAlmostEqual(c["mean"], a["mean"] - b_["mean"], places=12)
        self.assertGreater(s["headline"]["years"], 5)
        self.assertGreaterEqual(s["headline"]["best_mean"], s["headline"]["worst_mean"])


class FundamentalsTests(unittest.TestCase):
    def test_no_context_by_default(self):
        b = get("AAPL", "fundamentals")
        self.assertFalse(b["context"]["available"])
        self.assertEqual(len(b["valuation"]), 6); self.assertEqual(len(b["quality"]), 6)
        self.assertEqual(len(b["growth"]), 3)
        self.assertTrue(all(v["delta"] is None for v in b["valuation"]))

    def test_sector_context_uses_screener_universe(self):
        screener.reset()
        client.get("/api/screener")
        end = time.time() + 20
        while time.time() < end and screener.snapshot(False)["status"] != "ready":
            time.sleep(0.05)
        b = get("AAPL", "fundamentals", context="true")
        self.assertTrue(b["context"]["available"], b["context"])
        pe = next(v for v in b["valuation"] if v["key"] == "trailingPE")
        self.assertIsNotNone(pe["sector_median"])
        self.assertAlmostEqual(pe["delta"], (pe["value"] - pe["sector_median"]) / pe["sector_median"] * 100)
        roe = next(v for v in b["quality"] if v["key"] == "returnOnEquity")
        self.assertEqual(roe["delta_unit"], "pp")
        self.assertAlmostEqual(roe["delta"], (roe["value"] - roe["sector_median"]) * 100)
        for p in b["context"]["percentiles"]:
            self.assertTrue(0 < p["percentile"] <= 100)
        self.assertLessEqual(len(b["context"]["peers"]), 4)
        self.assertNotIn("AAPL", b["context"]["peers"])

    def test_dividend_panel_for_payers_only(self):
        payer = next(t for t in ("KO", "JNJ", "PG", "XOM", "T", "VZ") if not fake.get_dividends(t, "10y").empty)
        d = get(payer, "fundamentals")["dividends"]
        self.assertGreaterEqual(len(d["history"]), 5)
        self.assertTrue(all(h["year"] >= 2010 for h in d["history"]))
        self.assertGreaterEqual(d["streak"], 0)
        self.assertIsNotNone(d["yield"]["current_yield"])
        non = next(t for t in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ORCL", "AMD", "KO")
                   if fake.get_dividends(t, "10y").empty)
        self.assertIsNone(get(non, "fundamentals")["dividends"])


class FinancialsTests(unittest.TestCase):
    def test_all_sections_present_and_aligned(self):
        b = get("MSFT", "financials")
        self.assertTrue(b["available"])
        self.assertEqual(len(b["periods"]), 5)
        for k in ("dupont", "margins", "roic", "revenue_quality", "earnings_quality", "accruals", "fcf"):
            self.assertIsNotNone(b[k], k)
            self.assertEqual(b[k]["table"]["columns"], b["periods"], k)
        self.assertIn(b["dupont"]["driver"], {"Net Margin", "Asset Turnover", "Equity Multiplier", "—"})
        self.assertEqual(set(b["leverage"]["metrics"]), set(b["leverage"]["bands"]))
        sc = b["scorecard"]
        self.assertEqual(set(sc), {"profitability", "earnings_quality", "balance_sheet"})
        self.assertTrue(all(0 <= v["score"] <= 100 for v in sc.values() if v["score"] is not None))

    def test_quarterly(self):
        b = get("MSFT", "financials", freq="quarterly")
        self.assertEqual(len(b["periods"]), 8)

    def test_unavailable_for_etf_and_bad_freq(self):
        self.assertFalse(get("SPY", "financials")["available"])
        self.assertEqual(client.get("/api/analysis/MSFT/financials?freq=weekly").status_code, 422)

    def test_one_failing_analytic_does_not_break_the_tab(self):
        from api.services import analysis_fund as F
        orig = F.dupont_roe
        F.dupont_roe = lambda s: (_ for _ in ()).throw(ValueError("boom"))
        try:
            b = get("MSFT", "financials")
        finally:
            F.dupont_roe = orig
        self.assertIsNone(b["dupont"]); self.assertIsNotNone(b["roic"])


if __name__ == "__main__":
    unittest.main()
