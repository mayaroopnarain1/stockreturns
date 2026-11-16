# -*- coding: utf-8 -*-
"""Portfolio risk analytics (ported from pages/4_Portfolio_Risk.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from api.serialize import iso, series_xy
from api.services.common import ServiceError, scalar_metrics
from utils.metrics import compute_return_metrics

WEIGHT_TOLERANCE = 0.5  # weights (in %) must sum to 100 +/- this


def equal_weights(n: int) -> list[float]:
    """Equal weights in %, rounded to 1 dp with the last item absorbing the remainder."""
    w = [round(100 / n, 1)] * n
    w[-1] = round(100 - sum(w[:-1]), 1)
    return w


def inverse_vol_weights(vols) -> list[float]:
    """Weights in % proportional to 1/vol, last item absorbing the rounding remainder."""
    inv = 1 / np.array(vols, dtype=float)
    w = (inv / inv.sum() * 100).round(1)
    w[-1] = round(100 - float(w[:-1].sum()), 1)
    return [float(x) for x in w]


def diversification_level(ratio: float) -> str:
    if ratio >= 0.25:
        return "well"
    if ratio >= 0.10:
        return "moderate"
    return "concentrated"


def sector_concentration(sector_rows: list[dict]) -> dict:
    top = sector_rows[0]
    level = "high" if top["weight"] >= 60 else "medium" if top["weight"] >= 40 else "low"
    return {"level": level, "sector": top["sector"], "weight": top["weight"]}


def build_portfolio(tickers: list[str], weights_pct: list[float], horizon: str,
                    rf: float, data) -> dict:
    if len(tickers) < 2:
        raise ServiceError("Add at least 2 holdings.")
    if len(tickers) != len(weights_pct):
        raise ServiceError("Tickers and weights must have the same length.")
    if any(w < 0 for w in weights_pct):
        raise ServiceError("Weights cannot be negative.")
    if abs(sum(weights_pct) - 100) > WEIGHT_TOLERANCE:
        raise ServiceError(f"Weights must sum to 100% (currently {sum(weights_pct):.1f}%).")

    w_arr = np.array(weights_pct, dtype=float) / 100
    prices, info, errors = {}, {}, []
    for t in tickers:
        hist = data.get_price_history(t, horizon)
        if hist.empty:
            errors.append(t)
        else:
            prices[t] = hist["Close"]
            info[t] = data.get_ticker_info(t) or {}
    if errors:
        raise ServiceError(f"Could not fetch data for: {', '.join(errors)}.")

    spy_hist = data.get_price_history("SPY", horizon)
    spy_prices = spy_hist["Close"] if not spy_hist.empty else None

    price_df = pd.DataFrame(prices).dropna()
    if len(price_df) < 20:
        raise ServiceError("Not enough overlapping price data. Try a shorter horizon or check tickers.")

    ret_df = price_df.pct_change().dropna()
    port_ret = (ret_df * w_arr).sum(axis=1)            # daily-rebalanced portfolio
    port_cum = (1 + port_ret).cumprod()
    indiv_cum = (1 + ret_df).cumprod()

    cov_annual = ret_df.cov() * 252
    port_var = float(w_arr @ cov_annual.values @ w_arr)
    port_vol = float(np.sqrt(port_var) * 100)
    indiv_vols = ret_df.std() * np.sqrt(252)
    undiversified = float((w_arr * indiv_vols.values).sum()) * 100
    div_benefit = undiversified - port_vol
    div_ratio = div_benefit / undiversified if undiversified else 0.0

    pm = compute_return_metrics(port_cum, rf)

    mctr = (cov_annual.values @ w_arr) / np.sqrt(port_var) if port_var > 0 else np.zeros_like(w_arr)
    ctr = w_arr * mctr
    ctr_pct = (ctr / ctr.sum() * 100) if ctr.sum() else np.zeros_like(w_arr)

    benchmark, spy_cum = None, None
    if spy_prices is not None:
        spy_ret = spy_prices.pct_change().dropna()
        bench_m = compute_return_metrics(spy_prices, rf)
        beta = alpha_ann = corr_spy = None
        aligned = pd.concat([port_ret, spy_ret], axis=1, join="inner").dropna()
        aligned.columns = ["port", "spy"]
        if len(aligned) > 10:
            var_spy = aligned["spy"].var()
            beta = float(aligned.cov().loc["port", "spy"] / var_spy) if var_spy else None
            corr_spy = float(aligned.corr().loc["port", "spy"])
            rf_daily = (1 + rf) ** (1 / 252) - 1     # note: differs from rf/252 used for Sharpe
            if beta is not None:
                alpha_ann = float(((aligned["port"].mean() - rf_daily)
                                   - beta * (aligned["spy"].mean() - rf_daily)) * 252 * 100)
        benchmark = {
            "excess_return": float(pm["total_return"] - bench_m["total_return"]),
            "beta": beta, "alpha_annualized": alpha_ann, "correlation": corr_spy,
        }
        # Bug fix vs. the Streamlit page: rebase SPY to the portfolio's own date range
        # (previously the full-length SPY series did not start with the portfolio).
        spy_cum = (1 + spy_ret.reindex(port_cum.index).dropna()).cumprod().reindex(port_cum.index)

    sector_alloc: dict[str, float] = {}
    for t, w in zip(tickers, w_arr):
        sec = info.get(t, {}).get("sector") or "Unknown"
        sector_alloc[sec] = sector_alloc.get(sec, 0.0) + float(w) * 100
    sector_rows = [{"sector": k, "weight": round(v, 1)}
                   for k, v in sorted(sector_alloc.items(), key=lambda kv: kv[1], reverse=True)]

    corr = ret_df.corr().round(3)
    holdings = []
    for t, w in zip(tickers, w_arr):
        m = compute_return_metrics(price_df[t], rf)
        holdings.append({
            "ticker": t, "weight": round(float(w) * 100, 1),
            "total_return": round(m["total_return"], 2), "ann_vol": round(m["ann_vol"], 2),
            "sharpe": round(m["sharpe"], 2), "sortino": round(m["sortino"], 2),
            "max_drawdown": round(m["max_drawdown"], 2), "var_95": round(m["var_95"], 2),
        })

    iv = [float(indiv_vols[t]) for t in tickers]
    return {
        "tickers": tickers,
        "weights": [round(float(w) * 100, 1) for w in w_arr],
        "summary": {
            **{k: pm[k] for k in ("total_return", "sharpe", "sortino", "max_drawdown", "var_95")},
            "ann_vol": port_vol, "undiversified_vol": undiversified,
            "diversification_benefit": div_benefit, "diversification_ratio": div_ratio,
            "diversification_level": diversification_level(div_ratio),
        },
        "benchmark": benchmark,
        "cumulative": {
            "dates": [iso(d) for d in port_cum.index],
            "portfolio": series_xy(port_cum)["y"],
            "holdings": {t: series_xy(indiv_cum[t])["y"] for t in tickers},
            "spy": series_xy(spy_cum)["y"] if spy_cum is not None else None,
        },
        "contributions": [
            {"ticker": t, "weight": round(float(w) * 100, 2),
             "ann_vol": round(float(indiv_vols[t]) * 100, 2),
             "risk_contribution": round(float(c), 2)}
            for t, w, c in zip(tickers, w_arr, ctr_pct)
        ],
        "alternatives": [
            {"ticker": t, "current": round(float(w) * 100, 1), "equal": e, "inverse_vol": v}
            for t, w, e, v in zip(tickers, w_arr, equal_weights(len(tickers)), inverse_vol_weights(iv))
        ],
        "correlation": {"tickers": list(corr.columns), "matrix": corr.values.tolist()},
        "sectors": {"rows": sector_rows, "concentration": sector_concentration(sector_rows)},
        "holdings": holdings,
        "metrics": scalar_metrics(pm),
    }
