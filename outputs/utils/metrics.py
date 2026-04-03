# -*- coding: utf-8 -*-
"""Shared metric computations and descriptions."""

import numpy as np
import pandas as pd


def compute_return_metrics(prices: pd.Series, rf_annual: float = 0.05) -> dict:
    """Core risk/return metrics from a price series."""
    daily_ret = prices.pct_change().dropna()
    daily_ret_pct = daily_ret * 100
    rf_daily = rf_annual / 252

    avg = daily_ret.mean()
    std = daily_ret.std()
    downside = daily_ret[daily_ret < 0].std()

    sharpe = (avg - rf_daily) / std * np.sqrt(252) if std != 0 else 0.0
    sortino = (avg - rf_daily) / downside * np.sqrt(252) if downside != 0 else 0.0

    cumulative = (1 + daily_ret).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_dd = drawdown.min() * 100

    var_95 = daily_ret_pct.quantile(0.05)
    cvar_95 = daily_ret_pct[daily_ret_pct <= daily_ret_pct.quantile(0.05)].mean()

    total_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
    ann_return = ((1 + total_return / 100) ** (252 / len(daily_ret)) - 1) * 100 if len(daily_ret) > 0 else 0
    ann_vol = daily_ret_pct.std() * np.sqrt(252)

    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

    return {
        "daily_ret": daily_ret,
        "daily_ret_pct": daily_ret_pct,
        "drawdown_series": drawdown * 100,
        "trading_days": len(daily_ret_pct),
        "avg_daily": daily_ret_pct.mean(),
        "std_daily": daily_ret_pct.std(),
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "total_return": total_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_dd,
        "var_95": var_95,
        "cvar_95": cvar_95,
        "skewness": daily_ret_pct.skew(),
        "kurtosis": daily_ret_pct.kurtosis(),
    }


