# -*- coding: utf-8 -*-
"""Stock Analysis: fundamentals, dividends and statement-derived analytics."""

from __future__ import annotations

import math

import pandas as pd

from api.serialize import iso
from api.services import screener
from api.services.analysis import Context
from utils.constants import get_sector_peers
from utils.dividends import summarize as dividend_summary
from utils.financials import (accruals_analysis, dupont_roe, earnings_quality, fcf_conversion,
                              leverage_liquidity, margin_decomposition, quality_scorecard,
                              revenue_quality, roic_analysis)

VAL_FIELDS = [("trailingPE", "P/E (TTM)", "lower"), ("forwardPE", "Fwd P/E", "lower"),
              ("priceToBook", "P/B", "lower"), ("enterpriseToEbitda", "EV/EBITDA", "lower"),
              ("pegRatio", "PEG", "lower"), ("priceToSalesTrailing12Months", "P/S", "lower")]
QUAL_FIELDS = [("returnOnEquity", "ROE", "higher", True), ("returnOnAssets", "ROA", "higher", True),
               ("profitMargins", "Profit margin", "higher", True),
               ("operatingMargins", "Operating margin", "higher", True),
               ("debtToEquity", "D/E", "lower", False), ("currentRatio", "Current ratio", "higher", False)]
GROWTH_FIELDS = [("revenueGrowth", "Revenue growth"), ("earningsGrowth", "Earnings growth")]
PERCENTILE_METRICS = {"trailingPE": ("P/E", True), "priceToBook": ("P/B", True),
                      "enterpriseToEbitda": ("EV/EBITDA", True), "returnOnEquity": ("ROE", False),
                      "profitMargins": ("Margin", False), "revenueGrowth": ("Rev growth", False)}


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _sector_median(universe: pd.DataFrame, sector: str, key: str):
    if universe is None or universe.empty or key not in universe.columns or "sector" not in universe.columns:
        return None
    sub = universe[universe["sector"] == sector]
    if sub.empty:
        return None
    m = sub[key].astype(float).median()
    return None if pd.isna(m) else float(m)


