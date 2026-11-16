# -*- coding: utf-8 -*-
"""
Deterministic synthetic market data with the same function names, signatures
and return shapes as ``utils.data``. No network, no yfinance.
"""

from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np
import pandas as pd

from utils.constants import (  # noqa: F401 - mirrors utils.data's public names
    MACRO_TICKERS,
    SECTOR_ETF,
    SP500_TICKERS,
    UNIVERSE_OPTIONS,
    get_sector_etf,
    get_sector_peers,
)

_PERIOD_DAYS = {"5d": 5, "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252,
                "2y": 504, "5y": 1260, "10y": 2520}
_SECTORS = list(SECTOR_ETF.keys())
_ETFS = set(SECTOR_ETF.values()) | {"SPY"}


def _seed(symbol: str) -> int:
    return zlib.crc32(symbol.upper().encode("utf-8"))


def _rng(symbol: str, salt: str = "") -> np.random.Generator:
    return np.random.default_rng(_seed(symbol + salt))


def _today() -> pd.Timestamp:
    return pd.Timestamp.today().normalize()


@lru_cache(maxsize=512)
def _full_history(symbol: str) -> pd.DataFrame:
    """10 years of synthetic business-day OHLCV, identical on every call."""
    sym = symbol.upper()
    rng = _rng(sym)
    n = _PERIOD_DAYS["10y"]
    idx = pd.bdate_range(end=_today(), periods=n, name="Date")
    if sym == "^VIX":
        base, mu, sigma = 18.0, 0.0, 0.04
    elif sym == "^TNX":
        base, mu, sigma = 4.3, 0.0, 0.012
    else:
        base = 20 + (_seed(sym) % 400)
        mu = 0.0002 + (_seed(sym) % 7) * 0.00004
        sigma = 0.009 + (_seed(sym) % 5) * 0.003
    rets = rng.normal(mu, sigma, n)
    # A common market factor so correlations between tickers are non-trivial.
    mkt = np.random.default_rng(12345).normal(0.0003, 0.008, n)
    rets = rets + (0.0 if sym.startswith("^") else 0.5 * mkt)
    close = base * np.cumprod(1 + rets)
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    vol = rng.integers(1_000_000, 50_000_000, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def get_price_history(symbol: str, period: str) -> pd.DataFrame:
    if not symbol or symbol.upper().startswith("ZZZ"):
        return pd.DataFrame()  # simulates an unknown ticker
    days = _PERIOD_DAYS.get(period, 252)
    return _full_history(symbol).tail(days).copy()


def get_price_history_dates(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = get_price_history(symbol, "10y")
    if df.empty:
        return df
    return df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))].copy()


def _is_etf(symbol: str) -> bool:
    return symbol.upper() in _ETFS or symbol.upper().startswith("^")


