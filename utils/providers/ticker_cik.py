# -*- coding: utf-8 -*-
"""Ticker → CIK lookup backed by SEC's ``company_tickers.json``."""

from __future__ import annotations

import threading
import time
from typing import Any

from . import edgar_client
from .errors import ProviderNotCovered


_lock = threading.Lock()
_cache: dict[str, int] = {}
_loaded_at: float = 0.0
_MEMORY_TTL_SECONDS = 24 * 60 * 60  # refresh in-process map once per day


def _normalize(ticker: str) -> str:
    """Match EDGAR's canonical form — uppercase, '.' → '-' (e.g. BRK.B → BRK-B)."""
    return ticker.strip().upper().replace(".", "-")


def _build(raw: Any) -> dict[str, int]:
    """company_tickers.json is a dict of "0": {"cik_str":..., "ticker":...}, ..."""
    out: dict[str, int] = {}
    if isinstance(raw, dict):
        items = raw.values()
    else:
        items = raw  # defensive; format may evolve
    for row in items:
        try:
            t = _normalize(str(row["ticker"]))
            cik = int(row["cik_str"])
            out[t] = cik
        except (KeyError, TypeError, ValueError):
            continue
    return out


def load_ticker_cik_map() -> dict[str, int]:
    """Return an in-memory map, refreshing from disk/network at most once a day."""
    global _cache, _loaded_at
    with _lock:
        if _cache and (time.time() - _loaded_at) < _MEMORY_TTL_SECONDS:
            return _cache
        raw = edgar_client.get_json(
            edgar_client.company_tickers_url(),
            ttl_seconds=edgar_client.TICKERMAP_TTL_SECONDS,
        )
        _cache = _build(raw)
        _loaded_at = time.time()
        return _cache


def ticker_to_cik(ticker: str) -> int:
    """Resolve ticker → CIK or raise ``ProviderNotCovered``."""
    m = load_ticker_cik_map()
    norm = _normalize(ticker)
    if norm in m:
        return m[norm]
    # Try without class suffix — "BF-B" → match on "BF" is not correct, but
    # EDGAR occasionally lists only the primary class. Keep strict for now.
    raise ProviderNotCovered(f"No CIK found for ticker {ticker!r}")
