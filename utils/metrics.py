# -*- coding: utf-8 -*-
"""Shared metric computations and descriptions."""
from __future__ import annotations

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

    # Regression on excess returns: (R_s - Rf) = alpha + beta * (R_m - Rf)
    rf_daily = rf_annual / 252
    cov = np.cov(s, b)
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 0
    alpha_daily = (s.mean() - rf_daily) - beta * (b.mean() - rf_daily)
    alpha_annual = alpha_daily * 252

    # R-squared (on raw returns — R² is scale-invariant)
    ss_res = ((s - (s.mean() + beta * (b - b.mean()))) ** 2).sum()
    ss_tot = ((s - s.mean()) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    # Treynor
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
# Signal engine v2 — 5-dimension composite score → Buy / Hold / Sell
#
# Key changes from v1:
#   • Dropped P/B (meaningless for buyback-heavy companies like AAPL)
#   • Added forward P/E and FCF yield to valuation
#   • Sector-relative scoring uses smooth sigmoid instead of hard buckets
#   • Quality: capped ROE sensitivity at 50%, dropped current ratio, added gross margin
#   • NEW 5th dimension: Consensus (analyst target price upside + recommendation)
#   • Rebalanced weights: Val 20%, Quality 25%, Momentum 15%, Risk 20%, Consensus 20%
#   • Lower signal thresholds: Buy ≥ 62, Hold ≥ 40, Sell < 40
# ---------------------------------------------------------------------------

# Sector median fundamentals (trailing P/E, forward P/E, EV/EBITDA).
# Updated from S&P 500 data April 2026.
SECTOR_MEDIANS: dict = {
    "Technology":             {"tpe": 28.0, "fpe": 24.0, "ev": 20.0},
    "Financial Services":     {"tpe": 14.0, "fpe": 12.0, "ev": 12.0},
    "Healthcare":             {"tpe": 25.0, "fpe": 20.0, "ev": 15.0},
    "Industrials":            {"tpe": 22.0, "fpe": 19.0, "ev": 15.0},
    "Consumer Cyclical":      {"tpe": 22.0, "fpe": 18.0, "ev": 14.0},
    "Consumer Defensive":     {"tpe": 22.0, "fpe": 19.0, "ev": 14.0},
    "Energy":                 {"tpe": 14.0, "fpe": 12.0, "ev":  8.0},
    "Utilities":              {"tpe": 20.0, "fpe": 17.0, "ev": 13.0},
    "Communication Services": {"tpe": 18.0, "fpe": 15.0, "ev": 11.0},
    "Real Estate":            {"tpe": 35.0, "fpe": 30.0, "ev": 20.0},
    "Basic Materials":        {"tpe": 18.0, "fpe": 15.0, "ev": 10.0},
}
_DEFAULT_MEDIANS = {"tpe": 21.0, "fpe": 18.0, "ev": 14.0}


def _smooth_score(value: float, median: float, lower_is_better: bool = True) -> float:
    """Smooth sigmoid-style scoring vs sector median. Returns 0-100.
    Uses a continuous curve so small changes don't cause big score jumps."""
    if median <= 0:
        return 50.0
    ratio = value / median
    if lower_is_better:
        # ratio < 1 = cheap = high score; ratio > 1 = expensive = low score
        # Sigmoid centered at ratio=1, steepness tuned so 0.6x→~90, 1.5x→~15
        x = (1.0 - ratio) * 4.0  # scale factor controls steepness
    else:
        # Higher is better (e.g., margins)
        x = (ratio - 1.0) * 4.0
    # Sigmoid: maps x ∈ (-∞, ∞) → (0, 100)
    import math
    try:
        score = 100.0 / (1.0 + math.exp(-x))
    except OverflowError:
        score = 100.0 if x > 0 else 0.0
    return round(max(5.0, min(95.0, score)), 1)  # clamp to [5, 95]


def compute_signal(info: dict, metrics: dict, bench_metrics: dict | None = None) -> dict:
    """
    Score a stock 0–100 across five dimensions, then map to Buy / Hold / Sell.

    Dimensions & weights:
        Valuation  20%  — trailing P/E, forward P/E, EV/EBITDA, FCF yield (sector-relative)
        Quality    25%  — ROE (capped), profit margin, gross margin, D/E
        Momentum   15%  — 52w position, total return, earnings growth, revenue growth
        Risk       20%  — Sharpe, max drawdown, beta, alpha
        Consensus  20%  — analyst target upside %, recommendation mean

    Returns {"signal", "score", "breakdown", "why", "reasons", "weights"}.
    """
    scores = {}
    reasons: dict[str, str] = {}
    weights = {
        "Valuation": 0.20,
        "Quality": 0.25,
        "Momentum": 0.15,
        "Risk": 0.20,
        "Consensus": 0.20,
    }

    sector = info.get("sector", "")
    med = SECTOR_MEDIANS.get(sector, _DEFAULT_MEDIANS)

    # ── 1. VALUATION (sector-relative, 0-100, lower multiples = higher score) ──
    val_scores = []
    val_notes = []

    # Trailing P/E
    tpe = info.get("trailingPE")
    if tpe and 0 < tpe < 500:
        s = _smooth_score(tpe, med["tpe"], lower_is_better=True)
        val_scores.append(s)
        if s >= 65:
            val_notes.append(f"trailing P/E ({tpe:.1f}) looks cheap vs {sector or 'market'} median ({med['tpe']:.0f})")
        elif s <= 35:
            val_notes.append(f"trailing P/E ({tpe:.1f}) is rich vs {sector or 'market'} median ({med['tpe']:.0f})")

    # Forward P/E (weighted slightly more — forward-looking)
    fpe = info.get("forwardPE")
    if fpe and 0 < fpe < 500:
        s = _smooth_score(fpe, med["fpe"], lower_is_better=True)
        val_scores.append(s)
        val_scores.append(s)  # double-counted = 2x weight within valuation
        if s >= 65:
            val_notes.append(f"forward P/E ({fpe:.1f}) suggests earnings growth will compress valuation")

    # EV/EBITDA
    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda and 0 < ev_ebitda < 200:
        s = _smooth_score(ev_ebitda, med["ev"], lower_is_better=True)
        val_scores.append(s)

    # FCF Yield = freeCashflow / marketCap (higher = cheaper = better)
    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")
    if fcf and mcap and mcap > 0:
        fcf_yield = fcf / mcap
        # Score: >8% = excellent, ~4% = average, <2% = poor
        if fcf_yield > 0.08:
            fcf_s = 90.0
        elif fcf_yield > 0.05:
            fcf_s = 75.0
        elif fcf_yield > 0.03:
            fcf_s = 60.0
        elif fcf_yield > 0.01:
            fcf_s = 40.0
        elif fcf_yield > 0:
            fcf_s = 25.0
        else:
            fcf_s = 10.0  # negative FCF
        val_scores.append(fcf_s)
        if fcf_yield > 0.05:
            val_notes.append(f"strong {fcf_yield*100:.1f}% FCF yield")
        elif fcf_yield <= 0:
            val_notes.append("negative free cash flow")

    scores["Valuation"] = sum(val_scores) / len(val_scores) if val_scores else 50.0
    reasons["Valuation"] = "; ".join(val_notes) if val_notes else (
        "valuation roughly in line with sector peers" if scores["Valuation"] >= 40
        else "looks expensive relative to sector peers"
    )

    # ── 2. QUALITY (0-100) ─────────────────────────────────────────────────────
    qual_scores = []
    qual_notes = []

    # ROE — capped at 50% to avoid rewarding financial engineering (buybacks)
    roe = info.get("returnOnEquity")
    if roe is not None:
        effective_roe = min(roe, 0.50)  # cap at 50%
        # 15% = decent baseline
        if effective_roe > 0.25:
            qs = 90.0
        elif effective_roe > 0.15:
            qs = 70.0
        elif effective_roe > 0.08:
            qs = 50.0
        elif effective_roe > 0:
            qs = 30.0
        else:
            qs = 10.0
        qual_scores.append(qs)
        if effective_roe > 0.20:
            qual_notes.append(f"ROE is strong ({roe*100:.0f}%)")
        elif effective_roe < 0.05:
            qual_notes.append(f"ROE is weak ({roe*100:.0f}%)")

    # Profit margin
    margin = info.get("profitMargins")
    if margin is not None:
        if margin > 0.25:
            ms = 90.0
        elif margin > 0.15:
            ms = 75.0
        elif margin > 0.08:
            ms = 55.0
        elif margin > 0.03:
            ms = 35.0
        elif margin > 0:
            ms = 20.0
        else:
            ms = 5.0
        qual_scores.append(ms)
        if margin > 0.20:
            qual_notes.append(f"strong {margin*100:.0f}% profit margins")
        elif margin < 0.03:
            qual_notes.append(f"thin {margin*100:.1f}% profit margins")

    # Gross margin (competitive moat indicator)
    gross_margin = info.get("grossMargins")
    if gross_margin is not None:
        if gross_margin > 0.60:
            gms = 90.0
        elif gross_margin > 0.40:
            gms = 70.0
        elif gross_margin > 0.25:
            gms = 50.0
        elif gross_margin > 0.15:
            gms = 30.0
        else:
            gms = 15.0
        qual_scores.append(gms)
        if gross_margin > 0.55:
            qual_notes.append(f"high {gross_margin*100:.0f}% gross margins suggest pricing power")

    # Debt/Equity — sector-aware (financials naturally run higher)
    de = info.get("debtToEquity")
    if de is not None:
        de_threshold = 200 if sector == "Financial Services" else 100
        if de < de_threshold * 0.5:
            des = 85.0
        elif de < de_threshold:
            des = 65.0
        elif de < de_threshold * 2:
            des = 40.0
        else:
            des = 15.0
        qual_scores.append(des)
        if de > de_threshold * 1.5:
            qual_notes.append(f"elevated leverage (D/E {de:.0f})")

    scores["Quality"] = sum(qual_scores) / len(qual_scores) if qual_scores else 50.0
    reasons["Quality"] = "; ".join(qual_notes) if qual_notes else "quality metrics are average"

    # ── 3. MOMENTUM (0-100) ────────────────────────────────────────────────────
    mom_scores = []
    mom_notes = []

    # 52-week range position
    price = info.get("currentPrice")
    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    if price and high52 and low52 and high52 != low52:
        position = (price - low52) / (high52 - low52)
        # Near highs = strong momentum
        pos_score = 20.0 + position * 70.0  # maps 0→20, 1→90
        mom_scores.append(min(90.0, pos_score))
        if position > 0.85:
            mom_notes.append("trading near 52-week high")
        elif position < 0.30:
            pct_off = (high52 - price) / high52 * 100
            mom_notes.append(f"{pct_off:.0f}% below 52-week high")

    # Total return over analysis period
    tr = metrics.get("total_return", 0)
    if tr > 30:
        mom_scores.append(90.0)
        mom_notes.append(f"strong {tr:.0f}% return")
    elif tr > 15:
        mom_scores.append(75.0)
    elif tr > 5:
        mom_scores.append(60.0)
    elif tr > -5:
        mom_scores.append(45.0)
    elif tr > -15:
        mom_scores.append(25.0)
        mom_notes.append(f"{tr:.0f}% return dragging momentum")
    else:
        mom_scores.append(10.0)
        mom_notes.append(f"steep {tr:.0f}% decline")

    # Earnings growth
    eg = info.get("earningsGrowth")
    if eg is not None:
        if eg > 0.25:
            mom_scores.append(90.0)
            mom_notes.append(f"earnings growing {eg*100:.0f}%")
        elif eg > 0.10:
            mom_scores.append(70.0)
        elif eg > 0:
            mom_scores.append(55.0)
        elif eg > -0.10:
            mom_scores.append(35.0)
        else:
            mom_scores.append(15.0)
            mom_notes.append(f"earnings declining {eg*100:.0f}%")

    # Revenue growth
    rg = info.get("revenueGrowth")
    if rg is not None:
        if rg > 0.20:
            mom_scores.append(85.0)
        elif rg > 0.10:
            mom_scores.append(70.0)
        elif rg > 0.03:
            mom_scores.append(55.0)
        elif rg > -0.03:
            mom_scores.append(40.0)
        else:
            mom_scores.append(20.0)

    scores["Momentum"] = sum(mom_scores) / len(mom_scores) if mom_scores else 50.0
    reasons["Momentum"] = "; ".join(mom_notes) if mom_notes else "momentum is neutral"

    # ── 4. RISK (0-100, lower risk = higher score) ────────────────────────────
    risk_scores = []
    risk_notes = []

    # Sharpe ratio
    sharpe = metrics.get("sharpe", 0)
    if sharpe > 1.5:
        risk_scores.append(90.0)
        risk_notes.append(f"excellent risk-adjusted returns (Sharpe {sharpe:.2f})")
    elif sharpe > 1.0:
        risk_scores.append(75.0)
    elif sharpe > 0.5:
        risk_scores.append(55.0)
    elif sharpe > 0:
        risk_scores.append(35.0)
    else:
        risk_scores.append(15.0)
        risk_notes.append(f"poor risk-adjusted returns (Sharpe {sharpe:.2f})")

    # Max drawdown
    mdd = abs(metrics.get("max_drawdown", 0))
    if mdd < 10:
        risk_scores.append(85.0)
    elif mdd < 20:
        risk_scores.append(65.0)
    elif mdd < 30:
        risk_scores.append(45.0)
    elif mdd < 40:
        risk_scores.append(25.0)
    else:
        risk_scores.append(10.0)
        risk_notes.append(f"deep {mdd:.0f}% max drawdown")

    # Beta
    beta_val = info.get("beta")
    if beta_val is not None:
        if 0.7 <= beta_val <= 1.3:
            risk_scores.append(70.0)
        elif 0.4 <= beta_val <= 1.5:
            risk_scores.append(50.0)
        elif beta_val < 0.4:
            risk_scores.append(55.0)  # very low beta is fine
        else:
            risk_scores.append(20.0)
            risk_notes.append(f"high beta ({beta_val:.2f}) amplifies market swings")

    # Alpha vs benchmark
    if bench_metrics and "alpha" in bench_metrics:
        alpha = bench_metrics["alpha"]
        if alpha > 15:
            risk_scores.append(90.0)
            risk_notes.append(f"strong alpha ({alpha:.1f}%) vs benchmark")
        elif alpha > 5:
            risk_scores.append(72.0)
        elif alpha > 0:
            risk_scores.append(55.0)
        elif alpha > -10:
            risk_scores.append(35.0)
        else:
            risk_scores.append(15.0)
            risk_notes.append(f"negative alpha ({alpha:.1f}%) vs benchmark")

    scores["Risk"] = sum(risk_scores) / len(risk_scores) if risk_scores else 50.0
    reasons["Risk"] = "; ".join(risk_notes) if risk_notes else "risk profile is moderate"

    # ── 5. CONSENSUS (0-100, NEW dimension) ───────────────────────────────────
    cons_scores = []
    cons_notes = []

    # Analyst target price upside
    target = info.get("targetMeanPrice")
    cur = info.get("currentPrice")
    if target and cur and cur > 0:
        upside = (target / cur - 1) * 100
        # Map upside to score: >30% = 90, ~15% = 70, ~0% = 40, <-10% = 15
        if upside > 30:
            cs = 90.0
        elif upside > 15:
            cs = 75.0
        elif upside > 5:
            cs = 60.0
        elif upside > -5:
            cs = 40.0
        elif upside > -15:
            cs = 25.0
        else:
            cs = 10.0
        cons_scores.append(cs)
        cons_scores.append(cs)  # double-weight upside (most actionable)
        if upside > 20:
            cons_notes.append(f"analysts see {upside:.0f}% upside to ${target:.0f}")
        elif upside < -5:
            cons_notes.append(f"analysts see {upside:.0f}% downside")

    # Recommendation mean (1 = Strong Buy, 5 = Strong Sell)
    rec = info.get("recommendationMean")
    if rec and 1 <= rec <= 5:
        # 1→95, 2→75, 3→50, 4→25, 5→5
        rec_score = max(5.0, min(95.0, 95.0 - (rec - 1) * 22.5))
        cons_scores.append(rec_score)
        rec_labels = {1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Sell", 5: "Strong Sell"}
        nearest = rec_labels.get(round(rec), f"{rec:.1f}")
        if rec <= 2.0:
            cons_notes.append(f"Wall Street consensus is {nearest} ({rec:.1f})")
        elif rec >= 3.5:
            cons_notes.append(f"Wall Street consensus is cautious ({nearest}, {rec:.1f})")

    # Number of analysts (confidence weight — more coverage = more reliable)
    n_analysts = info.get("numberOfAnalystOpinions")
    if n_analysts is not None and n_analysts < 5:
        cons_notes.append(f"only {n_analysts} analysts cover this stock (low confidence)")

    scores["Consensus"] = sum(cons_scores) / len(cons_scores) if cons_scores else 50.0
    reasons["Consensus"] = "; ".join(cons_notes) if cons_notes else "limited analyst coverage"

    # ── COMPOSITE (weighted) ──────────────────────────────────────────────────
    composite = sum(weights[d] * scores[d] for d in weights)

    if composite >= 62:
        signal = "Buy"
    elif composite >= 40:
        signal = "Hold"
    else:
        signal = "Sell"

    # ── WHY (plain-English summary) ───────────────────────────────────────────
    dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best = dims[0]
    worst = dims[-1]
    why = (
        f"**{best[0]}** ({best[1]:.0f}/100) is the strongest dimension"
        f" — {reasons[best[0]]}. "
        f"**{worst[0]}** ({worst[1]:.0f}/100) is the weakest"
        f" — {reasons[worst[0]]}."
    )

    return {
        "signal": signal,
        "score": round(composite, 1),
        "breakdown": scores,
        "weights": weights,
        "why": why,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------

METRIC_DESC = {
    "trading_days": "Number of market days with price data in the selected period.",
    "total_return": "Total percentage gain or loss from start to end of the period.",
    "ann_return": "Total return scaled to an annualized rate for easier comparison across time horizons.",
    "avg_daily": "The average single-day return. Small daily numbers compound over time.",
    "std_daily": "How much daily returns typically vary from the average — higher means more day-to-day swings.",
    "ann_vol": "Daily standard deviation scaled to a year (×√252). A common way to compare volatility across stocks.",
    "sharpe": "Return earned per unit of total risk, after subtracting the risk-free rate. Above 1 is generally good.",
    "sortino": "Like Sharpe, but only penalizes downside moves. More relevant if you care about losses specifically.",
    "calmar": "Annualized return ÷ max drawdown. Measures return per unit of worst-case pain. Higher is better.",
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


# ---------------------------------------------------------------------------
# Prescriptive Action Engine
# ---------------------------------------------------------------------------

# Sector → friendly group name (for portfolio concentration checks)
SECTOR_GROUPS: dict[str, str] = {
    "Technology": "Tech", "Financial Services": "Financials",
    "Healthcare": "Healthcare", "Industrials": "Industrials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Energy": "Energy", "Utilities": "Utilities",
    "Communication Services": "Communication",
    "Real Estate": "Real Estate", "Basic Materials": "Materials",
}


def generate_prescription(
    signal_result: dict,
    info: dict,
    profile: dict,
    macro: dict | None = None,
    portfolio_holdings: list[str] | None = None,
    portfolio_info: dict[str, dict] | None = None,
) -> dict:
    """
    Generate a prescriptive action recommendation based on the composite
    signal, the investor's profile, macro context, and current portfolio.

    Parameters
    ----------
    signal_result : dict from compute_signal()
    info : dict from yfinance ticker.info
    profile : {"risk_tolerance": str, "goal": str, "horizon": str}
        risk_tolerance: "conservative", "moderate", "aggressive"
        goal: "growth", "income", "balanced"
        horizon: "short", "medium", "long"
    macro : dict from fetch_macro_context() or None
    portfolio_holdings : list of ticker symbols the user currently holds
    portfolio_info : dict mapping ticker → yfinance info dict (for sector checks)

    Returns
    -------
    dict with keys:
        action: str — the headline recommendation
        sizing: str — position sizing guidance
        entry_strategy: str — how to enter
        reasoning: list[str] — bullet-point rationale
        warnings: list[str] — risk factors to watch
        confidence: str — "High", "Medium", "Low"
        portfolio_note: str or None — portfolio-aware insight
    """
    score = signal_result["score"]
    sig = signal_result["signal"]
    breakdown = signal_result["breakdown"]
    reasons = signal_result["reasons"]

    rt = profile.get("risk_tolerance", "moderate")
    goal = profile.get("goal", "balanced")
    hor = profile.get("horizon", "medium")

    ticker = info.get("symbol", info.get("shortName", "this stock"))
    sector = info.get("sector", "Unknown")

    # ── Profile-adjusted thresholds ──────────────────────────────────────
    # Conservative investors need a higher score to get a "Buy" action
    buy_threshold = {"conservative": 68, "moderate": 62, "aggressive": 55}[rt]
    strong_buy_threshold = {"conservative": 78, "moderate": 72, "aggressive": 65}[rt]
    avoid_threshold = {"conservative": 50, "moderate": 40, "aggressive": 32}[rt]

    # ── Determine action ─────────────────────────────────────────────────
    action = ""
    sizing = ""
    entry_strategy = ""
    reasoning_points = []
    warnings = []

    # Volatility & drawdown info for entry strategy
    max_dd = abs(signal_result["breakdown"].get("Risk", 50))
    vix = macro.get("vix") if macro else None
    tnx = macro.get("tnx") if macro else None
    beta_val = info.get("beta", 1.0)
    dividend_yield = info.get("dividendYield")
    n_analysts = info.get("numberOfAnalystOpinions", 0) or 0

    if score >= strong_buy_threshold:
        action = "Buy — strong conviction"
        if rt == "aggressive":
            sizing = "Consider a 5–8% position"
        elif rt == "moderate":
            sizing = "Consider a 3–5% position"
        else:
            sizing = "Consider a 2–4% position"
        reasoning_points.append(
            f"Composite score of {score:.0f}/100 clears your {rt} Buy threshold ({buy_threshold}) with room to spare"
        )
    elif score >= buy_threshold:
        action = "Buy — start a position"
        if rt == "aggressive":
            sizing = "Consider a 3–5% position"
        elif rt == "moderate":
            sizing = "Consider a 2–4% position"
        else:
            sizing = "Consider a 1–3% position"
        reasoning_points.append(
            f"Score of {score:.0f}/100 crosses your {rt} Buy threshold ({buy_threshold})"
        )
    elif score >= avoid_threshold:
        action = "Hold — not compelling enough to add"
        sizing = "No new capital recommended"
        reasoning_points.append(
            f"Score of {score:.0f}/100 is in the Hold zone for a {rt} investor"
        )
    else:
        action = "Avoid — or trim if you own it"
        sizing = "Reduce exposure or stay out"
        reasoning_points.append(
            f"Score of {score:.0f}/100 falls below your {rt} Avoid threshold ({avoid_threshold})"
        )

    # ── Entry strategy (based on volatility + macro) ─────────────────────
    high_vol = (vix and vix > 20) or (beta_val and beta_val > 1.3)

    if "Buy" in action:
        if high_vol:
            entry_strategy = "Dollar-cost average in over 4–6 weeks — volatility is elevated"
            warnings.append("VIX or beta suggests above-average swings; avoid going all-in at once")
        elif hor == "short":
            entry_strategy = "Enter near current levels with a tight stop-loss (5–8% below entry)"
        elif hor == "long":
            entry_strategy = "Lump sum is fine for long-term holds; or split into 2 tranches a month apart"
        else:
            entry_strategy = "Enter in 2 tranches over 2–4 weeks to smooth timing risk"
    elif action.startswith("Hold"):
        entry_strategy = "Set an alert — revisit if the score moves above " + str(buy_threshold)
    else:
        entry_strategy = "No entry — wait for a fundamental improvement or a meaningful price reset"

    # ── Dimension-specific reasoning ─────────────────────────────────────
    dims_sorted = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    best_dim, best_score = dims_sorted[0]
    worst_dim, worst_score = dims_sorted[-1]

    reasoning_points.append(
        f"Strongest: {best_dim} ({best_score:.0f}/100) — {reasons.get(best_dim, '')}"
    )
    reasoning_points.append(
        f"Weakest: {worst_dim} ({worst_score:.0f}/100) — {reasons.get(worst_dim, '')}"
    )

    # Goal-specific commentary
    if goal == "income":
        if dividend_yield and dividend_yield > 0.02:
            reasoning_points.append(
                f"Dividend yield of {dividend_yield*100:.1f}% aligns with your income goal"
            )
        elif dividend_yield and dividend_yield > 0:
            warnings.append(
                f"Dividend yield is only {dividend_yield*100:.2f}% — may not meet income needs"
            )
        else:
            warnings.append("No dividend — doesn't fit an income-focused strategy")
    elif goal == "growth":
        eg = info.get("earningsGrowth")
        rg = info.get("revenueGrowth")
        if eg and eg > 0.10:
            reasoning_points.append(f"Earnings growth of {eg*100:.0f}% supports your growth goal")
        elif rg and rg > 0.10:
            reasoning_points.append(f"Revenue growth of {rg*100:.0f}% supports your growth goal")
        else:
            warnings.append("Growth metrics are modest — may not deliver the upside a growth investor wants")

    # Macro warnings
    if tnx and tnx > 4.5 and sector == "Technology":
        warnings.append(f"Treasury yields at {tnx:.1f}% pressure tech valuations — be prepared for multiple compression")
    if vix and vix > 25:
        warnings.append(f"VIX at {vix:.0f} signals elevated fear — expect wider price swings")

    # Earnings proximity warning
    from datetime import datetime
    raw_earnings = info.get("earningsTimestamp") or info.get("earningsDate")
    earnings_dt = None
    if isinstance(raw_earnings, (int, float)) and raw_earnings > 0:
        try:
            earnings_dt = datetime.fromtimestamp(raw_earnings)
        except Exception:
            pass
    elif isinstance(raw_earnings, list) and raw_earnings:
        try:
            earnings_dt = datetime.fromtimestamp(raw_earnings[0])
        except Exception:
            pass
    if earnings_dt:
        days_until = (earnings_dt - datetime.now()).days
        if 0 <= days_until <= 14:
            warnings.append(
                f"Earnings in {days_until} days — the signal could shift significantly. "
                f"Consider waiting until after the report if you're a {rt} investor"
            )

    # ── Confidence level ─────────────────────────────────────────────────
    confidence_score = 0
    if n_analysts >= 15:
        confidence_score += 2
    elif n_analysts >= 5:
        confidence_score += 1
    # How many signal dimensions have data?
    dims_with_data = sum(1 for v in breakdown.values() if v != 50.0)
    if dims_with_data >= 5:
        confidence_score += 2
    elif dims_with_data >= 3:
        confidence_score += 1
    # Clear signal (not borderline)
    if abs(score - buy_threshold) > 10:
        confidence_score += 1

    if confidence_score >= 4:
        confidence = "High"
    elif confidence_score >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"
        warnings.append("Limited data coverage — treat this recommendation with extra caution")

    # ── Portfolio-aware check ────────────────────────────────────────────
    portfolio_note = None
    if portfolio_holdings and portfolio_info and "Buy" in action:
        # Check sector concentration
        sector_counts: dict[str, int] = {}
        for t in portfolio_holdings:
            t_info = portfolio_info.get(t, {})
            t_sector = t_info.get("sector", "Unknown")
            sector_counts[t_sector] = sector_counts.get(t_sector, 0) + 1
        total = len(portfolio_holdings)
        same_sector_count = sector_counts.get(sector, 0)
        same_sector_pct = same_sector_count / total * 100 if total > 0 else 0

        ticker_sym = info.get("symbol", "")
        if ticker_sym.upper() in [t.upper() for t in portfolio_holdings]:
            portfolio_note = (
                f"You already hold {ticker_sym}. Consider whether adding more "
                f"increases concentration risk before sizing up."
            )
        elif same_sector_pct >= 30:
            friendly = SECTOR_GROUPS.get(sector, sector)
            portfolio_note = (
                f"You already have {same_sector_count} of {total} holdings in {friendly} "
                f"({same_sector_pct:.0f}%). Adding another {friendly} stock increases sector "
                f"concentration — consider diversifying into a different sector."
            )
        elif same_sector_pct >= 20:
            friendly = SECTOR_GROUPS.get(sector, sector)
            portfolio_note = (
                f"{friendly} already makes up {same_sector_pct:.0f}% of your holdings. "
                f"This is manageable, but keep an eye on sector concentration."
            )

    return {
        "action": action,
        "sizing": sizing,
        "entry_strategy": entry_strategy,
        "reasoning": reasoning_points,
        "warnings": warnings,
        "confidence": confidence,
        "portfolio_note": portfolio_note,
    }
