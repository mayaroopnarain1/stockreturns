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


# ---------------------------------------------------------------------------
# Technical indicators — pure functions on a price series
# ---------------------------------------------------------------------------

def rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """Classic Wilder-style RSI (14). Returns a Series aligned to `prices`."""
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(window=window, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram)."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(prices: pd.Series, window: int = 20, num_std: float = 2.0):
    """Return (upper, mid, lower) Bollinger Band series."""
    mid = prices.rolling(window=window).mean()
    std = prices.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def moving_averages(prices: pd.Series, windows: tuple[int, ...] = (20, 50, 200)) -> dict:
    """Return a dict of {window: moving_average_series}."""
    return {w: prices.rolling(window=w).mean() for w in windows}


def detect_outlier_days(returns: pd.Series, z_threshold: float = 3.0) -> pd.Series:
    """Return the subset of `returns` where |z-score| > threshold.

    `returns` should be a daily-return series (fractional or percentage — the
    function normalises internally).
    """
    if returns.empty:
        return returns
    mu = returns.mean()
    sigma = returns.std()
    if sigma == 0 or np.isnan(sigma):
        return returns.iloc[0:0]
    z = (returns - mu) / sigma
    return returns[z.abs() > z_threshold]


MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def monthly_seasonality(prices: pd.Series, lookback_years: int = 10) -> dict:
    """Compute calendar-month return statistics from a daily Close series.

    Resamples to month-end prices, takes monthly returns, then groups by
    month-of-year. Returns ``{"stats": DataFrame, "n_years": int, "start":
    Timestamp|None, "end": Timestamp|None}`` where ``stats`` is indexed by
    month number 1..12 with columns ``["mean", "median", "hit_rate", "best",
    "worst", "n"]``. ``hit_rate`` is the share of observations with positive
    return. Returns an empty stats DataFrame if fewer than 12 monthly
    observations are available.
    """
    empty = {
        "stats": pd.DataFrame(
            columns=["mean", "median", "hit_rate", "best", "worst", "n"],
            index=pd.Index(range(1, 13), name="month"),
        ),
        "n_years": 0,
        "start": None,
        "end": None,
    }
    if prices is None or len(prices) == 0:
        return empty

    s = prices.copy()
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)

    # Trim to the requested window (based on the most recent observation).
    if lookback_years and lookback_years > 0:
        cutoff = s.index.max() - pd.DateOffset(years=lookback_years)
        s = s[s.index >= cutoff]

    if len(s) < 2:
        return empty

    monthly = s.resample("ME").last().pct_change().dropna()
    if len(monthly) < 12:
        return empty

    grouped = monthly.groupby(monthly.index.month)
    stats = pd.DataFrame({
        "mean":     grouped.mean(),
        "median":   grouped.median(),
        "hit_rate": grouped.apply(lambda x: float((x > 0).mean())),
        "best":     grouped.max(),
        "worst":    grouped.min(),
        "n":        grouped.size().astype(int),
    })
    stats = stats.reindex(range(1, 13))
    stats.index.name = "month"

    return {
        "stats": stats,
        "n_years": int(len(monthly) // 12),
        "start": monthly.index.min(),
        "end": monthly.index.max(),
    }



def compute_technical_signals(prices: pd.Series) -> dict:
    """Compute a summary read of technical signals for a price series.

    Returns a dict with:
      - direction: "Bullish" | "Bearish" | "Neutral" | "Insufficient data"
      - strength: 0-100
      - signals: list of (name, direction, interpretation) tuples
      - indicator values: rsi, macd, macd_signal, ma20/50/200, bb_upper/lower/mid,
        bb_position (0 = at lower band, 1 = at upper band), current_price
    """
    if len(prices) < 50:
        return {
            "direction": "Insufficient data",
            "strength": 0,
            "signals": [],
            "current_price": float(prices.iloc[-1]) if len(prices) else None,
        }

    current_price = float(prices.iloc[-1])
    mas = moving_averages(prices, windows=(20, 50, 200))
    ma20 = float(mas[20].iloc[-1]) if not np.isnan(mas[20].iloc[-1]) else None
    ma50 = float(mas[50].iloc[-1]) if not np.isnan(mas[50].iloc[-1]) else None
    ma200 = float(mas[200].iloc[-1]) if len(prices) >= 200 and not np.isnan(mas[200].iloc[-1]) else None

    rsi_series = rsi(prices)
    rsi_val = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else None

    macd_line, signal_line, hist = macd(prices)
    macd_current = float(macd_line.iloc[-1])
    signal_current = float(signal_line.iloc[-1])

    upper_bb, mid_bb, lower_bb = bollinger_bands(prices)
    bb_position = None
    if not np.isnan(upper_bb.iloc[-1]) and not np.isnan(lower_bb.iloc[-1]):
        width = upper_bb.iloc[-1] - lower_bb.iloc[-1]
        if width > 0:
            bb_position = float((current_price - lower_bb.iloc[-1]) / width)

    signals: list[tuple[str, str, str]] = []
    bullish = 0.0
    bearish = 0.0

    # --- Trend (MA alignment) ---
    if ma50 is not None and ma200 is not None:
        if current_price > ma50 > ma200:
            signals.append(("Trend", "Bullish",
                            f"Price ${current_price:.2f} above MA50 (${ma50:.2f}) and MA200 (${ma200:.2f}) — uptrend."))
            bullish += 2
        elif current_price < ma50 < ma200:
            signals.append(("Trend", "Bearish",
                            f"Price below MA50 (${ma50:.2f}) and MA200 (${ma200:.2f}) — downtrend."))
            bearish += 2
        else:
            signals.append(("Trend", "Neutral",
                            "MAs not aligned — trend is unclear; wait for confirmation."))

    # --- Golden / Death cross (5-day lookback) ---
    if len(prices) >= 205:
        ma50_prev = mas[50].iloc[-5]
        ma200_prev = mas[200].iloc[-5]
        if not np.isnan(ma50_prev) and not np.isnan(ma200_prev):
            if ma50 > ma200 and ma50_prev <= ma200_prev:
                signals.append(("MA Cross", "Bullish",
                                "Golden cross detected — MA50 just crossed above MA200."))
                bullish += 1.5
            elif ma50 < ma200 and ma50_prev >= ma200_prev:
                signals.append(("MA Cross", "Bearish",
                                "Death cross detected — MA50 just crossed below MA200."))
                bearish += 1.5

    # --- RSI ---
    if rsi_val is not None:
        if rsi_val > 70:
            signals.append(("RSI", "Bearish",
                            f"RSI {rsi_val:.1f} — overbought; pullback risk elevated."))
            bearish += 1
        elif rsi_val < 30:
            signals.append(("RSI", "Bullish",
                            f"RSI {rsi_val:.1f} — oversold; potential bounce."))
            bullish += 1
        else:
            signals.append(("RSI", "Neutral",
                            f"RSI {rsi_val:.1f} — neutral zone (30-70)."))

    # --- MACD ---
    if macd_current > signal_current:
        signals.append(("MACD", "Bullish",
                        f"MACD above signal line — positive momentum."))
        bullish += 1
    else:
        signals.append(("MACD", "Bearish",
                        f"MACD below signal line — negative momentum."))
        bearish += 1

    # --- Bollinger position ---
    if bb_position is not None:
        if bb_position > 0.95:
            signals.append(("Bollinger", "Bearish",
                            "At or above upper band — extended, mean reversion likely."))
            bearish += 0.5
        elif bb_position < 0.05:
            signals.append(("Bollinger", "Bullish",
                            "At or below lower band — compressed, bounce possible."))
            bullish += 0.5
        else:
            signals.append(("Bollinger", "Neutral",
                            f"Within bands (position {bb_position*100:.0f}% of range)."))

    total = bullish + bearish
    if total == 0:
        direction = "Neutral"
        strength = 50
    elif bullish > bearish * 1.3:
        direction = "Bullish"
        strength = min(100, bullish / total * 100)
    elif bearish > bullish * 1.3:
        direction = "Bearish"
        strength = min(100, bearish / total * 100)
    else:
        direction = "Neutral"
        strength = 50

    return {
        "direction": direction,
        "strength": strength,
        "signals": signals,
        "rsi": rsi_val,
        "macd": macd_current,
        "macd_signal": signal_current,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "bb_upper": float(upper_bb.iloc[-1]) if not np.isnan(upper_bb.iloc[-1]) else None,
        "bb_lower": float(lower_bb.iloc[-1]) if not np.isnan(lower_bb.iloc[-1]) else None,
        "bb_mid": float(mid_bb.iloc[-1]) if not np.isnan(mid_bb.iloc[-1]) else None,
        "bb_position": bb_position,
        "current_price": current_price,
    }


# Technical-indicator descriptions for tooltips / help text
TECHNICAL_DESC: dict[str, str] = {
    "rsi": "Relative Strength Index (14-day). >70 suggests overbought; <30 oversold. Best used with trend context.",
    "macd": "Moving Average Convergence Divergence. MACD above its signal line = positive momentum; below = negative.",
    "bollinger": "Bands at mean ± 2σ over 20 days. Price near upper band is stretched; near lower band is compressed.",
    "ma20": "20-day moving average — short-term trend.",
    "ma50": "50-day moving average — intermediate trend. A common 'buy the dip' level.",
    "ma200": "200-day moving average — long-term trend. Price above MA200 is widely considered bullish.",
    "golden_cross": "MA50 crossing above MA200 — classic bullish signal.",
    "death_cross": "MA50 crossing below MA200 — classic bearish signal.",
}
