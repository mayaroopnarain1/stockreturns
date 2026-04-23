# -*- coding: utf-8 -*-
"""
Dividend-growth analytics — pure compute, no Streamlit dependency.

Inputs are the same shapes returned by utils.data: an annual statements dict
(``income`` / ``balance`` / ``cashflow`` DataFrames with yfinance-style row
labels) plus a DPS Series from ``get_dividends``. The Stock Analysis page
wraps these into a UI block.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _eps_series(stmts_annual: dict) -> pd.Series:
    """Return Diluted EPS as a DatetimeIndex-keyed Series, or empty."""
    inc = stmts_annual.get("income") if isinstance(stmts_annual, dict) else None
    if inc is None or inc.empty or "Diluted EPS" not in inc.index:
        return pd.Series(dtype=float)
    row = pd.to_numeric(inc.loc["Diluted EPS"], errors="coerce").dropna()
    row.index = pd.to_datetime(row.index)
    return row


def dividend_history(stmts_annual: dict, dividends: pd.Series) -> pd.DataFrame:
    """Per-fiscal-year DPS + EPS + payout ratio + YoY DPS growth.

    Returns a DataFrame indexed by fiscal-year-end Timestamp with columns
    ``DPS``, ``EPS``, ``PayoutRatio``, ``YoY``. Payout ratio is clipped to
    [0, 2.0] so a one-off loss year doesn't distort the chart.
    """
    if dividends is None or len(dividends) == 0:
        return pd.DataFrame(columns=["DPS", "EPS", "PayoutRatio", "YoY"])

    dps = pd.to_numeric(dividends, errors="coerce").dropna()
    dps.index = pd.to_datetime(dps.index)
    dps = dps.sort_index()

    eps = _eps_series(stmts_annual)

    # Align EPS onto the DPS index (nearest fiscal-year-end within 45 days).
    df = pd.DataFrame({"DPS": dps})
    if not eps.empty:
        aligned = eps.reindex(dps.index, method="nearest", tolerance=pd.Timedelta("45D"))
        df["EPS"] = aligned
    else:
        df["EPS"] = np.nan

    payout = df["DPS"] / df["EPS"].replace(0, np.nan)
    df["PayoutRatio"] = payout.clip(lower=0, upper=2.0)
    df["YoY"] = df["DPS"].pct_change()
    return df


def dividend_cagr(dividends: pd.Series, years: int = 5) -> float:
    """Compound annual growth rate of DPS over the trailing N fiscal years."""
    if dividends is None or len(dividends) == 0:
        return float("nan")
    s = pd.to_numeric(dividends, errors="coerce").dropna().sort_index()
    if len(s) <= years:
        return float("nan")
    end = float(s.iloc[-1])
    start = float(s.iloc[-(years + 1)])
    if start <= 0:
        return float("nan")
    return (end / start) ** (1.0 / years) - 1.0


def dividend_streak(dividends: pd.Series) -> int:
    """Consecutive fiscal years (from most recent) with a non-decreasing DPS."""
    if dividends is None or len(dividends) == 0:
        return 0
    s = pd.to_numeric(dividends, errors="coerce").dropna().sort_index()
    if len(s) < 2:
        return 0
    streak = 0
    vals = s.values
    for i in range(len(vals) - 1, 0, -1):
        if vals[i] >= vals[i - 1]:
            streak += 1
        else:
            break
    return streak


def _price_at_or_before(close: pd.Series, when: pd.Timestamp) -> float:
    """Return the last close on or before ``when``. NaN if no such row."""
    if close is None or len(close) == 0:
        return float("nan")
    before = close[close.index <= when]
    if before.empty:
        return float("nan")
    return float(before.iloc[-1])


def yield_stats(
    current_price: float | None,
    dividends: pd.Series,
    close_history: pd.Series | None,
    lookback_years: int = 5,
) -> dict:
    """Current dividend yield and its position vs the trailing average.

    ``current_price`` is today's price (yfinance). ``dividends`` is the
    annual DPS series. ``close_history`` is the full daily Close series used
    to look up year-end prices for the historical-yield calc.

    Returns ``{"current_yield", "avg_yield", "min_yield", "max_yield",
    "percentile", "n_years"}`` — all floats, NaN where not computable.
    ``percentile`` is 0..1 (where does current yield sit in the lookback).
    """
    out = {
        "current_yield": float("nan"),
        "avg_yield": float("nan"),
        "min_yield": float("nan"),
        "max_yield": float("nan"),
        "percentile": float("nan"),
        "n_years": 0,
    }
    if dividends is None or len(dividends) == 0:
        return out
    dps = pd.to_numeric(dividends, errors="coerce").dropna().sort_index()
    if dps.empty:
        return out

    latest_dps = float(dps.iloc[-1])
    if current_price and current_price > 0:
        out["current_yield"] = latest_dps / float(current_price)

    if close_history is None or len(close_history) == 0:
        return out
    ch = close_history.copy()
    ch.index = pd.to_datetime(ch.index)
    if getattr(ch.index, "tz", None) is not None:
        ch.index = ch.index.tz_localize(None)

    recent = dps.tail(lookback_years)
    ys = []
    for fy_end, d in recent.items():
        p = _price_at_or_before(ch, pd.Timestamp(fy_end))
        if np.isfinite(p) and p > 0:
            ys.append(d / p)
    if ys:
        ys_arr = np.array(ys, dtype=float)
        out["avg_yield"] = float(ys_arr.mean())
        out["min_yield"] = float(ys_arr.min())
        out["max_yield"] = float(ys_arr.max())
        out["n_years"] = int(len(ys_arr))
        cy = out["current_yield"]
        if np.isfinite(cy) and len(ys_arr) >= 2:
            out["percentile"] = float((ys_arr <= cy).mean())
    return out


def summarize(
    stmts_annual: dict,
    dividends: pd.Series,
    current_price: float | None,
    close_history: pd.Series | None,
) -> dict:
    """One-shot aggregator used by the UI."""
    hist = dividend_history(stmts_annual, dividends)
    return {
        "history": hist,
        "cagr_3y": dividend_cagr(dividends, 3),
        "cagr_5y": dividend_cagr(dividends, 5),
        "cagr_10y": dividend_cagr(dividends, 10),
        "streak": dividend_streak(dividends),
        "latest_payout": (
            float(hist["PayoutRatio"].dropna().iloc[-1])
            if "PayoutRatio" in hist.columns and hist["PayoutRatio"].dropna().size
            else float("nan")
        ),
        "yield": yield_stats(current_price, dividends, close_history),
    }
