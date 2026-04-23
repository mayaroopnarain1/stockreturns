# -*- coding: utf-8 -*-
"""Offline tests for the EDGAR provider, concept resolver, and chain fallback."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd

from utils.providers import ticker_cik, xbrl_concepts, edgar_provider
from utils.providers.errors import ProviderNotCovered


FIX = Path(__file__).parent / "fixtures" / "edgar"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


# ---------------------------------------------------------------------------
# xbrl_concepts.resolve_series
# ---------------------------------------------------------------------------

class ResolveSeriesTests(unittest.TestCase):
    def test_annual_revenue_picks_amendment(self):
        facts = _load("companyfacts_synthetic.json")["facts"]
        rows = xbrl_concepts.resolve_series(facts, "revenue", freq="annual")

        by_end = {r["end"]: r for r in rows}
        # 2023 has both original and amendment; amendment has val=111M, higher `filed`.
        self.assertEqual(by_end["2023-12-31"]["val"], 111000000)
        self.assertEqual(by_end["2022-12-31"]["val"], 100000000)
        self.assertEqual(by_end["2024-12-31"]["val"], 120000000)
        # Q2 10-Q row is excluded from annual.
        self.assertNotIn("2024-06-30", by_end)
        # Output is oldest → newest.
        self.assertEqual([r["end"] for r in rows],
                         ["2022-12-31", "2023-12-31", "2024-12-31"])

    def test_concept_alias_fallback(self):
        """Filer with no `Revenues` tag resolves via the ASC-606 alias."""
        facts = _load("companyfacts_rev_alias.json")["facts"]
        rows = xbrl_concepts.resolve_series(facts, "revenue", freq="annual")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["val"], 80000000)
        self.assertEqual(rows[0]["end"], "2024-12-31")

    def test_missing_concept_returns_empty(self):
        facts = _load("companyfacts_rev_alias.json")["facts"]
        # No operating_income tagged on this filer.
        rows = xbrl_concepts.resolve_series(facts, "operating_income", freq="annual")
        self.assertEqual(rows, [])

    def test_shares_unit_preference(self):
        # Synthetic has no shares; this just documents the units-selection path
        # never blows up on empty inputs.
        rows = xbrl_concepts.resolve_series({}, "shares_outstanding", freq="annual")
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# edgar_provider.get_financials
# ---------------------------------------------------------------------------

class GetFinancialsTests(unittest.TestCase):
    def setUp(self):
        self.facts_payload = _load("companyfacts_synthetic.json")

    def _patch_companyfacts(self, payload):
        return mock.patch.object(
            edgar_provider, "_fetch_companyfacts", return_value=payload
        )

    def test_statements_have_yfinance_style_row_labels(self):
        with self._patch_companyfacts(self.facts_payload):
            stmts = edgar_provider.get_financials("SYN", freq="annual")

        inc = stmts["income"]
        bal = stmts["balance"]
        cf = stmts["cashflow"]

        # Row labels downstream `utils/financials.py` knows how to match.
        self.assertIn("Total Revenue", inc.index)
        self.assertIn("Net Income", inc.index)
        self.assertIn("Total Assets", bal.index)
        self.assertIn("Stockholders Equity", bal.index)
        self.assertIn("Operating Cash Flow", cf.index)
        self.assertIn("Capital Expenditure", cf.index)
        # Derived rows:
        self.assertIn("Free Cash Flow", cf.index)

    def test_columns_are_oldest_to_newest(self):
        with self._patch_companyfacts(self.facts_payload):
            stmts = edgar_provider.get_financials("SYN", freq="annual")
        cols = list(stmts["income"].columns)
        self.assertEqual(cols, sorted(cols))

    def test_capex_sign_is_flipped_to_yfinance_convention(self):
        """XBRL reports CapEx positive (a payment). yfinance convention is
        negative (a cash outflow). FCF = OCF + CapEx should work unchanged."""
        with self._patch_companyfacts(self.facts_payload):
            stmts = edgar_provider.get_financials("SYN", freq="annual")
        capex_2024 = stmts["cashflow"].loc["Capital Expenditure", pd.Timestamp("2024-12-31")]
        self.assertLess(capex_2024, 0)
        # FCF = OCF + CapEx with CapEx negative → 35M + (-9M) = 26M
        fcf_2024 = stmts["cashflow"].loc["Free Cash Flow", pd.Timestamp("2024-12-31")]
        self.assertAlmostEqual(fcf_2024, 26_000_000, places=0)

    def test_not_covered_raises_through(self):
        def _raise(_symbol):
            raise ProviderNotCovered("no CIK")
        with mock.patch.object(edgar_provider, "_fetch_companyfacts", side_effect=_raise):
            with self.assertRaises(ProviderNotCovered):
                edgar_provider.get_financials("XYZZY")


# ---------------------------------------------------------------------------
# ticker_cik mapping
# ---------------------------------------------------------------------------

class TickerCIKTests(unittest.TestCase):
    def setUp(self):
        # Clear module-level cache between tests.
        ticker_cik._cache = {}
        ticker_cik._loaded_at = 0.0

    def test_normalization_and_lookup(self):
        raw = json.loads((FIX / "company_tickers.json").read_text())
        with mock.patch(
            "utils.providers.edgar_client.get_json", return_value=raw
        ):
            self.assertEqual(ticker_cik.ticker_to_cik("aapl"), 320193)
            # BRK.B should normalize to BRK-B internally.
            self.assertEqual(ticker_cik.ticker_to_cik("BRK.B"), 1067983)

    def test_unknown_ticker_raises_not_covered(self):
        raw = json.loads((FIX / "company_tickers.json").read_text())
        with mock.patch(
            "utils.providers.edgar_client.get_json", return_value=raw
        ):
            with self.assertRaises(ProviderNotCovered):
                ticker_cik.ticker_to_cik("NVO")  # foreign issuer, not in fixture


# ---------------------------------------------------------------------------
# Chain fallback in utils/data.py — EDGAR raises → yfinance is called
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    __import__("importlib").util.find_spec("yfinance"),
    "yfinance not installed — skipping chain-fallback test",
)
class ChainFallbackTests(unittest.TestCase):
    def test_financials_falls_back_to_yfinance_when_not_covered(self):
        # Avoid importing streamlit's full caching stack — stub it out.
        import types
        st_stub = types.ModuleType("streamlit")
        st_stub.cache_data = lambda *a, **kw: (lambda f: f)
        st_stub.secrets = {}
        sys.modules["streamlit"] = st_stub

        # Must import after stubbing streamlit.
        from utils import data as data_mod

        with mock.patch.object(
            data_mod.edgar_provider, "get_financials",
            side_effect=ProviderNotCovered("nope"),
        ), mock.patch.object(
            data_mod, "_yf_financials",
            return_value={
                "income": pd.DataFrame({"x": [1]}, index=["Total Revenue"]),
                "balance": pd.DataFrame(),
                "cashflow": pd.DataFrame(),
            },
        ) as yf_fn:
            result = data_mod.get_financials("NVO", freq="annual")
            yf_fn.assert_called_once_with("NVO", "annual")
            self.assertIn("income", result)
            self.assertFalse(result["income"].empty)


# ---------------------------------------------------------------------------
# edgar_client.get_json fail-fast on rate-limit
# ---------------------------------------------------------------------------

class RateLimitFailFastTests(unittest.TestCase):
    def test_get_json_fails_fast_on_persistent_429(self):
        """On back-to-back 429s the client should raise after 2 attempts, not 3.

        This keeps the chain fallback to yfinance snappy when SEC is throttling
        us (typically because we're running without a real contact email).
        """
        from utils.providers import edgar_client
        from utils.providers.errors import ProviderRateLimited

        class _Resp:
            status_code = 429
            text = "Too Many Requests"

        calls = {"n": 0}

        def _fake_get(url, headers=None, timeout=None):
            calls["n"] += 1
            return _Resp()

        # Use a throwaway cache dir under the tests fixtures path so the
        # disk-cache doesn't short-circuit the test against a prior run.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(edgar_client.requests, "get", side_effect=_fake_get), \
                 mock.patch.object(edgar_client, "time", wraps=edgar_client.time) as tmock:
                # Stub out the sleep so the test doesn't actually wait.
                tmock.sleep = lambda _s: None
                with self.assertRaises(ProviderRateLimited):
                    edgar_client.get_json(
                        "https://data.sec.gov/fake-429",
                        cache_dir=td,
                        ttl_seconds=0,
                    )
        # Two attempts total — one initial + one retry before raising.
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
