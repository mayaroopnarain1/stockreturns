# -*- coding: utf-8 -*-
"""
Persistent watchlist storage.

Stores tracked tickers + optional price targets + added-date in a local
JSON file next to the app (`.watchlist.json`). Deliberately chosen over
st.session_state because session state does not survive app restarts.

Shape of the stored file:
{
  "items": [
    {"ticker": "AAPL", "target_price": 200.0, "added_date": "2026-04-16", "notes": ""},
    ...
  ]
}
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

# Store the file alongside the app entrypoint (parent of utils/)
_WATCHLIST_PATH = Path(__file__).resolve().parent.parent / ".watchlist.json"


def _load_raw() -> dict:
    if not _WATCHLIST_PATH.exists():
        return {"items": []}
    try:
        with open(_WATCHLIST_PATH, "r") as f:
            data = json.load(f)
        if "items" not in data or not isinstance(data["items"], list):
            return {"items": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"items": []}


def _save_raw(data: dict) -> None:
    try:
        with open(_WATCHLIST_PATH, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except OSError:
        # Non-writable filesystem (e.g. hosted demo) — fail silently; session
        # state inside Streamlit can still hold the working copy.
        pass


def load_watchlist() -> list[dict]:
    """Return the list of watched items (dicts). Empty list if none."""
    return _load_raw().get("items", [])


def save_watchlist(items: list[dict]) -> None:
    """Overwrite the watchlist with the provided list of dicts."""
    _save_raw({"items": items})


def add_ticker(ticker: str, target_price: float | None = None, notes: str = "") -> bool:
    """Add a ticker. Returns True if added, False if already present."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    items = load_watchlist()
    if any(it.get("ticker") == ticker for it in items):
        # Already exists — update target if a new one was provided
        if target_price is not None:
            for it in items:
                if it.get("ticker") == ticker:
                    it["target_price"] = float(target_price)
            save_watchlist(items)
        return False
    items.append({
        "ticker": ticker,
        "target_price": float(target_price) if target_price is not None else None,
        "added_date": date.today().isoformat(),
        "notes": notes or "",
    })
    save_watchlist(items)
    return True


def remove_ticker(ticker: str) -> bool:
    """Remove a ticker from the watchlist. Returns True if removed."""
    ticker = ticker.strip().upper()
    items = load_watchlist()
    new_items = [it for it in items if it.get("ticker") != ticker]
    if len(new_items) == len(items):
        return False
    save_watchlist(new_items)
    return True


def update_target(ticker: str, target_price: float | None) -> bool:
    """Update a ticker's price target. Returns True if updated."""
    ticker = ticker.strip().upper()
    items = load_watchlist()
    updated = False
    for it in items:
        if it.get("ticker") == ticker:
            it["target_price"] = float(target_price) if target_price is not None else None
            updated = True
    if updated:
        save_watchlist(items)
    return updated


def update_notes(ticker: str, notes: str) -> bool:
    """Update a ticker's notes. Returns True if updated."""
    ticker = ticker.strip().upper()
    items = load_watchlist()
    updated = False
    for it in items:
        if it.get("ticker") == ticker:
            it["notes"] = notes or ""
            updated = True
    if updated:
        save_watchlist(items)
    return updated


def get_tickers() -> list[str]:
    """Convenience: just the list of tickers, in watchlist order."""
    return [it["ticker"] for it in load_watchlist()]
