# -*- coding: utf-8 -*-
"""Small pure helpers shared by several services."""

from __future__ import annotations

NEAR_TARGET_PCT = -5.0  # within 5% below target counts as "near"


def target_status(price: float | None, target: float | None) -> tuple[float | None, str]:
    """Return ``(vs_target_pct, status)``.

    status: ``no_data`` | ``none`` | ``hit`` | ``near`` | ``below``. Mirrors the
    Streamlit Home/Watchlist logic: hit when price >= target, near when within
    5% below, otherwise below. No/zero target gives ``none``.
    """
    if price is None:
        return None, "no_data"
    if target is None or target <= 0:
        return None, "none"
    vs = (price - target) / target * 100
    if price >= target:
        return vs, "hit"
    if vs >= NEAR_TARGET_PCT:
        return vs, "near"
    return vs, "below"


def rsi_bucket(value: float | None) -> dict:
    """RSI bucket: ``{"label","value"}`` with label Overbought/Oversold/Neutral/None."""
    if value is None:
        return {"label": None, "value": None}
    if value >= 70:
        return {"label": "Overbought", "value": value}
    if value <= 30:
        return {"label": "Oversold", "value": value}
    return {"label": "Neutral", "value": value}
