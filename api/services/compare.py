# -*- coding: utf-8 -*-
"""Side-by-side comparison (ported from pages/3_Compare_Stocks.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from api.serialize import iso, series_xy
from api.services.common import ServiceError
from utils.metrics import compute_return_metrics, compute_technical_signals
from utils.prescription import generate_prescription

RISK_ROWS = [
    ("Total Return (%)", "total_return", 2), ("Avg Daily Return (%)", "avg_daily", 4),
    ("Std Deviation (%)", "std_daily", 4), ("Annualized Vol (%)", "ann_vol", 2),
    ("Sharpe Ratio", "sharpe", 2), ("Sortino Ratio", "sortino", 2),
    ("Max Drawdown (%)", "max_drawdown", 2), ("VaR 95% (%)", "var_95", 2),
    ("Skewness", "skewness", 2), ("Kurtosis", "kurtosis", 2),
]

FUND_FIELDS = {
    "shortName": "Company", "sector": "Sector", "marketCap": "Market Cap",
    "trailingPE": "P/E", "forwardPE": "Fwd P/E", "priceToBook": "P/B",
    "enterpriseToEbitda": "EV/EBITDA", "pegRatio": "PEG", "dividendYield": "Div Yield",
    "returnOnEquity": "ROE", "profitMargins": "Margin", "revenueGrowth": "Rev Growth",
    "debtToEquity": "D/E", "beta": "Beta",
}
LOWER_IS_BETTER = {"P/E", "Fwd P/E", "P/B", "EV/EBITDA", "PEG", "D/E"}
NOT_RANKED = {"Company", "Sector", "Market Cap"}
PCT_FIELDS = {"dividendYield", "returnOnEquity", "profitMargins", "revenueGrowth"}


def format_fundamental(key: str, val) -> str:
    """Display string for one fundamentals cell, identical to the Streamlit table."""
    if val is None:
        return "—"
    if key == "marketCap":
        return f"${val / 1e9:.1f}B"
    if key in PCT_FIELDS:
        return f"{val * 100:.1f}%"
    if key == "debtToEquity":
        return f"{val:.0f}"
    return f"{val:.2f}" if isinstance(val, float) else str(val)


def best_tickers(label: str, raw: dict) -> list[str]:
    """Tickers holding the best numeric value in a row (ties all win); [] when not ranked."""
    if label in NOT_RANKED:
        return []
    nums = {t: pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0] for t, v in raw.items()}
    valid = {t: float(v) for t, v in nums.items() if not pd.isna(v)}
    if not valid:
        return []
    best = min(valid.values()) if label in LOWER_IS_BETTER else max(valid.values())
    return [t for t, v in valid.items() if v == best]


def correlation_read(avg: float) -> str:
    if avg >= 0.8:
        return "warning"
    if avg >= 0.6:
        return "info"
    return "success"


def build_compare(tickers: list[str], horizon: str, rf: float, benchmark: bool,
                  profile: str, data) -> dict:
    prices, metrics, info, errors = {}, {}, {}, []
    for t in tickers:
        hist = data.get_price_history(t, horizon)
        if hist.empty:
            errors.append(t)
            continue
        prices[t] = hist["Close"]
        metrics[t] = compute_return_metrics(hist["Close"], rf)
        info[t] = data.get_ticker_info(t) or {}
    if benchmark:
        spy = data.get_price_history("SPY", horizon)
        if not spy.empty:
            prices["SPY"] = spy["Close"]
            metrics["SPY"] = compute_return_metrics(spy["Close"], rf)

    valid = [t for t in tickers if t in metrics]
    if len(valid) < 2:
        raise ServiceError("Need at least 2 valid tickers. Check symbols and try again.")
    has_spy = "SPY" in metrics
    with_spy = valid + (["SPY"] if has_spy else [])

    macro = data.get_macro_snapshot()
    verdicts = {}
    for t in valid:
        p = generate_prescription(info[t], compute_technical_signals(prices[t]), macro, profile=profile)
        verdicts[t] = {k: p[k] for k in ("verdict", "confidence", "composite_score", "thesis")}

    price_df = pd.DataFrame(prices).dropna(how="all").ffill().dropna()
    norm = price_df.div(price_df.iloc[0]) if not price_df.empty else price_df
    totals = []
    for t in with_spy:
        v = metrics[t]["total_return"]
        totals.append({"ticker": t, "value": v,
                       "vs_spy": (v - metrics["SPY"]["total_return"]) if has_spy and t != "SPY" else None})

    risk_rows = {t: {label: round(metrics[t][key], nd) for label, key, nd in RISK_ROWS} for t in with_spy}

    fund_rows = []
    for key, label in FUND_FIELDS.items():
        raw = {t: info[t].get(key) for t in valid}
        best = best_tickers(label, raw)
        fund_rows.append({
            "label": label, "key": key,
            "values": {t: {"display": format_fundamental(key, raw[t]), "raw": raw[t],
                           "best": t in best} for t in valid},
        })

    returns_df = pd.DataFrame({t: metrics[t]["daily_ret_pct"] for t in with_spy})
    corr = returns_df.corr().round(3)
    names = [c for c in corr.columns if c != "SPY"]
    off = [corr.loc[a, b] for i, a in enumerate(names) for b in names[i + 1:]]
    avg = float(np.mean(off)) if off else None

    return {
        "tickers": valid, "errors": errors, "benchmark": has_spy, "profile": profile,
        "verdicts": verdicts,
        "performance": {
            "dates": [iso(d) for d in norm.index],
            "series": {c: series_xy(norm[c])["y"] for c in norm.columns},
            "total_return": totals,
        },
        "risk": {"labels": [r[0] for r in RISK_ROWS], "tickers": with_spy, "rows": risk_rows,
                 "scatter": [{"ticker": t, "ann_vol": metrics[t]["ann_vol"],
                              "total_return": metrics[t]["total_return"]} for t in with_spy]},
        "fundamentals": fund_rows,
        "correlation": {"tickers": list(corr.columns), "matrix": corr.values.tolist(),
                        "avg_pairwise": avg,
                        "level": correlation_read(avg) if avg is not None else None},
    }