def get_ticker_info(symbol: str) -> dict:
    sym = symbol.upper()
    if sym.startswith("ZZZ"):
        return {}
    hist = _full_history(sym)
    price = float(hist["Close"].iloc[-1])
    last_year = hist["Close"].tail(252)
    rng = _rng(sym, "info")
    sector = _SECTORS[_seed(sym) % len(_SECTORS)]
    info: dict = {
        "symbol": sym,
        "shortName": f"{sym} Corp",
        "sector": sector,
        "industry": f"{sector} — Synthetic",
        "currentPrice": price,
        "fiftyTwoWeekHigh": float(last_year.max()),
        "fiftyTwoWeekLow": float(last_year.min()),
        "beta": round(float(rng.uniform(0.6, 1.8)), 2),
    }
    if _is_etf(sym):
        info.update({"shortName": f"{sym} ETF", "sector": None, "industry": None})
        return info
    shares = float(rng.uniform(0.3e9, 8e9))
    info.update({
        "marketCap": price * shares,
        "trailingPE": round(float(rng.uniform(8, 48)), 2),
        "forwardPE": round(float(rng.uniform(8, 40)), 2),
        "priceToBook": round(float(rng.uniform(0.8, 12)), 2),
        "enterpriseToEbitda": round(float(rng.uniform(5, 28)), 2),
        "priceToSalesTrailing12Months": round(float(rng.uniform(0.7, 14)), 2),
        "pegRatio": round(float(rng.uniform(0.5, 3.5)), 2) if _seed(sym) % 5 else None,
        "dividendYield": round(float(rng.uniform(0.005, 0.05)), 4) if _seed(sym) % 3 else 0.0,
        "payoutRatio": round(float(rng.uniform(0.1, 0.9)), 2),
        "returnOnEquity": round(float(rng.uniform(0.02, 0.45)), 3),
        "returnOnAssets": round(float(rng.uniform(0.01, 0.2)), 3),
        "profitMargins": round(float(rng.uniform(0.02, 0.35)), 3),
        "operatingMargins": round(float(rng.uniform(0.04, 0.40)), 3),
        "revenueGrowth": round(float(rng.uniform(-0.1, 0.4)), 3),
        "earningsGrowth": round(float(rng.uniform(-0.2, 0.5)), 3),
        "debtToEquity": round(float(rng.uniform(5, 260)), 1),
        "currentRatio": round(float(rng.uniform(0.6, 3.0)), 2),
        "freeCashflow": float(rng.uniform(0.2e9, 30e9)),
        "operatingCashflow": float(rng.uniform(0.5e9, 40e9)),
        "totalRevenue": float(rng.uniform(1e9, 200e9)),
        "ebitda": float(rng.uniform(0.3e9, 60e9)),
        "enterpriseValue": price * shares * 1.1,
    })
    return info


def fetch_fundamentals_bulk(tickers: list[str]) -> pd.DataFrame:
    fields = [
        "shortName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
        "priceToBook", "enterpriseToEbitda", "priceToSalesTrailing12Months", "pegRatio",
        "dividendYield", "payoutRatio", "returnOnEquity", "returnOnAssets",
        "profitMargins", "operatingMargins", "revenueGrowth", "earningsGrowth",
        "debtToEquity", "currentRatio", "freeCashflow", "operatingCashflow",
        "enterpriseValue", "totalRevenue", "ebitda", "beta", "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow", "currentPrice",
    ]
    rows = []
    for t in tickers:
        info = get_ticker_info(t)
        if not info:
            continue
        rows.append({"Ticker": t, **{f: info.get(f) for f in fields}})
    return pd.DataFrame(rows).set_index("Ticker") if rows else pd.DataFrame()


def get_macro_snapshot() -> dict:
    out = {}
    for sym, label in MACRO_TICKERS.items():
        h = _full_history(sym)["Close"]
        cur, prev = float(h.iloc[-1]), float(h.iloc[-2])
        out[sym] = {"current": cur, "change_pct": (cur - prev) / prev * 100, "label": label}
    return out


def get_daily_changes(tickers: tuple) -> pd.DataFrame:
    rows = []
    for t in tickers:
        h = get_price_history(t, "1mo")
        if len(h) < 2:
            continue
        price, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
        rows.append({
            "Ticker": t, "price": price, "prev_close": prev,
            "change_abs": price - prev, "change_pct": (price - prev) / prev * 100,
            "volume": float(h["Volume"].iloc[-1]),
        })
    return pd.DataFrame(rows).set_index("Ticker") if rows else pd.DataFrame()


def get_earnings_dates(symbol: str) -> pd.DataFrame:
    if symbol.upper().startswith("ZZZ") or _is_etf(symbol):
        return pd.DataFrame()
    rng = _rng(symbol, "earn")
    today = _today()
    dates = [today + pd.Timedelta(days=int(10 + _seed(symbol) % 40))]
    for q in range(1, 17):
        dates.append(today - pd.Timedelta(days=int(q * 91 - _seed(symbol) % 30)))
    idx = pd.DatetimeIndex(sorted(dates))
    eps = rng.uniform(0.5, 4, len(idx))
    df = pd.DataFrame({
        "EPS Estimate": eps, "Reported EPS": eps * rng.uniform(0.9, 1.15, len(idx)),
        "Surprise(%)": rng.uniform(-8, 12, len(idx)),
    }, index=idx)
    df.iloc[-1, df.columns.get_loc("Reported EPS")] = np.nan  # the future one
    return df