def universe_frame() -> tuple[pd.DataFrame, dict]:
    """The screener universe as a DataFrame (starting a build if needed) plus its status."""
    from api.datasource import data
    snap = screener.snapshot()
    if snap["status"] in ("idle", "error"):
        screener.start(data)
        snap = screener.snapshot()
    if snap["status"] != "ready":
        return pd.DataFrame(), {k: snap[k] for k in ("status", "done", "total")}
    df = pd.DataFrame(snap["rows"]).set_index("ticker")
    for c in df.columns:
        if c not in ("shortName", "sector", "industry"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, {"status": "ready", "done": snap["done"], "total": snap["total"]}


def dividends_panel(ctx: Context) -> dict | None:
    divs = ctx.data.get_dividends(ctx.ticker, period="10y")
    if divs is None or divs.empty:
        return None
    stmts = ctx.data.get_financials(ctx.ticker, freq="annual")
    s = dividend_summary(stmts, divs, ctx.info.get("currentPrice"), ctx.close)
    hist = s["history"]
    history = []
    for idx, r in hist.iterrows():
        history.append({"year": int(pd.Timestamp(idx).year), "dps": _num(r["DPS"]), "yoy": _num(r["YoY"]),
                        "payout_ratio": _num(r["PayoutRatio"])})
    y = s["yield"]
    return {
        "history": history,
        "yield": {k: _num(v) if k != "n_years" else int(v) for k, v in y.items()},
        "cagr_3y": _num(s["cagr_3y"]), "cagr_5y": _num(s["cagr_5y"]), "cagr_10y": _num(s["cagr_10y"]),
        "streak": int(s["streak"]), "latest_payout": _num(s["latest_payout"]),
    }


def fundamentals(ctx: Context, with_context: bool = False) -> dict:
    info, sector = ctx.info, ctx.sector
    universe, ustatus = (pd.DataFrame(), None)
    if with_context:
        universe, ustatus = universe_frame()
    have_ctx = with_context and not universe.empty

    def delta(key, val, is_pct=False):
        med = _sector_median(universe, sector, key) if have_ctx else None
        if med is None or val is None:
            return None, None
        if is_pct:
            return med, (val - med) * 100                       # percentage points
        if med == 0:
            return med, None
        return med, (val - med) / med * 100                      # percent difference

    valuation = []
    for key, label, direction in VAL_FIELDS:
        v = _num(info.get(key))
        med, d = delta(key, v)
        valuation.append({"key": key, "label": label, "direction": direction, "value": v,
                          "sector_median": med, "delta": d, "delta_unit": "%"})
    quality = []
    for key, label, direction, is_pct in QUAL_FIELDS:
        v = _num(info.get(key))
        med, d = delta(key, v, is_pct)
        quality.append({"key": key, "label": label, "direction": direction, "is_pct": is_pct, "value": v,
                        "sector_median": med, "delta": d, "delta_unit": "pp" if is_pct else "%"})
    growth = [{"key": k, "label": l, "value": _num(info.get(k))} for k, l in GROWTH_FIELDS]
    growth.append({"key": "freeCashflow", "label": "Free cash flow", "value": _num(info.get("freeCashflow"))})

    percentiles, peers = [], []
    if have_ctx and ctx.ticker in universe.index:
        sub = universe[universe["sector"] == sector]
        if ctx.ticker in sub.index:
            for key, (label, reverse) in PERCENTILE_METRICS.items():
                if key in sub.columns and pd.notna(sub.loc[ctx.ticker, key]):
                    series = sub[key].dropna()
                    if len(series) > 1:
                        rank = series.rank(pct=True, ascending=not reverse)
                        if ctx.ticker in rank.index:
                            percentiles.append({"metric": label, "percentile": float(rank.loc[ctx.ticker] * 100)})
    if have_ctx:
        peers = get_sector_peers(ctx.ticker, sector, universe, n=4)

    return {
        "sector": sector, "valuation": valuation, "quality": quality, "growth": growth,
        "context": {"requested": with_context, "available": have_ctx, "universe": ustatus,
                    "percentiles": percentiles, "peers": peers},
        "dividends": dividends_panel(ctx),
    }


# --------------------------------------------------------------- financials

def _safe(fn, stmts):
    try:
        return fn(stmts)
    except Exception:  # noqa: BLE001 - one bad analytic must not take down the tab
        return None


def _table(res: dict | None):
    return None if res is None else res["df"]


def financials(ctx: Context, freq: str = "annual") -> dict:
    stmts = ctx.data.get_financials(ctx.ticker, freq=freq)
    if all(stmts[k].empty for k in ("income", "balance", "cashflow")):
        return {"available": False, "freq": freq}

    dup, mar, roi = _safe(dupont_roe, stmts), _safe(margin_decomposition, stmts), _safe(roic_analysis, stmts)
    rev, eq = _safe(revenue_quality, stmts), _safe(earnings_quality, stmts)
    acc, fcf, lev = _safe(accruals_analysis, stmts), _safe(fcf_conversion, stmts), _safe(leverage_liquidity, stmts)

    try:
        score = quality_scorecard(dup or {"latest_roe": None}, mar or {"df": pd.DataFrame()},
                                  roi or {}, eq or {}, acc or {}, fcf or {}, lev or {})
    except Exception:  # noqa: BLE001
        nan = float("nan")
        score = {k: {"score": nan, "label": "—"} for k in ("profitability", "earnings_quality", "balance_sheet")}

    def part(res, *scalars):
        if res is None:
            return None
        return {"table": res["df"] if "df" in res else None, **{k: res.get(k) for k in scalars}}

    first = next(s for s in (stmts["income"], stmts["balance"], stmts["cashflow"]) if not s.empty)
    return {
        "available": True, "freq": freq,
        "periods": [iso(c) if not isinstance(c, str) else c for c in first.columns],
        "scorecard": score,
        "dupont": part(dup, "latest_roe", "driver"),
        "margins": part(mar, "biggest_leak"),
        "roic": part(roi, "latest_roic", "wacc_proxy", "creates_value"),
        "revenue_quality": part(rev, "cagr_3y", "ar_outpacing_revenue", "latest_yoy"),
        "earnings_quality": part(eq, "latest_gap", "tax_std", "tax_unstable"),
        "accruals": part(acc, "latest", "band"),
        "fcf": part(fcf, "latest"),
        "leverage": None if lev is None else {"metrics": lev["metrics"], "bands": lev["bands"]},
    }
