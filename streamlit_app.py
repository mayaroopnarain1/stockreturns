# -*- coding: utf-8 -*-
"""
StockLens — Home
Screen, analyze, and compare stocks. Built for MBA-level investors.
"""

import streamlit as st

st.set_page_config(page_title="StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/query_stats: StockLens")
st.caption("Screen, analyze, and compare stocks — all in one place.")

st.markdown("---")

# Quick-start: popular tickers
st.subheader("Quick Start")
_popular = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "UNH", "V"]
_qs_cols = st.columns(len(_popular))
for i, _t in enumerate(_popular):
    if _qs_cols[i].button(_t, key=f"qs_{_t}", use_container_width=True):
        st.session_state["recent_tickers"] = [_t] + st.session_state.get("recent_tickers", [])[:9]
        st.switch_page("pages/1_Stock_Analysis.py")

# Recently analyzed (show if any)
_recent = st.session_state.get("recent_tickers", [])
if _recent:
    st.caption(f"Recently analyzed: {', '.join(_recent[:5])}")
    _rc_cols = st.columns(min(len(_recent), 5))
    for i, _t in enumerate(_recent[:5]):
        if _rc_cols[i].button(f"↩ {_t}", key=f"rc_{_t}", use_container_width=True):
            # Move this ticker to front so Stock Analysis loads it
            st.session_state["recent_tickers"] = [_t] + [x for x in _recent if x != _t][:9]
            st.switch_page("pages/1_Stock_Analysis.py")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader(":material/search: Stock Analysis")
    st.write(
        "Enter any ticker and get a **prescriptive recommendation** — not just "
        "Buy/Hold/Sell, but specific position sizing, entry strategy, and risk "
        "warnings tailored to **your investor profile** (risk tolerance, goal, "
        "time horizon). Backed by a 5-dimension composite score with macro context, "
        "full fundamentals, benchmark comparison, and portfolio-aware insights."
    )

    st.subheader(":material/filter_list: Stock Screener")
    st.write(
        "Scan the S&P 500 for undervalued, high-quality stocks using intuitive "
        "dropdown filters (P/E, EV/EBITDA, ROE, margins) with quick-pick presets "
        "like Value Plays, Quality Growth, and Dividend Income."
    )

with col2:
    st.subheader(":material/compare_arrows: Compare Stocks")
    st.write(
        "Pick 2–5 tickers and compare them side by side — normalized performance, "
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
