# -*- coding: utf-8 -*-
"""
Thin HTTP client for SEC EDGAR.

Responsibilities:
  * Attach the SEC-required ``User-Agent`` header with a contact email.
  * Enforce the SEC fair-access rate limit (10 requests per second).
  * Gzip-decode large JSON payloads (``companyfacts`` can reach ~20 MB).
  * Persist raw JSON responses to a local disk cache so Streamlit container
    restarts and cache-evictions don't trigger a refetch.
  * Retry transiently-failing requests with exponential backoff.

The client is deliberately pure-Python (no Streamlit import) so it can be
unit-tested offline with fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .errors import ProviderNotCovered, ProviderRateLimited


EDGAR_API_BASE = "https://data.sec.gov"
EDGAR_WWW_BASE = "https://www.sec.gov"

DEFAULT_USER_AGENT = "StockLens-OSS stocklens-ops@example.org"
DEFAULT_CACHE_DIR = Path(os.environ.get("EDGAR_CACHE_DIR", ".edgar_cache"))
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 h

_RATE_LIMIT_PER_SEC = 10


class _TokenBucket:
    """Simple blocking token bucket for the 10 req/s SEC fair-access limit."""

    def __init__(self, rate_per_sec: int) -> None:
        self._interval = 1.0 / float(rate_per_sec)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = now + self._interval


_bucket = _TokenBucket(_RATE_LIMIT_PER_SEC)


def _user_agent() -> str:
    """Resolve the User-Agent header.

    Priority: ``st.secrets["edgar"]["user_agent"]`` → env var
    ``EDGAR_USER_AGENT`` → hard-coded default (works but SEC may throttle).
    The secrets lookup is wrapped so the client still imports cleanly when run
    outside Streamlit (unit tests).
    """
    try:
        import streamlit as st  # lazy — avoid hard Streamlit dep in tests
        ua = st.secrets.get("edgar", {}).get("user_agent")  # type: ignore[attr-defined]
        if ua:
            return str(ua)
    except Exception:
        pass
    return os.environ.get("EDGAR_USER_AGENT", DEFAULT_USER_AGENT)


def _cache_path(url: str, cache_dir: Path) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return cache_dir / f"{h}.json"


def _read_cache(path: Path, ttl_seconds: int) -> Any | None:
    if not path.exists():
        return None
    if ttl_seconds >= 0 and (time.time() - path.stat().st_mtime) > ttl_seconds:
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        tmp.replace(path)
    except Exception:
        pass  # disk cache is best-effort


def get_json(
    url: str,
    *,
    cache_dir: Path | str | None = None,
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    max_attempts: int = 3,
    timeout: float = 20.0,
) -> Any:
    """GET ``url`` and return parsed JSON. Cached to disk and rate-limited.

    Raises ``ProviderNotCovered`` on 404 (ticker / concept not in EDGAR).
    Raises ``ProviderRateLimited`` on persistent 429/503.
    """
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cpath = _cache_path(url, cache_dir)

    cached = _read_cache(cpath, ttl_seconds)
    if cached is not None:
        return cached

    headers = {
        "User-Agent": _user_agent(),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        _bucket.acquire()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(2 ** attempt)
            continue

        if resp.status_code == 404:
            raise ProviderNotCovered(f"EDGAR 404 for {url}")
        if resp.status_code in (429, 503):
            last_exc = ProviderRateLimited(f"EDGAR {resp.status_code} for {url}")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 500:
            last_exc = RuntimeError(f"EDGAR {resp.status_code} for {url}")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"EDGAR {resp.status_code} for {url}: {resp.text[:200]}")

        try:
            payload = resp.json()
        except ValueError as e:
            raise RuntimeError(f"EDGAR returned non-JSON for {url}") from e

        _write_cache(cpath, payload)
        return payload

    if isinstance(last_exc, ProviderRateLimited):
        raise last_exc
    raise RuntimeError(f"EDGAR request failed after {max_attempts} attempts: {last_exc}")


def company_tickers_url() -> str:
    return f"{EDGAR_WWW_BASE}/files/company_tickers.json"


def submissions_url(cik_int: int) -> str:
    return f"{EDGAR_API_BASE}/submissions/CIK{cik_int:010d}.json"


def companyfacts_url(cik_int: int) -> str:
    return f"{EDGAR_API_BASE}/api/xbrl/companyfacts/CIK{cik_int:010d}.json"
