# -*- coding: utf-8 -*-
"""Tests for the framework-free TTL cache."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from utils.cache import parse_ttl, ttl_cache


class ParseTTLTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_ttl("30m"), 1800)
        self.assertEqual(parse_ttl("6h"), 21600)
        self.assertEqual(parse_ttl("2d"), 172800)
        self.assertEqual(parse_ttl(90), 90.0)
        self.assertIsNone(parse_ttl(None))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_ttl("soon")


class TTLCacheTests(unittest.TestCase):
    def test_caches_and_keys_by_args(self):
        calls = []

        @ttl_cache("1h")
        def f(x, y=0):
            calls.append((x, y))
            return x + y

        self.assertEqual(f(1, y=2), 3)
        self.assertEqual(f(1, y=2), 3)
        self.assertEqual(f(2), 2)
        self.assertEqual(len(calls), 2)

    def test_unhashable_arguments_work(self):
        calls = []

        @ttl_cache("1h")
        def total(items):
            calls.append(1)
            return sum(items)

        self.assertEqual(total([1, 2, 3]), 6)
        self.assertEqual(total([1, 2, 3]), 6)
        self.assertEqual(len(calls), 1)

    def test_expires(self):
        calls = []

        @ttl_cache(0.05)
        def f():
            calls.append(1)
            return len(calls)

        self.assertEqual(f(), 1)
        time.sleep(0.08)
        self.assertEqual(f(), 2)

    def test_exceptions_not_cached(self):
        calls = []

        @ttl_cache("1h")
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return "ok"

        with self.assertRaises(RuntimeError):
            flaky()
        self.assertEqual(flaky(), "ok")

    def test_cache_clear_and_eviction(self):
        calls = []

        @ttl_cache("1h", max_entries=2)
        def f(x):
            calls.append(x)
            return x

        f(1); f(2); f(3)          # evicts the oldest entry
        self.assertEqual(len(calls), 3)
        f.cache_clear()
        f(3)
        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
