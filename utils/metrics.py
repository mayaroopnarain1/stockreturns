# -*- coding: utf-8 -*-
"""
Shared metric computations used across multiple pages.
"""

import numpy as np
import pandas as pd


def compute_return_metrics(prices: pd.Series, rf_annual: float = 0.05) -> dict:
    """
    Compute risk/return metrics from a price series.
    Returns a dict with all scalar metrics plus the daily-return series.
    """
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

    total_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100

    return {
        "daily_ret": daily_ret,
        "daily_ret_pct": daily_ret_pct,
        "trading_days": len(daily_ret_pct),
        "avg_daily": daily_ret_pct.mean(),
        "std_daily": daily_ret_pct.std(),
        "ann_vol": daily_ret_pct.std() * np.sqrt(252),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "var_95": var_95,
        "skewness": daily_ret_pct.skew(),
        "kurtosis": daily_ret_pct.kurtosis(),
        "total_return": total_return,
    }


# ---------------------------------------------------------------------------
# Metric descriptions — plain-English, one-liner explanations
# ---------------------------------------------------------------------------

METRIC_DESC: dict[str, str] = {
    "trading_days": "Number of market days with price data in the selected period.",
    "total_return": "Total percentage gain or loss from start to end of the period.",
    "avg_daily": "The average single-day return. Small daily numbers compound over time.",
    "std_daily": "How much daily returns typically vary from the average — higher means more day-to-day swings.",
    "ann_vol": "Daily standard deviation scaled to a year (×√252). A common way to compare volatility across stocks.",
    "sharpe": "Return earned per unit of total risk, after subtracting the risk-free rate. Above 1 is generally good.",
    "sortino": "Like Sharpe, but only penalises downside moves. More relevant if you care about losses specifically.",
    "max_drawdown": "The worst peak-to-trough drop in the period. Answers: \"what's the most I could have lost?\"",
    "var_95": "The 5th-percentile daily return. On 95% of trading days the loss was smaller than this.",
    "skewness": "Whether returns lean left or right. Negative skew = extreme losses more common than extreme gains.",
    "kurtosis": "How fat the tails are vs. a normal distribution. Higher = more frequent extreme moves.",
}

# Fundamental metric descriptions for the screener
FUNDAMENTAL_DESC: dict[str, str] = {
    "trailingPE": "Price ÷ last 12 months' earnings. Lower may signal undervaluation — but check why it's low.",
    "forwardPE": "Price ÷ expected next-year earnings. Lower suggests the market expects less growth.",
    "priceToBook": "Price ÷ book value per share. Below 1 means the market values the company below its net assets.",
    "enterpriseToEbitda": "Enterprise value ÷ EBITDA. A debt-adjusted 'cheapness' measure. Under 10 is often considered cheap.",
    "pegRatio": "P/E ÷ earnings growth rate. Below 1 suggests you're paying less than the growth warrants.",
    "dividendYield": "Annual dividend ÷ share price. Higher yield can mean income — or a stock the market is discounting.",
    "returnOnEquity": "Net income ÷ shareholder equity. Measures how efficiently a company uses invested capital. Above 15% is strong.",
    "debtToEquity": "Total debt ÷ equity. Higher means more leverage. Above 2 warrants scrutiny in most sectors.",
    "profitMargins": "Net income ÷ revenue. Higher margins generally mean a stronger competitive position.",
    "revenueGrowth": "Year-over-year revenue change. Positive and accelerating is what growth investors look for.",
    "earningsGrowth": "Year-over-year earnings change. Drives forward P/E compression when strong.",
    "currentRatio": "Current assets ÷ current liabilities. Above 1.5 is healthy; below 1 is a liquidity warning.",
    "beta": "Sensitivity to market moves. Above 1 = more volatile than the market; below 1 = less.",
    "pct_below_52w_high": "How far the stock is from its 52-week high. Larger gap may signal a beaten-down opportunity.",
}


def metric_card(container, label: str, value: str, key: str, descs: dict | None = None) -> None:
    """Render a st.metric card followed by a small description caption."""
    descs = descs or METRIC_DESC
    container.metric(label, value)
    desc = descs.get(key, "")
    if desc:
        container.caption(desc)