def compute_benchmark_metrics(
    stock_ret: pd.Series, bench_ret: pd.Series, rf_annual: float = 0.05
) -> dict:
    """Alpha, Beta, R², Treynor, Upside/Downside Capture vs a benchmark."""
    # Align dates
    aligned = pd.concat([stock_ret, bench_ret], axis=1, join="inner").dropna()
    if len(aligned) < 20:
        return {}
    s, b = aligned.iloc[:, 0], aligned.iloc[:, 1]

    # Regression: stock = alpha + beta * benchmark
    cov = np.cov(s, b)
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 0
    alpha_daily = s.mean() - beta * b.mean()
    alpha_annual = alpha_daily * 252

    # R-squared
    ss_res = ((s - (alpha_daily + beta * b)) ** 2).sum()
    ss_tot = ((s - s.mean()) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    # Treynor
    rf_daily = rf_annual / 252
    treynor = (s.mean() - rf_daily) / beta * 252 if beta != 0 else 0

    # Upside / Downside capture
    up_days = b > 0
    down_days = b < 0
    up_capture = (s[up_days].mean() / b[up_days].mean() * 100) if up_days.sum() > 0 else 0
    down_capture = (s[down_days].mean() / b[down_days].mean() * 100) if down_days.sum() > 0 else 0

    return {
        "alpha": alpha_annual,
        "beta": beta,
        "r_squared": r_squared,
        "treynor": treynor,
        "up_capture": up_capture,
        "down_capture": down_capture,
    }


def monthly_returns_table(prices: pd.Series) -> pd.DataFrame:
    """Calendar heatmap: rows = years, cols = months, values = monthly return %."""
    if not isinstance(prices.index, pd.DatetimeIndex):
        return pd.DataFrame()
    try:
        monthly = prices.resample("ME").last().pct_change() * 100
    except Exception:
        monthly = prices.resample("M").last().pct_change() * 100
    monthly = monthly.dropna()
    if monthly.empty:
        return pd.DataFrame()
    table = monthly.groupby([monthly.index.year, monthly.index.month]).first().unstack()
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Only label columns that exist (partial years)
    table.columns = [month_names[c - 1] for c in table.columns]
    table.index.name = "Year"
    return table.round(2)


# ---------------------------------------------------------------------------
# Signal engine — composite quantitative score → Buy / Hold / Sell
# ---------------------------------------------------------------------------

def compute_signal(info: dict, metrics: dict, bench_metrics: dict | None = None) -> dict:
    """
    Score a stock 0–100 across four dimensions, then map to a signal.
    Returns {"signal": "Buy"/"Hold"/"Sell", "score": 0-100, "breakdown": {...}}.
    """
    scores = {}

    # --- 1. VALUATION (0-100, higher = cheaper = better) ---
    val_points = 0
    val_count = 0

    pe = info.get("trailingPE")
    if pe and pe > 0:
        val_count += 1
        if pe < 12:
            val_points += 100
        elif pe < 18:
            val_points += 70
        elif pe < 25:
            val_points += 40
        else:
            val_points += 10

    pb = info.get("priceToBook")
    if pb and pb > 0:
        val_count += 1
        if pb < 1:
            val_points += 100
        elif pb < 2:
            val_points += 70
        elif pb < 4:
            val_points += 40
        else:
            val_points += 10

    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda and ev_ebitda > 0:
        val_count += 1
        if ev_ebitda < 8:
            val_points += 100
        elif ev_ebitda < 12:
            val_points += 70
        elif ev_ebitda < 18:
            val_points += 40
        else:
            val_points += 10

    peg = info.get("pegRatio")
    if peg and peg > 0:
        val_count += 1
        if peg < 1:
            val_points += 100
        elif peg < 1.5:
            val_points += 70
        elif peg < 2.5:
            val_points += 40
        else:
            val_points += 10

    scores["Valuation"] = val_points / val_count if val_count > 0 else 50

    # --- 2. QUALITY (0-100) ---
    qual_points = 0
    qual_count = 0

    roe = info.get("returnOnEquity")
    if roe is not None:
        qual_count += 1
        if roe > 0.25:
            qual_points += 100
        elif roe > 0.15:
            qual_points += 75
        elif roe > 0.08:
            qual_points += 45
        else:
            qual_points += 10

    margin = info.get("profitMargins")
    if margin is not None:
        qual_count += 1
        if margin > 0.20:
            qual_points += 100
        elif margin > 0.10:
            qual_points += 70
        elif margin > 0.03:
            qual_points += 40
        else:
            qual_points += 10

    de = info.get("debtToEquity")
    if de is not None:
        qual_count += 1
        if de < 50:
            qual_points += 100
        elif de < 100:
            qual_points += 70
        elif de < 200:
            qual_points += 40
        else:
            qual_points += 10

    cr = info.get("currentRatio")
    if cr is not None:
        qual_count += 1
        if cr > 2:
            qual_points += 100
        elif cr > 1.5:
            qual_points += 70
        elif cr > 1:
            qual_points += 40
        else:
            qual_points += 10

    scores["Quality"] = qual_points / qual_count if qual_count > 0 else 50

    # --- 3. MOMENTUM / TECHNICAL (0-100) ---
    mom_points = 0
    mom_count = 0

    # Price vs 52-week high
    price = info.get("currentPrice")
    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    if price and high52 and low52 and high52 != low52:
        mom_count += 1
        position = (price - low52) / (high52 - low52)
        if position > 0.8:
            mom_points += 80  # near high — strong momentum
        elif position > 0.5:
            mom_points += 60
        elif position > 0.3:
            mom_points += 50  # middle — neutral
        else:
            mom_points += 30  # beaten down — could be opportunity or trap

    # Recent total return
    tr = metrics.get("total_return", 0)
    mom_count += 1
    if tr > 20:
        mom_points += 85
    elif tr > 5:
        mom_points += 65
    elif tr > -5:
        mom_points += 45
    elif tr > -15:
        mom_points += 25
    else:
        mom_points += 10

    # Earnings growth
    eg = info.get("earningsGrowth")
    if eg is not None:
        mom_count += 1
        if eg > 0.20:
            mom_points += 90
        elif eg > 0.05:
            mom_points += 65
        elif eg > -0.05:
            mom_points += 40
        else:
            mom_points += 15

    scores["Momentum"] = mom_points / mom_count if mom_count > 0 else 50

    # --- 4. RISK (0-100, lower risk = higher score) ---
    risk_points = 0
    risk_count = 0

    sharpe = metrics.get("sharpe", 0)
    risk_count += 1
    if sharpe > 1.5:
        risk_points += 95
    elif sharpe > 0.8:
        risk_points += 70
    elif sharpe > 0.3:
        risk_points += 45
    elif sharpe > 0:
        risk_points += 25
    else:
        risk_points += 10

    mdd = abs(metrics.get("max_drawdown", 0))
    risk_count += 1
    if mdd < 10:
        risk_points += 90
    elif mdd < 20:
        risk_points += 65
    elif mdd < 35:
        risk_points += 40
    else:
        risk_points += 15

    beta_val = info.get("beta")
    if beta_val is not None:
        risk_count += 1
        if 0.5 <= beta_val <= 1.2:
            risk_points += 75
        elif beta_val < 0.5:
            risk_points += 60  # low beta — defensive but could lag
        elif beta_val <= 1.5:
            risk_points += 50
        else:
            risk_points += 20

    # Benchmark alpha bonus
    if bench_metrics and "alpha" in bench_metrics:
        risk_count += 1
        alpha = bench_metrics["alpha"]
        if alpha > 10:
            risk_points += 90
        elif alpha > 0:
            risk_points += 65
        elif alpha > -10:
            risk_points += 35
        else:
            risk_points += 10

    scores["Risk"] = risk_points / risk_count if risk_count > 0 else 50

    # --- COMPOSITE (weighted) ---
    composite = (
        0.30 * scores["Valuation"]
        + 0.25 * scores["Quality"]
        + 0.20 * scores["Momentum"]
        + 0.25 * scores["Risk"]
    )

    if composite >= 68:
        signal = "Buy"
    elif composite >= 45:
        signal = "Hold"
    else:
        signal = "Sell"

    return {"signal": signal, "score": round(composite, 1), "breakdown": scores}


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------

METRIC_DESC = {
    "trading_days": "Number of market days with price data in the selected period.",
    "total_return": "Total percentage gain or loss from start to end of the period.",
    "ann_return": "Total return scaled to an annualised rate for easier comparison across time horizons.",
    "avg_daily": "The average single-day return. Small daily numbers compound over time.",
    "std_daily": "How much daily returns typically vary from the average — higher means more day-to-day swings.",
    "ann_vol": "Daily standard deviation scaled to a year (×√252). A common way to compare volatility across stocks.",
    "sharpe": "Return earned per unit of total risk, after subtracting the risk-free rate. Above 1 is generally good.",
    "sortino": "Like Sharpe, but only penalises downside moves. More relevant if you care about losses specifically.",
    "calmar": "Annualised return ÷ max drawdown. Measures return per unit of worst-case pain. Higher is better.",
    "max_drawdown": "The worst peak-to-trough drop in the period. Answers: \"what's the most I could have lost?\"",
    "var_95": "The 5th-percentile daily return. On 95% of trading days the loss was smaller than this.",
    "cvar_95": "Average loss on the worst 5% of days. Goes beyond VaR to show how bad the tail actually is.",
    "skewness": "Whether returns lean left or right. Negative skew = extreme losses more common than extreme gains.",
    "kurtosis": "How fat the tails are vs. a normal distribution. Higher = more frequent extreme moves.",
    "alpha": "Excess return vs. the benchmark after adjusting for beta. Positive alpha = outperformance.",
    "beta": "Sensitivity to the market. Above 1 = amplifies market moves; below 1 = dampens them.",
    "r_squared": "How much of the stock's movement is explained by the benchmark. Above 0.7 = closely tracks the market.",
    "treynor": "Return per unit of systematic (market) risk. Like Sharpe but uses beta instead of total volatility.",
    "up_capture": "What % of the benchmark's up-day returns the stock captures. Above 100 = amplifies gains.",
    "down_capture": "What % of the benchmark's down-day losses the stock captures. Below 100 = absorbs less pain.",
}

FUNDAMENTAL_DESC = {
    "trailingPE": "Price ÷ last 12 months' earnings. Lower may signal undervaluation — but check why it's low.",
    "forwardPE": "Price ÷ expected next-year earnings. Lower suggests the market expects less growth.",
    "priceToBook": "Price ÷ book value per share. Below 1 means the market values the company below its net assets.",
    "enterpriseToEbitda": "Enterprise value ÷ EBITDA. A debt-adjusted 'cheapness' measure. Under 10 is often considered cheap.",
    "pegRatio": "P/E ÷ earnings growth rate. Below 1 suggests you're paying less than the growth warrants.",
    "dividendYield": "Annual dividend ÷ share price. Higher yield can mean income — or a stock the market is discounting.",
    "returnOnEquity": "Net income ÷ shareholder equity. Measures capital efficiency. Above 15% is strong.",
    "debtToEquity": "Total debt ÷ equity. Higher means more leverage. Above 200 warrants scrutiny in most sectors.",
    "profitMargins": "Net income ÷ revenue. Higher margins generally mean a stronger competitive position.",
    "revenueGrowth": "Year-over-year revenue change. Positive and accelerating is what growth investors look for.",
    "earningsGrowth": "Year-over-year earnings change. Drives forward P/E compression when strong.",
    "currentRatio": "Current assets ÷ current liabilities. Above 1.5 is healthy; below 1 is a liquidity warning.",
    "beta": "Sensitivity to market moves. Above 1 = more volatile than the market; below 1 = less.",
    "pct_below_52w_high": "How far the stock is from its 52-week high. Larger gap may signal a beaten-down opportunity.",
}


def metric_card(container, label: str, value: str, key: str, descs: dict | None = None):
    descs = descs or METRIC_DESC
    container.metric(label, value)
    desc = descs.get(key, "")
    if desc:
        container.caption(desc)
