# -*- coding: utf-8 -*-
"""
Page 2 — Returns & Volatility
Deep-dive into a single stock's return profile with benchmark comparison.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from datetime import date, timedelta
from utils.data import get_price_history, get_price_history_dates
from utils.metrics import compute_return_metrics, METRIC_DESC, metric_card

st.set_page_config(page_title="Returns & Volatility — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/bar_chart: Returns & Volatility")
st.caption("Assess risk and return through daily percentage returns, risk-adjusted metrics, and benchmark comparison.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    ticker = st.text_input("Stock ticker", value="AAPL").upper()
    benchmark = st.selectbox("Benchmark", ["SPY", "QQQ", "None"], index=0)

    horizon_map = {
        "1 Month": "1mo",
        "3 Months": "3mo",
        "6 Months": "6mo",
        "1 Year": "1y",
        "2 Years": "2y",
        "5 Years": "5y",
        "10 Years": "10y",
        "Custom range": "custom",
    }
    horizon = st.selectbox("Time horizon", options=list(horizon_map.keys()), index=3)

    use_custom = horizon_map[horizon] == "custom"
    custom_start = custom_end = None
    if use_custom:
        custom_start = st.date_input("Start date", value=date.today() - timedelta(days=365))
        custom_end = st.date_input("End date", value=date.today())
        if custom_start >= custom_end:
            st.error("Start date must be before end date.")
            st.stop()

    with st.expander("Settings"):
        risk_free_rate = st.number_input(
            "Annual risk-free rate", min_value=0.0, max_value=0.20,
            value=0.05, step=0.01, format="%.2f",
            help="Used for Sharpe and Sortino calculations",
        )
        rolling_window = st.selectbox("Rolling volatility window (days)", [21, 30, 60], index=1)

if not ticker:
    st.info("Enter a stock ticker to get started.")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def _load(symbol: str) -> pd.DataFrame:
    if use_custom:
        return get_price_history_dates(symbol, str(custom_start), str(custom_end))
    return get_price_history(symbol, horizon_map[horizon])

data = _load(ticker)
if data.empty:
    st.error(f"No data found for **{ticker}**. Check the ticker symbol and try again.")
    st.stop()

metrics = compute_return_metrics(data["Close"], risk_free_rate)
returns = metrics["daily_ret_pct"]

bench_metrics = None
if benchmark != "None":
    bench_data = _load(benchmark)
    if not bench_data.empty:
        bench_metrics = compute_return_metrics(bench_data["Close"], risk_free_rate)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_summary, tab_returns, tab_distribution, tab_data = st.tabs(
    ["Summary", "Returns", "Distribution", "Data"]
)

# ========================== SUMMARY =========================================
with tab_summary:
    period_start = data.index[0].strftime("%b %d, %Y")
    period_end = data.index[-1].strftime("%b %d, %Y")
    st.subheader(f"{ticker} — {period_start} to {period_end}")

    r1 = st.columns(4)
    metric_card(r1[0], "Trading Days", str(metrics["trading_days"]), "trading_days")
    metric_card(r1[1], "Total Return", f"{metrics['total_return']:.2f}%", "total_return")
    metric_card(r1[2], "Avg Daily Return", f"{metrics['avg_daily']:.4f}%", "avg_daily")
    metric_card(r1[3], "Std Deviation", f"{metrics['std_daily']:.4f}%", "std_daily")

    r2 = st.columns(4)
    metric_card(r2[0], "Annualised Volatility", f"{metrics['ann_vol']:.2f}%", "ann_vol")
    metric_card(r2[1], "Sharpe Ratio", f"{metrics['sharpe']:.2f}", "sharpe")
    metric_card(r2[2], "Sortino Ratio", f"{metrics['sortino']:.2f}", "sortino")
    metric_card(r2[3], "Max Drawdown", f"{metrics['max_drawdown']:.2f}%", "max_drawdown")

    r3 = st.columns(4)
    metric_card(r3[0], "VaR (95%)", f"{metrics['var_95']:.2f}%", "var_95")
    metric_card(r3[1], "Skewness", f"{metrics['skewness']:.2f}", "skewness")
    metric_card(r3[2], "Kurtosis", f"{metrics['kurtosis']:.2f}", "kurtosis")

    if bench_metrics:
        st.divider()
        st.subheader(f"Benchmark: {benchmark}")

        b1 = st.columns(4)
        metric_card(b1[0], "Trading Days", str(bench_metrics["trading_days"]), "trading_days")
        metric_card(b1[1], "Total Return", f"{bench_metrics['total_return']:.2f}%", "total_return")
        metric_card(b1[2], "Avg Daily Return", f"{bench_metrics['avg_daily']:.4f}%", "avg_daily")
        metric_card(b1[3], "Std Deviation", f"{bench_metrics['std_daily']:.4f}%", "std_daily")

        b2 = st.columns(4)
        metric_card(b2[0], "Annualised Volatility", f"{bench_metrics['ann_vol']:.2f}%", "ann_vol")
        metric_card(b2[1], "Sharpe Ratio", f"{bench_metrics['sharpe']:.2f}", "sharpe")
        metric_card(b2[2], "Sortino Ratio", f"{bench_metrics['sortino']:.2f}", "sortino")
        metric_card(b2[3], "Max Drawdown", f"{bench_metrics['max_drawdown']:.2f}%", "max_drawdown")

        st.divider()
        st.subheader("Side-by-Side")
        comp = pd.DataFrame({
            ticker: {
                "Total Return (%)": f"{metrics['total_return']:.2f}",
                "Avg Daily Return (%)": f"{metrics['avg_daily']:.4f}",
                "Annualised Vol (%)": f"{metrics['ann_vol']:.2f}",
                "Sharpe": f"{metrics['sharpe']:.2f}",
                "Sortino": f"{metrics['sortino']:.2f}",
                "Max Drawdown (%)": f"{metrics['max_drawdown']:.2f}",
                "VaR 95% (%)": f"{metrics['var_95']:.2f}",
            },
            benchmark: {
                "Total Return (%)": f"{bench_metrics['total_return']:.2f}",
                "Avg Daily Return (%)": f"{bench_metrics['avg_daily']:.4f}",
                "Annualised Vol (%)": f"{bench_metrics['ann_vol']:.2f}",
                "Sharpe": f"{bench_metrics['sharpe']:.2f}",
                "Sortino": f"{bench_metrics['sortino']:.2f}",
                "Max Drawdown (%)": f"{bench_metrics['max_drawdown']:.2f}",
                "VaR 95% (%)": f"{bench_metrics['var_95']:.2f}",
            },
        })
        st.dataframe(comp, use_container_width=True)

# ========================== RETURNS =========================================
with tab_returns:
    st.subheader("Daily Returns Over Time")

    ret_df = returns.reset_index()
    ret_df.columns = ["Date", "Daily Return (%)"]

    bar = (
        alt.Chart(ret_df).mark_bar()
        .encode(
            x=alt.X("Date:T"),
            y=alt.Y("Daily Return (%):Q"),
            color=alt.condition(
                alt.datum["Daily Return (%)"] >= 0,
                alt.value("#2ecc71"), alt.value("#e74c3c"),
            ),
            tooltip=["Date:T", alt.Tooltip("Daily Return (%):Q", format=".4f")],
        ).properties(height=350)
    )
    st.altair_chart(bar, use_container_width=True)

    # Rolling vol
    st.subheader(f"Rolling {rolling_window}-Day Volatility")
    st.caption("Spikes indicate periods of heightened uncertainty — earnings surprises, macro shocks, etc.")

    rvol = returns.rolling(window=rolling_window).std().dropna()
    vol_df = rvol.reset_index()
    vol_df.columns = ["Date", "Rolling Std Dev (%)"]

    area = (
        alt.Chart(vol_df).mark_area(opacity=0.25, color="#3498db")
        .encode(x="Date:T", y="Rolling Std Dev (%):Q",
                tooltip=["Date:T", alt.Tooltip("Rolling Std Dev (%):Q", format=".4f")])
        .properties(height=300)
    )
    line = (
        alt.Chart(vol_df).mark_line(color="#3498db", strokeWidth=1.5)
        .encode(x="Date:T", y="Rolling Std Dev (%):Q")
    )

    if bench_metrics:
        br = bench_metrics["daily_ret_pct"].rolling(window=rolling_window).std().dropna().reset_index()
        br.columns = ["Date", "Rolling Std Dev (%)"]
        bline = (
            alt.Chart(br).mark_line(color="#e67e22", strokeWidth=1.5, strokeDash=[6, 3])
            .encode(x="Date:T", y="Rolling Std Dev (%):Q")
        )
        st.altair_chart(area + line + bline, use_container_width=True)
        st.caption(f"Blue = {ticker}  ·  Orange dashed = {benchmark}")
    else:
        st.altair_chart(area + line, use_container_width=True)

# ========================== DISTRIBUTION ====================================
with tab_distribution:
    st.subheader("Return Distribution")
    st.caption("If the bars extend further left than the orange normal curve, the stock has fatter downside tails than theory predicts.")

    ret_df = returns.reset_index()
    ret_df.columns = ["Date", "Daily Return (%)"]
    avg, std = metrics["avg_daily"], metrics["std_daily"]

    hist = (
        alt.Chart(ret_df).mark_bar(opacity=0.75)
        .encode(
            alt.X("Daily Return (%):Q", bin=alt.Bin(maxbins=50)),
            alt.Y("count()", title="Frequency"),
            tooltip=["count()"],
        ).properties(height=350)
    )

    x_rng = np.linspace(returns.min(), returns.max(), 200)
    npdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_rng - avg) / std) ** 2)
    bw = (returns.max() - returns.min()) / 50
    ndf = pd.DataFrame({"Daily Return (%)": x_rng, "Normal": npdf * len(returns) * bw})

    nline = (
        alt.Chart(ndf).mark_line(color="orange", strokeDash=[6, 3], strokeWidth=2)
        .encode(x="Daily Return (%):Q", y=alt.Y("Normal:Q", title="Frequency"))
    )
    mrule = (
        alt.Chart(pd.DataFrame({"x": [avg]}))
        .mark_rule(color="red", strokeDash=[4, 4], strokeWidth=2)
        .encode(x="x:Q")
    )

    st.altair_chart(hist + nline + mrule, use_container_width=True)
    st.caption("Orange dashed = normal distribution  ·  Red dashed = mean return")

    cl, cr = st.columns(2)
    metric_card(cl, "Skewness", f"{metrics['skewness']:.2f}", "skewness")
    metric_card(cr, "Kurtosis", f"{metrics['kurtosis']:.2f}", "kurtosis")

# ========================== DATA ============================================
with tab_data:
    st.subheader("Raw Data")
    disp = data[["Close"]].copy()
    disp["Daily Return (%)"] = data["Close"].pct_change() * 100
    disp.columns = ["Adj Close", "Daily Return (%)"]
    disp.index = disp.index.strftime("%Y-%m-%d")
    st.dataframe(disp.sort_index(ascending=False), use_container_width=True)
