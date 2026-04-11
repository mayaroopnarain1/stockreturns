# -*- coding: utf-8 -*-
"""
Page 5 — Portfolio Risk
Enter holdings + weights → portfolio-level risk, diversification, risk contributions.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history_batch
from utils.metrics import compute_return_metrics, metric_card

st.set_page_config(page_title="Portfolio Risk — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title(":material/account_balance_wallet: Portfolio Risk")
st.caption("Enter holdings and weights to get portfolio-level risk metrics and per-stock risk contributions.")

with st.sidebar:
    st.subheader("Holdings")
    st.caption("Weights must sum to 100%.")
    num = st.number_input("Number of holdings", min_value=2, max_value=10, value=3, step=1)
    deft = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","JPM","V","JNJ"]
    defw = [40,35,25,0,0,0,0,0,0,0]
    tickers, weights = [], []
    for i in range(int(num)):
        c1, c2 = st.columns([2,1])
        t = c1.text_input(f"Ticker {i+1}", deft[i] if i < len(deft) else "", key=f"t{i}").upper()
        w = c2.number_input(f"Wt %", min_value=0, max_value=100, value=defw[i] if i < len(defw) else 0, key=f"w{i}")
        if t: tickers.append(t); weights.append(w)
    total_w = sum(weights)
    if total_w != 100:
        st.warning(f"Weights sum to {total_w}%.")
    horizon_map = {"3M": "3mo", "6M": "6mo", "1Y": "1y", "2Y": "2y", "5Y": "5y"}
    horizon = st.pills("Time horizon", list(horizon_map.keys()), default="1Y")
    if not horizon:
        horizon = "1Y"
    rf = st.number_input("Risk-free rate", 0.0, 0.20, 0.05, 0.01, format="%.2f")
    st.caption("Default 5% approximates the current short-term Treasury yield.")

if total_w != 100 or len(tickers) < 2:
    if total_w != 100:
        st.warning(f"Weights sum to **{total_w}%** — adjust in the sidebar so they total 100%.")
    else:
        st.info("Add at least 2 holdings in the sidebar.")
    st.stop()

w_arr = np.array(weights) / 100
with st.spinner("Fetching…"):
    pdf = get_price_history_batch(tickers, horizon_map[horizon])
if pdf.empty:
    st.error("Could not fetch data. Try again.")
    st.stop()
errs = [t for t in tickers if t not in pdf.columns or pdf[t].isna().all()]
if errs:
    st.error(f"No data for: {', '.join(errs)}")
    st.stop()

pdf = pdf[tickers].dropna()
if len(pdf) < 20:
    st.error("Not enough overlapping data.")
    st.stop()

ret_df = pdf.pct_change().dropna()
port_ret = (ret_df * w_arr).sum(axis=1)
port_cum = (1 + port_ret).cumprod()
indiv_cum = (1 + ret_df).cumprod()
cov_ann = ret_df.cov() * 252
port_var = w_arr @ cov_ann.values @ w_arr
port_vol = np.sqrt(port_var) * 100
indiv_vols = ret_df.std() * np.sqrt(252)
undiv_vol = (w_arr * indiv_vols.values).sum() * 100
div_benefit = undiv_vol - port_vol

port_prices = port_cum
port_m = compute_return_metrics(port_prices, rf)
mctr = (cov_ann.values @ w_arr) / np.sqrt(port_var)
ctr = w_arr * mctr
ctr_pct = ctr / ctr.sum() * 100

tab_ov, tab_cont, tab_hold = st.tabs(["Overview", "Risk Contributions", "Holdings"])

with tab_ov:
    st.subheader("Portfolio Summary")
    r1 = st.columns(4)
    metric_card(r1[0], "Portfolio Return", f"{port_m['total_return']:.2f}%", "total_return")
    metric_card(r1[1], "Portfolio Vol", f"{port_vol:.2f}%", "ann_vol")
    metric_card(r1[2], "Sharpe", f"{port_m['sharpe']:.2f}", "sharpe")
    metric_card(r1[3], "Max Drawdown", f"{port_m['max_drawdown']:.2f}%", "max_drawdown")

    r2 = st.columns(4)
    r2[0].metric("Undiversified Vol", f"{undiv_vol:.2f}%")
    r2[0].caption("What you'd get if all stocks moved in perfect sync.")
    r2[1].metric("Diversification Benefit", f"{div_benefit:.2f}%")
    r2[1].caption("Volatility saved by holding stocks that don't move together.")
    metric_card(r2[2], "Sortino", f"{port_m['sortino']:.2f}", "sortino")
    metric_card(r2[3], "VaR (95%)", f"{port_m['var_95']:.2f}%", "var_95")

    st.divider()
    st.subheader("Cumulative Performance")
    cum = indiv_cum.copy()
    cum["Portfolio"] = port_cum
    plot = cum.reset_index().melt(id_vars="Date", var_name="Holding", value_name="Cumulative")
    ch = alt.Chart(plot).mark_line().encode(
        x="Date:T", y=alt.Y("Cumulative:Q").scale(zero=False), color="Holding:N",
        strokeDash=alt.condition(alt.datum.Holding == "Portfolio", alt.value([1,0]), alt.value([6,3])),
        tooltip=["Date:T","Holding:N",alt.Tooltip("Cumulative:Q",format=".4f")]
    ).properties(height=400)
    st.altair_chart(ch, width="stretch")

with tab_cont:
    st.subheader("Risk Contribution by Holding")
    st.caption("A stock can contribute more risk than its weight if it's volatile or correlated with the rest.")
    cdf = pd.DataFrame({
        "Ticker": tickers, "Weight (%)": [w*100 for w in w_arr],
        "Ann. Vol (%)": [indiv_vols[t]*100 for t in tickers],
        "Risk Contribution (%)": ctr_pct,
    }).set_index("Ticker").round(2)
    st.dataframe(cdf, width="stretch")

    bd = cdf[["Weight (%)","Risk Contribution (%)"]].reset_index().melt(id_vars="Ticker", var_name="Measure", value_name="Pct")
    bc = alt.Chart(bd).mark_bar().encode(
        x="Ticker:N", y="Pct:Q", color="Measure:N", xOffset="Measure:N",
        tooltip=["Ticker:N","Measure:N",alt.Tooltip("Pct:Q",format=".1f")]
    ).properties(height=350)
    st.altair_chart(bc, width="stretch")
    st.caption("If risk contribution > weight, that stock is a disproportionate risk source.")

    st.divider()
    st.subheader("Correlation Matrix")
    corr = ret_df.corr().round(3)
    st.dataframe(corr.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1), width="stretch")

with tab_hold:
    st.subheader("Individual Metrics")
    rows = {}
    for t in tickers:
        m = compute_return_metrics(pdf[t], rf)
        rows[t] = {
            "Weight (%)": round(w_arr[tickers.index(t)]*100,1),
            "Total Return (%)": round(m["total_return"],2), "Ann. Vol (%)": round(m["ann_vol"],2),
            "Sharpe": round(m["sharpe"],2), "Sortino": round(m["sortino"],2),
            "Max DD (%)": round(m["max_drawdown"],2),
        }
    st.dataframe(pd.DataFrame(rows), width="stretch")
