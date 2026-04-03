# -*- coding: utf-8 -*-
"""
StockLens — Home page
A multi-page Streamlit app for stock screening, risk/return analysis,
and portfolio assessment. Built for MBA students and finance professionals.
"""

import streamlit as st

st.set_page_config(
    page_title="StockLens",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

st.title(":material/query_stats: StockLens")
st.caption("Screen, analyse, and compare stocks — all in one place.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader(":material/search: Stock Screener")
    st.write(
        "Scan the S&P 500 for undervalued stocks using fundamental filters "
        "like P/E, P/B, EV/EBITDA, ROE, and more. Rank by a composite value "
        "score that combines cheapness with quality."
    )

    st.subheader(":material/bar_chart: Returns & Volatility")
    st.write(
        "Deep-dive into a single stock's return profile. See daily returns, "
        "rolling volatility, Sharpe and Sortino ratios, max drawdown, VaR, "
        "and compare against a benchmark like SPY or QQQ."
    )

with col2:
    st.subheader(":material/compare_arrows: Compare Stocks")
    st.write(
        "Pick 2–5 tickers and compare them side by side — returns, risk "
        "metrics, fundamentals, and correlation. See who's outperforming "
        "and how diversified your picks are."
    )

    st.subheader(":material/account_balance_wallet: Portfolio Risk")
    st.write(
        "Enter your holdings and weights to get portfolio-level metrics: "
        "weighted return, portfolio volatility, diversification benefit, "
        "and individual stock contributions to total risk."
    )

st.markdown("---")

st.info(
    "**Data source:** All market data is pulled live from Yahoo Finance via yfinance. "
    "Fundamental data is cached for up to 12 hours; price data for up to 6 hours. "
    "No API key required.",
    icon=":material/info:",
)

st.caption(
    "Use the sidebar to navigate between pages. "
    "Built with Streamlit · Data from Yahoo Finance"
)
