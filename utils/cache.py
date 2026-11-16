# -*- coding: utf-8 -*-
"""
Framework-free TTL cache.

Replaces ``st.cache_data`` so ``utils.data`` can be imported by both the
Streamlit app and the FastAPI service. In-process only; thread-safe; keyed by
the repr of the call arguments so unhashable arguments (lists) work.
"""

from __future__ import annotations

import functools
import re
import threading
import time
from typing import Any, Callable

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_ttl(ttl: str | int | float | None) -> float | None:
    """Accept seconds or strings like ``"30m"``, ``"6h"``, ``"2d"``. None = no expiry."""
    if ttl is None:
        return None
    if isinstance(ttl, (int, float)):
        return float(ttl)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd])\s*", str(ttl))
    if not m:
        raise ValueError(f"Invalid TTL: {ttl!r}")
    return float(m.group(1)) * _UNITS[m.group(2)]


def ttl_cache(ttl: str | int | float | None = None, max_entries: int = 2048) -> Callable:
    """Decorator caching a function's return value for ``ttl``.

    The cached value is returned by reference (like ``st.cache_data`` with
    copies disabled), so callers must not mutate results in place. Exceptions
    are never cached. ``fn.cache_clear()`` empties the cache.
    """
    ttl_s = parse_ttl(ttl)

    def decorator(fn: Callable) -> Callable:
        store: dict[str, tuple[float, Any]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = repr((args, sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
                if hit is not None and (ttl_s is None or now - hit[0] < ttl_s):
                    return hit[1]
            value = fn(*args, **kwargs)
            with lock:
                if len(store) >= max_entries:
                    # Drop the oldest entry; simple and good enough here.
                    oldest = min(store, key=lambda k: store[k][0])
                    store.pop(oldest, None)
                store[key] = (time.monotonic(), value)
            return value

        def cache_clear() -> None:
            with lock:
                store.clear()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        return wrapper

    return decorator


def cache_data(ttl: str | int | float | None = None) -> Callable:
    """Cache decorator that adapts to its host.

    * Under the Streamlit app: delegates to ``st.cache_data`` so behaviour
      (value copies, per-session invalidation, UI integration) is unchanged.
    * Anywhere else (the FastAPI service, tests, scripts), or when the
      environment variable ``STOCKLENS_BACKEND=api`` is set: uses the
      framework-free :func:`ttl_cache`, so Streamlit is not required.
    """
    import os

    if os.environ.get("STOCKLENS_BACKEND", "").lower() != "api":
        try:
            import streamlit as st  # noqa: WPS433 - optional dependency

            return st.cache_data(show_spinner=False, ttl=ttl)
        except Exception:
            pass
    return ttl_cache(ttl)
