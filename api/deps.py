# -*- coding: utf-8 -*-
"""Request validation helpers and the per-IP rate limiter."""

from __future__ import annotations

import re
import threading
import time

from fastapi import HTTPException

TICKER_RE = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-=]{0,9}$")
MAX_COMPARE = 5
MAX_PORTFOLIO = 15
MAX_WATCHLIST = 50
VALID_HORIZONS = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y"}


def clean_ticker(raw: str) -> str:
    t = (raw or "").strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {raw!r}")
    return t


def clean_tickers(raw: list[str], limit: int, minimum: int = 0) -> list[str]:
    seen: list[str] = []
    for r in raw:
        t = clean_ticker(r)
        if t not in seen:
            seen.append(t)
    if len(seen) < minimum:
        raise HTTPException(status_code=422, detail=f"Provide at least {minimum} tickers")
    if len(seen) > limit:
        raise HTTPException(status_code=422, detail=f"At most {limit} tickers allowed")
    return seen


def clean_horizon(h: str) -> str:
    if h not in VALID_HORIZONS:
        raise HTTPException(status_code=422, detail=f"Invalid horizon: {h!r}")
    return h


def clean_rf(rf: float) -> float:
    if not (0.0 <= rf <= 0.20):
        raise HTTPException(status_code=422, detail="Risk-free rate must be between 0 and 0.20")
    return rf


class RateLimiter:
    """Sliding-window limiter: ``limit`` requests per ``window`` seconds per key."""

    def __init__(self, limit: int = 240, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 5000:  # bound memory under many distinct IPs
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    self._hits.pop(k, None)
            return True
