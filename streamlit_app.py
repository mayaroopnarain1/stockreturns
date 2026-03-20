# -*- coding: utf-8 -*-
"""
Stock Daily Returns Analysis
Assess risk and volatility through daily percentage returns,
average return, and standard deviation.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Stock Returns & Volatility",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

st.title(":material/query_stats: Stock Returns & Volatility")
st.caption("Assess risk and volatility through daily percentage returns.")

# --- Sidebar inputs ---
with st.sidebar:
    ticker = st.text_input("Stock ticker", value="AAPL").upper()

    horizon_map = {
        "1 Month": "1mo",
        "3 Months": "3mo",
        "6 Months": "6mo",
        "1 Year": "1y",
        "2 Years": "2y",
        "5 Years": "5y",
    }
    horizon = st.selectbox("Time horizon", options=list(horizon_map.keys()), index=3)

if not ticker:
    st.info("Enter a stock ticker to get started.")
    st.stop()


# --- Load data ---
@st.cache_data(show_spinner="Fetching data…", ttl="6h")
def load_data(ticker: str, period: str) -> pd.DataFrame:
    data = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if data is None or data.empty:
        return pd.DataFrame()
    return data


data = load_data(ticker, horizon_map[horizon])

if data.empty:
    st.error(f"No data found for **{ticker}**. Check the ticker symbol and try again.")
    st.stop()


# --- Calculate daily % returns ---
# With auto_adjust=True the "Close" column is already the adjusted close.
data["Daily Return (%)"] = data["Close"].pct_change() * 100
returns = data["Daily Return (%)"].dropna()

avg_return = returns.mean()
std_return = returns.std()
total_days = len(returns)

# --- Summary metrics ---
st.subheader(f"{ticker} — Summary")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Trading Days", total_days)
col2.metric("Avg Daily Return", f"{avg_return:.4f}%")
col3.metric("Std Deviation", f"{std_return:.4f}%")
col4.metric(
    "Annualised Volatility",
    f"{std_return * (252 ** 0.5):.2f}%",
    help="Daily std × √252 (trading days per year)",
)

st.divider()

# --- Daily returns chart ---
st.subheader("Daily Returns Over Time")

returns_df = returns.reset_index()
returns_df.columns = ["Date", "Daily Return (%)"]

bar_chart = (
    alt.Chart(returns_df)
    .mark_bar()
    .encode(
        x=alt.X("Date:T"),
        y=alt.Y("Daily Return (%):Q"),
        color=alt.condition(
            alt.datum["Daily Return (%)"] >= 0,
            alt.value("#2ecc71"),  # green for positive
            alt.value("#e74c3c"),  # red for negative
        ),
        tooltip=["Date:T", alt.Tooltip("Daily Return (%):Q", format=".4f")],
    )
    .properties(height=350)
)

st.altair_chart(bar_chart, use_container_width=True)

# --- Histogram of returns ---
st.subheader("Return Distribution")

hist_chart = (
    alt.Chart(returns_df)
    .mark_bar(opacity=0.75)
    .encode(
        alt.X("Daily Return (%):Q", bin=alt.Bin(maxbins=50), title="Daily Return (%)"),
        alt.Y("count()", title="Frequency"),
        tooltip=["count()"],
    )
    .properties(height=300)
)

mean_rule = (
    alt.Chart(pd.DataFrame({"x": [avg_return]}))
    .mark_rule(color="red", strokeDash=[4, 4], strokeWidth=2)
    .encode(x="x:Q")
)

st.altair_chart(hist_chart + mean_rule, use_container_width=True)
st.caption("Red dashed line = mean daily return")

# --- Raw data table ---
st.subheader("Raw Data")
display_df = data[["Close", "Daily Return (%)"]].copy()
display_df.columns = ["Adj Close", "Daily Return (%)"]
st.dataframe(display_df.sort_index(ascending=False), use_container_width=True)
