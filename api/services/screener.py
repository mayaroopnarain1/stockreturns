# -*- coding: utf-8 -*-
"""
S&P 500 fundamentals universe, built in a background thread.

The cold fetch takes minutes against live providers, so the API never blocks
on it: the first request starts a job, clients poll for progress, and the
finished table (cached for 12 h) is returned whole so the browser can apply
the picklist filters instantly.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from api.serialize import frame_records
from utils.constants import FUNDAMENTAL_FIELDS, SP500_TICKERS

CACHE_SECONDS = 12 * 3600
MIN_REFRESH_SECONDS = 3600      # forced refresh allowed at most hourly
WORKERS = 4

_lock = threading.Lock()
_state: dict = {"status": "idle", "done": 0, "total": 0, "started": None,
                "updated": None, "error": None, "rows": None}


def reset() -> None:
    """Testing hook: forget everything."""
    with _lock:
        _state.update(status="idle", done=0, total=0, started=None, updated=None, error=None, rows=None)


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "currentPrice" in df.columns and "fiftyTwoWeekHigh" in df.columns:
        df["pct_below_52w_high"] = ((df["fiftyTwoWeekHigh"] - df["currentPrice"])
                                    / df["fiftyTwoWeekHigh"] * 100).round(1)
    df["marketCapB"] = (df["marketCap"] / 1e9).round(2)
    df["dividendYieldPct"] = (df["dividendYield"].fillna(0) * 100).round(2)
    return df


def _build(data, tickers: list[str]) -> None:
    def one(sym: str):
        try:
            info = data.get_ticker_info(sym)
        except Exception:
            info = {}
        with _lock:
            _state["done"] += 1
        if not info:
            return None
        return {"Ticker": sym, **{f: info.get(f) for f in FUNDAMENTAL_FIELDS}}

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            rows = [r for r in pool.map(one, tickers) if r]
        if not rows:
            raise RuntimeError("No fundamentals could be fetched. The data provider may be rate-limiting.")
        df = _derive(pd.DataFrame(rows).set_index("Ticker"))
        payload = frame_records(df, index_name="ticker")
        with _lock:
            _state.update(status="ready", rows=payload, updated=time.time(), error=None)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client
        with _lock:
            _state.update(status="error", error=str(exc))


def start(data, tickers: list[str] | None = None, force: bool = False) -> bool:
    """Begin a build unless one is running or fresh data exists. Returns True if started."""
    tickers = list(tickers or SP500_TICKERS)
    with _lock:
        if _state["status"] == "building":
            return False
        fresh = _state["updated"] and (time.time() - _state["updated"]) < (
            MIN_REFRESH_SECONDS if force else CACHE_SECONDS)
        if _state["status"] == "ready" and fresh:
            return False
        _state.update(status="building", done=0, total=len(tickers), started=time.time(), error=None)
    threading.Thread(target=_build, args=(data, tickers), daemon=True, name="screener-build").start()
    return True


def snapshot(include_rows: bool = True) -> dict:
    with _lock:
        out = {k: _state[k] for k in ("status", "done", "total", "updated", "error")}
        if include_rows and _state["status"] == "ready":
            out["rows"] = _state["rows"]
            out["sectors"] = sorted({r["sector"] for r in _state["rows"] if r.get("sector")})
        return out
