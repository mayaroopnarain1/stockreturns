# -*- coding: utf-8 -*-
"""
Page 3 — Returns & Volatility
Deep-dive into a single stock's return profile with benchmark comparison.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from datetime import date, timedelta
from utils.data import get_price_history, get_price_history_dates
from utils.metrics import compute_return_metrics, compute_benchmark_metrics, monthly_returns_table, metric_card

st.set_page_config(page_title="Returns & Volatility — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title(":material/bar_chart: Returns & Volatility")
st.caption("Deep-dive into a single stock's daily returns, risk metrics, and benchmark comparison.")

with st.sidebar:
    ticker = st.text_input("Stock ticker", value="AAPL").upper()
    benchmark = st.selectbox("Benchmark", ["SPY", "QQQ", "None"], index=0)
    horizon_map = {
        "1 Month": "1mo", "3 Months": "3mo", "6 Months": "6mo",
        "1 Year": "1y", "2 Years": "2y", "5 Years": "5y", "10 Years": "10y",
        "Custom range": "custom",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=3)
    use_custom = horizon_map[horizon] == "custom"
    custom_start = custom_end = None
    if use_custom:
        custom_start = st.date_input("Start date", value=date.today() - timedelta(days=365))
        custom_end = st.date_input("End date", value=date.today())
        if custom_start >= custom_end:
            st.error("Start must be before end.")
            st.stop()
    with st.expander("Settings"):
        rf = st.number_input("Risk-free rate", 0.0, 0.20, 0.05, 0.01, format="%.2f")
        roll_win = st.selectbox("Rolling vol window (days)", [21, 30, 60], index=1)

if not ticker:
    st.info("Enter a ticker.")
    st.stop()

def _load(sym):
    if use_custom:
        return get_price_history_dates(sym, str(custom_start), str(custom_end))
    return get_price_history(sym, horizon_map[horizon])

data = _load(ticker)
if data.empty:
    st.error(f"No data for **{ticker}**.")
    st.stop()

metrics = compute_return_metrics(data["Close"], rf)
returns = metrics["daily_ret_pct"]

bench_m = bench_comp = None
bench_data = pd.DataFrame()
if benchmark != "None":
    bench_data = _load(benchmark)
    if not bench_data.empty:
        bench_m = compute_return_metrics(bench_data["Close"], rf)
        bench_comp = compute_benchmark_metrics(metrics["daily_ret"], bench_m["daily_ret"], rf)

tab_sum, tab_ret, tab_dd, tab_dist, tab_month, tab_data = st.tabs(
    ["Summary", "Returns", "Drawdown", "Distribution", "Monthly", "Data"]
)

with tab_sum:
    ps = data.index[0].strftime("%b %d, %Y")
    pe = data.index[-1].strftime("%b %d, %Y")
    st.subheader(f"{ticker} — {ps} to {pe}")

    r1 = st.columns(4)
    metric_card(r1[0], "Total Return", f"{metrics['total_return']:.2f}%", "total_return")
    metric_card(r1[1], "Ann. Return", f"{metrics['ann_return']:.2f}%", "ann_return")
    metric_card(r1[2], "Ann. Volatility", f"{metrics['ann_vol']:.2f}%", "ann_vol")
    metric_card(r1[3], "Sharpe Ratio", f"{metrics['sharpe']:.2f}", "sharpe")

    r2 = st.columns(4)
    metric_card(r2[0], "Sortino Ratio", f"{metrics['sortino']:.2f}", "sortino")
    metric_card(r2[1], "Calmar Ratio", f"{metrics['calmar']:.2f}", "calmar")
    metric_card(r2[2], "Max Drawdown", f"{metrics['max_drawdown']:.2f}%", "max_drawdown")
    metric_card(r2[3], "VaR (95%)", f"{metrics['var_95']:.2f}%", "var_95")

    r3 = st.columns(4)
    metric_card(r3[0], "CVaR (95%)", f"{metrics['cvar_95']:.2f}%", "cvar_95")
    metric_card(r3[1], "Skewness", f"{metrics['skewness']:.2f}", "skewness")
    metric_card(r3[2], "Kurtosis", f"{metrics['kurtosis']:.2f}", "kurtosis")

    if bench_comp:
        st.divider()
        st.subheader(f"vs. {benchmark}")
        b1 = st.columns(3)
        metric_card(b1[0], "Alpha (ann.)", f"{bench_comp['alpha']:.2f}%", "alpha")
        metric_card(b1[1], "Beta", f"{bench_comp['beta']:.2f}", "beta")
        metric_card(b1[2], "R-Squared", f"{bench_comp['r_squared']:.2f}", "r_squared")
        b2 = st.columns(3)
        metric_card(b2[0], "Treynor", f"{bench_comp['treynor']:.2f}", "treynor")
        metric_card(b2[1], "Upside Capture", f"{bench_comp['up_capture']:.1f}%", "up_capture")
        metric_card(b2[2], "Downside Capture", f"{bench_comp['down_capture']:.1f}%", "down_capture")

with tab_ret:
    st.subheader("Daily Returns")
    rdf = returns.reset_index()
    rdf.columns = ["Date", "Daily Return (%)"]
    bar = alt.Chart(rdf).mark_bar().encode(
        x="Date:T", y="Daily Return (%):Q",
        color=alt.condition(alt.datum["Daily Return (%)"] >= 0, alt.value("#2ecc71"), alt.value("#e74c3c")),
        tooltip=["Date:T", alt.Tooltip("Daily Return (%):Q", format=".4f")],
    ).properties(height=350)
    st.altair_chart(bar, width="stretch")

    st.subheader(f"Rolling {roll_win}-Day Volatility")
    rv = returns.rolling(roll_win).std().dropna().reset_index()
    rv.columns = ["Date", "Vol (%)"]
    va = alt.Chart(rv).mark_area(opacity=0.25, color="#3498db").encode(x="Date:T", y="Vol (%):Q").properties(height=250)
    vl = alt.Chart(rv).mark_line(color="#3498db", strokeWidth=1.5).encode(x="Date:T", y="Vol (%):Q")
    if bench_m:
        br = bench_m["daily_ret_pct"].rolling(roll_win).std().dropna().reset_index()
        br.columns = ["Date", "Vol (%)"]
        bl = alt.Chart(br).mark_line(color="#e67e22", strokeWidth=1.5, strokeDash=[6,3]).encode(x="Date:T", y="Vol (%):Q")
        st.altair_chart(va + vl + bl, width="stretch")
        st.caption(f"Blue = {ticker}  ·  Orange = {benchmark}")
    else:
        st.altair_chart(va + vl, width="stretch")

with tab_dd:
    st.subheader("Drawdown Over Time")
    st.caption("How far below the running peak at any point. Deeper = more pain.")
    dd = metrics["drawdown_series"].reset_index()
    dd.columns = ["Date", "Drawdown (%)"]
    dda = alt.Chart(dd).mark_area(opacity=0.4, color="#e74c3c").encode(
        x="Date:T", y="Drawdown (%):Q", tooltip=["Date:T", alt.Tooltip("Drawdown (%):Q", format=".2f")]
    ).properties(height=300)
    ddl = alt.Chart(dd).mark_line(color="#e74c3c", strokeWidth=1).encode(x="Date:T", y="Drawdown (%):Q")
    st.altair_chart(dda + ddl, width="stretch")

with tab_dist:
    st.subheader("Return Distribution")
    rdf = returns.reset_index()
    rdf.columns = ["Date", "Daily Return (%)"]
    avg, std = metrics["avg_daily"], metrics["std_daily"]
    hist = alt.Chart(rdf).mark_bar(opacity=0.75).encode(
        alt.X("Daily Return (%):Q", bin=alt.Bin(maxbins=50)), alt.Y("count()"), tooltip=["count()"]
    ).properties(height=350)
    xr = np.linspace(returns.min(), returns.max(), 200)
    npdf = (1/(std*np.sqrt(2*np.pi)))*np.exp(-0.5*((xr-avg)/std)**2)
    bw = (returns.max()-returns.min())/50
    ndf = pd.DataFrame({"Daily Return (%)": xr, "N": npdf*len(returns)*bw})
    nl = alt.Chart(ndf).mark_line(color="orange", strokeDash=[6,3], strokeWidth=2).encode(x="Daily Return (%):Q", y=alt.Y("N:Q", title="Frequency"))
    mr = alt.Chart(pd.DataFrame({"x":[avg]})).mark_rule(color="red", strokeDash=[4,4], strokeWidth=2).encode(x="x:Q")
    st.altair_chart(hist + nl + mr, width="stretch")
    st.caption("Orange = normal distribution  ·  Red = mean")

with tab_month:
    st.subheader("Monthly Returns Heatmap")
    mt = monthly_returns_table(data["Close"])
    if not mt.empty:
        mt["YTD"] = mt.sum(axis=1).round(2)
        st.dataframe(mt.style.background_gradient(cmap="RdYlGn", axis=None, vmin=-10, vmax=10).format("{:.1f}%", na_rep="—"), width="stretch")
    else:
        st.info("Not enough data.")

with tab_data:
    st.subheader("Raw Data")
    disp = data[["Close"]].copy()
    disp["Daily Return (%)"] = data["Close"].pct_change() * 100
    disp.columns = ["Adj Close", "Daily Return (%)"]
    disp.index = disp.index.strftime("%Y-%m-%d")
    st.dataframe(disp.sort_index(ascending=False), width="stretch")
