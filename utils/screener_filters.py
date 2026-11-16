# -*- coding: utf-8 -*-
"""Screener filter presets and mask helpers (framework-free, shared by the
Streamlit page and the API's /api/meta endpoint)."""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Filter presets — one labeled dropdown per metric
# ---------------------------------------------------------------------------
# Each entry: (label, min_inclusive_or_None, max_inclusive_or_None).
# "Any" means no filter; other options define a bound. A single bound on
# one side is the typical case; two-sided is used for market-cap tiers.
#
# yfinance reports debtToEquity as a percentage (150 = 1.5×). The preset
# bounds match that convention (< 50 = < 0.5×).

FILTER_PRESETS: dict[str, list[tuple[str, float | None, float | None]]] = {
    "marketCap": [
        ("Any",                     None,      None),
        ("Mega cap (> $200B)",      200e9,     None),
        ("Large cap ($10–200B)",    10e9,      200e9),
        ("Mid cap ($2–10B)",        2e9,       10e9),
        ("Small cap (< $2B)",       None,      2e9),
    ],
    "trailingPE": [
        ("Any",                     None,      None),
        ("Value (< 15)",            None,      15),
        ("Moderate (< 25)",         None,      25),
        ("Growthy (< 40)",          None,      40),
        ("Expensive (< 60)",        None,      60),
    ],
    "priceToBook": [
        ("Any",                     None,      None),
        ("Below book (< 1.0)",      None,      1.0),
        ("Cheap (< 2.0)",           None,      2.0),
        ("Moderate (< 4.0)",        None,      4.0),
        ("Premium (< 8.0)",         None,      8.0),
    ],
    "enterpriseToEbitda": [
        ("Any",                     None,      None),
        ("Bargain (< 8)",           None,      8),
        ("Fair (< 15)",             None,      15),
        ("Premium (< 25)",          None,      25),
    ],
    "pegRatio": [
        ("Any",                     None,      None),
        ("Undervalued (< 1.0)",     None,      1.0),
        ("Fair (< 2.0)",            None,      2.0),
        ("Rich (< 3.0)",            None,      3.0),
    ],
    "dividendYield": [
        ("Any",                     None,      None),
        ("Pays dividend (> 0%)",    0.0001,    None),
        ("Income (> 2%)",           0.02,      None),
        ("High yield (> 4%)",       0.04,      None),
        ("Very high (> 6%)",        0.06,      None),
    ],
    "returnOnEquity": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Decent (> 10%)",          0.10,      None),
        ("Strong (> 15%)",          0.15,      None),
        ("Elite (> 25%)",           0.25,      None),
    ],
    "profitMargins": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Healthy (> 10%)",         0.10,      None),
        ("Premium (> 20%)",         0.20,      None),
    ],
    "revenueGrowth": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Growing (> 5%)",          0.05,      None),
        ("Fast (> 15%)",            0.15,      None),
        ("Hyper (> 30%)",           0.30,      None),
    ],
    "debtToEquity": [
        ("Any",                     None,      None),
        ("Debt-free (< 0.25×)",     None,      25),
        ("Conservative (< 0.5×)",   None,      50),
        ("Moderate (< 1.0×)",       None,      100),
        ("Leveraged (< 2.0×)",      None,      200),
    ],
}


def _preset_labels(key: str) -> list[str]:
    return [label for label, _, _ in FILTER_PRESETS[key]]


def _preset_bounds(key: str, label: str) -> tuple[float | None, float | None]:
    for lbl, lo, hi in FILTER_PRESETS[key]:
        if lbl == label:
            return lo, hi
    return None, None


def _apply_bounds(series: pd.Series, lo: float | None, hi: float | None) -> pd.Series:
    """Build a boolean mask for a series against optional inclusive bounds.

    Rows with NaN values fail any active bound check (same semantics the
    slider-based version used via ``.fillna(sentinel)``). When both bounds
    are None the mask is all-True.
    """
    if lo is None and hi is None:
        return pd.Series(True, index=series.index)
    mask = series.notna()
    if lo is not None:
        mask &= series >= lo
    if hi is not None:
        mask &= series <= hi
    return mask
