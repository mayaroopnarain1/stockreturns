# -*- coding: utf-8 -*-
"""
StockLens — Home
Screen, analyse, and compare stocks. Built for MBA-level investors.
"""

import streamlit as st

st.set_page_config(page_title="StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/query_stats: StockLens")
st.caption("Screen, analyse, and compare stocks — all in one place.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader(":material/search: Stock Analysis")
    st.write(
        "Enter any ticker and get a **Buy / Hold / Sell** signal backed by a "
        "composite score across valuation, quality, momentum, and risk. Full "
        "fundamentals, benchmark comparison, drawdown chart, and monthly heatmap included."
    )

    st.subheader(":material/filter_list: Stock Screener")
    st.write(
        "Scan the S&P 500 for undervalued, high-quality stocks using fundamental "
        "filters (P/E, P/B, EV/EBITDA, ROE, margins) and rank by a composite value score."
    )

    st.subheader(":material/bar_chart: Returns & Volatility")
    st.write(
        "Deep-dive into daily returns, rolling volatility, Sharpe/Sortino/Calmar ratios, "
        "Alpha, Beta, upside/downside capture, CVaR, drawdown chart, and monthly heatmap."
    )

with col2:
    st.subheader(":material/compare_arrows: Compare Stocks")
    st.write(
        "Pick 2–5 tickers and compare them side by side — normalised performance, "
        "risk metrics, fundamentals, risk-return scatter, and correlation matrix."
    )

    st.subheader(":material/account_balance_wallet: Portfolio Risk")
    st.write(
        "Enter holdings and weights to get portfolio-level metrics: weighted return, "
        "portfolio volatility, Sharpe, diversification benefit, and per-stock risk contributions."
    )

st.markdown("---")

st.info(
    "**Data source:** All data pulled live from Yahoo Finance via yfinance. "
    "Fundamental data cached 12 hours; price data cached 6 hours. No API key required.",
    icon=":material/info:",
)

st.markdown("---")

st.markdown(
    "**Disclaimer:** StockLens provides quantitative signals and analytics for "
    "educational and informational purposes only. It is not financial advice. "
    "Always do your own research and consult a qualified financial advisor "
    "before making investment decisions."
)
