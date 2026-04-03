# -*- coding: utf-8 -*-
"""
Page 4 — Compare Stocks
Side-by-side 2–5 ticker comparison: performance, risk, fundamentals, correlation.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history, get_ticker_info
from utils.metrics import compute_return_metrics, METRIC_DESC, FUNDAMENTAL_DESC

st.set_page_config(page_title="Compare Stocks — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title(":material/compare_arrows: Compare Stocks")
st.caption("Pick 2–5 tickers and compare returns, risk, fundamentals, and correlation.")

with st.sidebar:
    raw = st.text_input("Tickers (comma-separated)", "AAPL, MSFT, GOOGL")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    if len(tickers) < 2:
        st.warning("Enter at least 2 tickers.")
        st.stop()
    if len(tickers) > 5:
        tickers = tickers[:5]
        st.info("Using first 5 tickers.")
    horizon_map = {"3 Months":"3mo","6 Months":"6mo","1 Year":"1y","2 Years":"2y","5 Years":"5y"}
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=2)
    rf = st.number_input("Risk-free rate", 0.0, 0.20, 0.05, 0.01, format="%.2f")

prices, mets, infos, errors = {}, {}, {}, []
with st.spinner("Fetching…"):
    for t in tickers:
        h = get_price_history(t, horizon_map[horizon])
        if h.empty:
            errors.append(t)
            continue
        prices[t] = h["Close"]
        mets[t] = compute_return_metrics(h["Close"], rf)
        infos[t] = get_ticker_info(t)

if errors:
    st.warning(f"No data for: {', '.join(errors)}")
valid = [t for t in tickers if t in mets]
if len(valid) < 2:
    st.error("Need 2+ valid tickers.")
    st.stop()

tab_perf, tab_risk, tab_fund, tab_corr = st.tabs(["Performance", "Risk Metrics", "Fundamentals", "Correlation"])

with tab_perf:
    st.subheader("Normalised Price (Start = 1.0)")
    st.caption("Compares cumulative performance regardless of share price.")
    pdf = pd.DataFrame(prices)
    norm = pdf.div(pdf.iloc[0])
    plot = norm.reset_index().melt(id_vars="Date", var_name="Ticker", value_name="Norm")
    c = alt.Chart(plot).mark_line().encode(x="Date:T", y=alt.Y("Norm:Q").scale(zero=False), color="Ticker:N",
        tooltip=["Date:T","Ticker:N",alt.Tooltip("Norm:Q",format=".4f")]).properties(height=400)
    st.altair_chart(c, use_container_width=True)

    cols = st.columns(len(valid))
    for i, t in enumerate(valid):
        cols[i].metric(t, f"{mets[t]['total_return']:.2f}%")

with tab_risk:
    st.subheader("Risk & Return Comparison")
    rows = {}
    for t in valid:
        m = mets[t]
        rows[t] = {
            "Total Return (%)": round(m["total_return"],2), "Ann. Vol (%)": round(m["ann_vol"],2),
            "Sharpe": round(m["sharpe"],2), "Sortino": round(m["sortino"],2),
            "Calmar": round(m["calmar"],2), "Max Drawdown (%)": round(m["max_drawdown"],2),
            "VaR 95% (%)": round(m["var_95"],2), "CVaR 95% (%)": round(m["cvar_95"],2),
        }
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    with st.expander("What do these metrics mean?"):
        for k, d in METRIC_DESC.items():
            st.markdown(f"**{k.replace('_',' ').title()}:** {d}")

    st.subheader("Risk vs. Return")
    st.caption("Ideal: upper-left (high return, low vol).")
    sd = pd.DataFrame({"Ticker": valid,
        "Ann. Vol (%)": [mets[t]["ann_vol"] for t in valid],
        "Total Return (%)": [mets[t]["total_return"] for t in valid]})
    sc = alt.Chart(sd).mark_circle(size=120).encode(
        x=alt.X("Ann. Vol (%):Q"), y="Total Return (%):Q", color="Ticker:N",
        tooltip=["Ticker:N","Ann. Vol (%):Q","Total Return (%):Q"]).properties(height=350)
    lb = sc.mark_text(align="left", dx=8).encode(text="Ticker:N")
    st.altair_chart(sc + lb, use_container_width=True)

with tab_fund:
    st.subheader("Key Fundamentals")
    ff = {"shortName":"Company","sector":"Sector","marketCap":"Mkt Cap","trailingPE":"P/E",
        "forwardPE":"Fwd P/E","priceToBook":"P/B","enterpriseToEbitda":"EV/EBITDA",
        "pegRatio":"PEG","dividendYield":"Div Yield","returnOnEquity":"ROE",
        "profitMargins":"Margin","revenueGrowth":"Rev Growth","debtToEquity":"D/E","beta":"Beta"}
    fr = {}
    for t in valid:
        info = infos.get(t, {})
        row = {}
        for k, l in ff.items():
            v = info.get(k)
            if v is None: row[l] = "—"
            elif k == "marketCap": row[l] = f"${v/1e9:.1f}B"
            elif k in ("dividendYield","returnOnEquity","profitMargins","revenueGrowth"): row[l] = f"{v*100:.1f}%"
            elif k == "debtToEquity": row[l] = f"{v:.0f}"
            else: row[l] = f"{v:.2f}" if isinstance(v, float) else str(v)
        fr[t] = row
    st.dataframe(pd.DataFrame(fr), use_container_width=True)

with tab_corr:
    st.subheader("Return Correlation Matrix")
    st.caption("Near 1 = move together; near 0 = independent; negative = move opposite. Lower = better diversification.")
    rdf = pd.DataFrame({t: mets[t]["daily_ret_pct"] for t in valid})
    corr = rdf.corr().round(3)
    st.dataframe(corr.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1), use_container_width=True)
