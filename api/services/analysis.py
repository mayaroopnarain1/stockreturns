# -*- coding: utf-8 -*-
"""Stock Analysis: overview, technicals, risk, price & events (ported from the Streamlit page)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from api.serialize import iso, series_xy
from api.services.common import ServiceError, scalar_metrics
from utils.constants import get_sector_etf
from utils.metrics import (MONTH_ABBR, bollinger_bands, compute_return_metrics,
                           compute_technical_signals, detect_outlier_days,
                           macd, monthly_seasonality, moving_averages, rsi)
from utils.prescription import (INVESTOR_PROFILES, PROFILE_DESCRIPTIONS,
                                generate_prescription)


class TickerNotFound(ServiceError):
    pass


@dataclass
class Params:
    horizon: str = "1y"
    start: str | None = None
    end: str | None = None
    profile: str = "Balanced"
    rf: float = 0.05
    outlier_z: float = 3.0
    rolling: int = 30


@dataclass
class Context:
    ticker: str
    params: Params
    data: object
    prices: pd.DataFrame
    close: pd.Series
    info: dict
    macro: dict
    ret_metrics: dict
    signals: dict
    prescription: dict
    sector: str = "—"
    extras: dict = field(default_factory=dict)


def load_prices(data, symbol: str, p: Params) -> pd.DataFrame:
    if p.horizon == "custom":
        if not p.start or not p.end:
            raise ServiceError("Custom range needs start and end dates.")
        if pd.Timestamp(p.start) >= pd.Timestamp(p.end):
            raise ServiceError("Start date must be before end date.")
        return data.get_price_history_dates(symbol, p.start, p.end)
    return data.get_price_history(symbol, p.horizon)


def _fallback_prescription(ticker: str, profile: str, exc: Exception) -> dict:
    return {
        "verdict": "Hold", "confidence": "Low", "composite_score": 50.0,
        "valuation_score": 50.0, "quality_score": 50.0, "momentum_score": 50.0, "macro_score": 50.0,
        "valuation_rationale": ["Data unavailable"], "quality_rationale": ["Data unavailable"],
        "momentum_rationale": ["Data unavailable"], "macro_rationale": ["Data unavailable"],
        "weights": {"valuation": 0.25, "quality": 0.25, "momentum": 0.25, "macro": 0.25},
        "profile": profile,
        "thesis": (f"Verdict engine couldn't run for {ticker} — likely a data provider hiccup "
                   f"({type(exc).__name__}). Other tabs still work."),
    }


def load_context(data, ticker: str, p: Params) -> Context:
    if p.profile not in INVESTOR_PROFILES:
        raise ServiceError(f"Unknown profile: {p.profile!r}")
    prices = load_prices(data, ticker, p)
    if prices.empty:
        raise TickerNotFound(f"No price data found for {ticker}. Check the ticker symbol and try again.")
    close = prices["Close"]
    info = data.get_ticker_info(ticker) or {}
    macro = data.get_macro_snapshot()
    ret_metrics = compute_return_metrics(close, p.rf)
    signals = compute_technical_signals(close)
    try:
        prescription = generate_prescription(info, signals, macro, profile=p.profile)
    except Exception as exc:  # noqa: BLE001
        prescription = _fallback_prescription(ticker, p.profile, exc)
    return Context(ticker, p, data, prices, close, info, macro, ret_metrics, signals, prescription,
                   sector=info.get("sector") or "—")


# ------------------------------------------------------------------ overview

def score_band(score: float) -> str:
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Solid"
    if score >= 45:
        return "Fair"
    if score >= 30:
        return "Weak"
    return "Poor"


def vix_label(v: float) -> str:
    return "Calm" if v < 15 else "Elevated" if v > 25 else "Moderate"


def tnx_label(v: float) -> str:
    return "Accommodative" if v < 3 else "Restrictive" if v > 5 else "Neutral"


def overview(ctx: Context) -> dict:
    info, close, pres = ctx.info, ctx.close, ctx.prescription
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
    pct_range = (price - lo) / (hi - lo) * 100 if hi and lo and hi > lo else None

    macro = {}
    for sym in ("^VIX", "^TNX", "SPY"):
        m = ctx.macro.get(sym, {})
        cur = m.get("current")
        label = None
        if cur is not None and sym == "^VIX":
            label = vix_label(cur)
        elif cur is not None and sym == "^TNX":
            label = tnx_label(cur)
        macro[sym] = {"current": cur, "change_pct": m.get("change_pct"), "label": label}

    def stat(key):
        return info.get(key)

    dims = [
        ("Valuation", "valuation"), ("Quality", "quality"),
        ("Momentum", "momentum"), ("Risk/Macro", "macro"),
    ]
    return {
        "hero": {
            "ticker": ctx.ticker,
            "name": info.get("shortName") or info.get("longName") or ctx.ticker,
            "sector": info.get("sector") or "—", "industry": info.get("industry") or "—",
            "price": price, "day_change_abs": price - prev,
            "day_change_pct": (price - prev) / prev * 100 if prev else 0.0,
            "week_low": lo, "week_high": hi, "pct_of_range": pct_range,
        },
        "prescription": pres,
        "profile_description": PROFILE_DESCRIPTIONS.get(ctx.params.profile, ""),
        "dimensions": [
            {"name": name, "score": pres[f"{key}_score"], "band": score_band(pres[f"{key}_score"]),
             "rationale": pres[f"{key}_rationale"][:2]}
            for name, key in dims
        ],
        "macro": macro,
        "key_stats": {
            "market_cap": stat("marketCap"), "beta": stat("beta"),
            "dividend_yield": stat("dividendYield"), "forward_pe": stat("forwardPE"),
            "trailing_pe": stat("trailingPE"), "roe": stat("returnOnEquity"),
            "revenue_growth": stat("revenueGrowth"),
            "total_return": ctx.ret_metrics["total_return"],
        },
    }


# ---------------------------------------------------------------- technicals

def _aligned(index, **series) -> dict:
    return {k: series_xy(v.reindex(index))["y"] for k, v in series.items()}


def technicals(ctx: Context) -> dict:
    sig = ctx.signals
    if sig.get("direction") == "Insufficient data":
        return {"insufficient": True}
    close = ctx.close
    idx = close.index
    mas = moving_averages(close, windows=(20, 50, 200))
    macd_line, signal_line, hist = macd(close)
    upper, mid, lower = bollinger_bands(close)
    rsi_s = rsi(close)
    bb_pos = sig.get("bb_position")
    return {
        "insufficient": False,
        "direction": sig["direction"], "strength": sig["strength"],
        "signals": [list(s) for s in sig.get("signals", [])],
        "ma_values": {"ma20": sig.get("ma20"), "ma50": sig.get("ma50"), "ma200": sig.get("ma200")},
        "dates": [iso(d) for d in idx],
        "series": {
            "price": series_xy(close)["y"],
            **_aligned(idx, ma20=mas[20], ma50=mas[50], ma200=mas[200], rsi=rsi_s,
                       macd=macd_line, macd_signal=signal_line, macd_hist=hist,
                       bb_upper=upper, bb_middle=mid, bb_lower=lower),
        },
        "bb_position": bb_pos,
        "bb_read": (None if bb_pos is None else
                    "at upper band — stretched" if bb_pos > 0.9 else
                    "at lower band — compressed" if bb_pos < 0.1 else "normal"),
    }


# ---------------------------------------------------------------------- risk

def risk(ctx: Context) -> dict:
    m = ctx.ret_metrics
    rp: pd.Series = m["daily_ret_pct"]
    rvol = rp.rolling(window=ctx.params.rolling).std().dropna()
    avg, std = m["avg_daily"], m["std_daily"]
    hist = {"edges": [], "counts": [], "normal": None}
    if len(rp) >= 2:
        counts, edges = np.histogram(rp.values, bins=50)
        hist["edges"], hist["counts"] = edges.tolist(), counts.tolist()
        if std and not np.isnan(std):
            x = np.linspace(float(rp.min()), float(rp.max()), 200)
            pdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - avg) / std) ** 2)
            bw = (float(rp.max()) - float(rp.min())) / 50
            hist["normal"] = {"x": x.tolist(), "y": (pdf * len(rp) * bw).tolist()}
    return {
        "metrics": scalar_metrics(m),
        "rolling_window": ctx.params.rolling,
        "rolling_vol": series_xy(rvol),
        "histogram": hist,
        "mean": avg,
    }


# ------------------------------------------------------------ price & events

def _naive(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(None) if t.tzinfo is not None else t


def _marker(price_map: pd.Series, dt: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """Price on the first trading day on/after ``dt`` (None if beyond the series)."""
    future = price_map.index[price_map.index >= dt]
    if not len(future):
        return None
    d = future.min()
    return d, float(price_map.loc[d])


def seasonality(ctx: Context) -> dict:
    data = ctx.data

    def close10(sym):
        h = data.get_price_history(sym, "10y")
        return h["Close"] if not h.empty else pd.Series(dtype=float)

    etf = get_sector_etf(ctx.sector)
    series = {ctx.ticker: monthly_seasonality(close10(ctx.ticker), 10),
              "SPY": monthly_seasonality(close10("SPY"), 10)}
    if etf and etf != "SPY":
        s = close10(etf)
        if not s.empty:
            series[etf] = monthly_seasonality(s, 10)

    t_stats = series[ctx.ticker]["stats"]
    if t_stats["n"].fillna(0).sum() == 0:
        return {"available": False}

    rows = []
    for name, res in series.items():
        st = res["stats"]
        rows.append({"series": name, "kind": "ticker" if name == ctx.ticker else "benchmark",
                     "months": [{"month": MONTH_ABBR[m - 1], "mean": _f(st.loc[m, "mean"]),
                                 "hit_rate": _f(st.loc[m, "hit_rate"]), "n": int(st.loc[m, "n"])
                                 if pd.notna(st.loc[m, "n"]) else 0} for m in range(1, 13)]})
    spy_stats = series["SPY"]["stats"]
    excess = []
    for m in range(1, 13):
        a, b = t_stats.loc[m, "mean"], spy_stats.loc[m, "mean"]
        excess.append({"month": MONTH_ABBR[m - 1], "mean": _f(a - b) if pd.notna(a) and pd.notna(b) else None,
                       "hit_rate": None, "n": int(t_stats.loc[m, "n"]) if pd.notna(t_stats.loc[m, "n"]) else 0})
    rows.append({"series": f"{ctx.ticker} − SPY", "kind": "excess", "months": excess})

    tv = t_stats.dropna(subset=["mean"])
    best = int(tv["mean"].idxmax()); worst = int(tv["mean"].idxmin())
    res = series[ctx.ticker]
    return {
        "available": True, "rows": rows, "months": list(MONTH_ABBR),
        "headline": {"best_month": MONTH_ABBR[best - 1], "best_mean": _f(tv.loc[best, "mean"]),
                     "worst_month": MONTH_ABBR[worst - 1], "worst_mean": _f(tv.loc[worst, "mean"]),
                     "avg_hit_rate": _f(tv["hit_rate"].mean()), "years": res["n_years"],
                     "start": iso(res["start"]) if res["start"] is not None else None,
                     "end": iso(res["end"]) if res["end"] is not None else None},
        "short_window": res["n_years"] < 5,
    }


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def events(ctx: Context, relative: bool = False) -> dict:
    data, close, ticker = ctx.data, ctx.close, ctx.ticker
    display = close.copy()
    display.index = pd.DatetimeIndex([_naive(i) for i in display.index])
    label = "Price ($)"
    etf = get_sector_etf(ctx.sector)
    notice = None
    if relative and etf:
        sect = load_prices(data, etf, ctx.params)
        if not sect.empty:
            sc = sect["Close"].copy()
            sc.index = pd.DatetimeIndex([_naive(i) for i in sc.index])
            aligned = pd.concat([display, sc], axis=1, join="inner")
            aligned.columns = ["stock", "sector"]
            if len(aligned) > 1:
                display = (aligned["stock"] / aligned["stock"].iloc[0]) / (aligned["sector"] / aligned["sector"].iloc[0])
                label = f"{ticker} / {etf} (start = 1.0)"
        else:
            notice = f"Could not load {etf}; showing absolute price."
    elif relative and not etf:
        notice = "No sector ETF mapped for this ticker; showing absolute price."

    start, end = display.index[0], display.index[-1]
    out_events = []

    ed = data.get_earnings_dates(ticker)
    if ed is not None and not ed.empty:
        for dt in ed.index[(ed.index >= start) & (ed.index <= end)]:
            mk = _marker(display, dt)
            if mk:
                out_events.append({"type": "earnings", "date": iso(mk[0]), "price": mk[1], "label": "Earnings"})

    divs = data.get_dividends(ticker, period="10y")
    if divs is not None and not divs.empty:
        divs = divs.copy()
        divs.index = pd.DatetimeIndex([_naive(i) for i in divs.index])
        for dt, amt in divs[(divs.index >= start) & (divs.index <= end)].items():
            mk = _marker(display, dt)
            if mk:
                out_events.append({"type": "dividend", "date": iso(mk[0]), "price": mk[1],
                                   "label": f"Dividend ${amt:.2f}"})

    rets = close.pct_change().dropna()
    for dt, r in detect_outlier_days(rets, z_threshold=ctx.params.outlier_z).items():
        d = _naive(dt)
        if d in display.index:
            out_events.append({"type": "outlier", "date": iso(d), "price": float(display.loc[d]),
                               "label": f"Outlier: {r * 100:+.2f}%", "return_pct": float(r * 100)})

    rets_pct = close.pct_change() * 100
    top = rets_pct.dropna().abs().nlargest(10).index
    top_moves = [{"date": iso(d), "price": float(close.loc[d]), "return_pct": float(rets_pct.loc[d])} for d in top]

    next_er = None
    if ed is not None and not ed.empty:
        today = pd.Timestamp.today().normalize()
        up = ed[ed.index >= today]
        if not up.empty:
            nxt = up.index.min()
            next_er = {"date": iso(nxt), "days_until": (nxt - today).days}

    return {
        "label": label, "relative": label != "Price ($)", "sector_etf": etf, "notice": notice,
        "price": series_xy(display), "events": out_events, "top_moves": top_moves,
        "next_earnings": next_er, "outlier_z": ctx.params.outlier_z,
    }