def get_dividends(symbol: str, period: str = "5y") -> pd.Series:
    """Annual declared DPS indexed by fiscal-year end (matches the EDGAR path)."""
    sym = symbol.upper()
    if _is_etf(sym) or _seed(sym) % 3 == 0 or sym.startswith("ZZZ"):
        return pd.Series(dtype=float)
    years = 10 if period == "10y" else 5
    end_year = _today().year - 1
    idx = pd.DatetimeIndex([pd.Timestamp(year=y, month=12, day=31)
                            for y in range(end_year - years + 1, end_year + 1)])
    base = 0.4 + (_seed(sym) % 10) * 0.15
    growth = 1.0 + (_seed(sym) % 9) * 0.01
    return pd.Series([round(base * growth ** i, 3) for i in range(len(idx))], index=idx)


def get_financials(symbol: str, freq: str = "annual") -> dict:
    sym = symbol.upper()
    empty = {"income": pd.DataFrame(), "balance": pd.DataFrame(), "cashflow": pd.DataFrame()}
    if _is_etf(sym) or sym.startswith("ZZZ"):
        return empty
    rng = _rng(sym, "fin")
    n = 8 if freq == "quarterly" else 5
    step = 3 if freq == "quarterly" else 12
    end = pd.Timestamp(year=_today().year - 1, month=12, day=31)
    cols = [end - pd.DateOffset(months=step * i) for i in range(n - 1, -1, -1)]
    scale = 1 if freq == "annual" else 0.25
    rev0 = float(rng.uniform(2e9, 120e9)) * scale
    growth = float(rng.uniform(0.02, 0.14))
    rev = np.array([rev0 * (1 + growth) ** i for i in range(n)])
    gm, om, nm = rng.uniform(0.3, 0.65), rng.uniform(0.08, 0.3), rng.uniform(0.04, 0.22)
    gp, op, ni = rev * gm, rev * om, rev * nm
    interest = rev * 0.01
    pretax = op - interest
    tax = pretax * 0.21
    assets = rev * rng.uniform(1.2, 2.2) / scale * scale
    equity = assets * rng.uniform(0.3, 0.6)
    cash = assets * 0.12
    debt = assets * rng.uniform(0.1, 0.3)
    ocf = ni * rng.uniform(0.9, 1.4)
    capex = -rev * rng.uniform(0.02, 0.08)

    def frame(rows: dict) -> pd.DataFrame:
        return pd.DataFrame({c: [v[i] for v in rows.values()] for i, c in enumerate(cols)},
                            index=list(rows.keys()))

    income = frame({
        "Total Revenue": rev, "Cost Of Revenue": rev - gp, "Gross Profit": gp,
        "Operating Income": op, "EBITDA": op * 1.15, "Pretax Income": pretax,
        "Tax Provision": tax, "Interest Expense": interest, "Net Income": ni,
        "Diluted EPS": ni / 2e9,
    })
    balance = frame({
        "Total Assets": assets, "Current Assets": assets * 0.4,
        "Cash And Cash Equivalents": cash, "Accounts Receivable": rev * 0.12,
        "Inventory": rev * 0.08, "Total Liabilities Net Minority Interest": assets - equity,
        "Current Liabilities": assets * 0.25, "Long Term Debt": debt * 0.8,
        "Current Debt": debt * 0.2, "Total Debt": debt, "Stockholders Equity": equity,
    })
    cashflow = frame({
        "Operating Cash Flow": ocf, "Capital Expenditure": capex,
        "Free Cash Flow": ocf + capex,
    })
    return {"income": income, "balance": balance, "cashflow": cashflow}
