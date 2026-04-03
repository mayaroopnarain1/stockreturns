# -*- coding: utf-8 -*-
"""
Page 3 — Compare Stocks
Side-by-side comparison of 2–5 tickers: returns, risk metrics,
fundamentals, correlation, and normalised price chart.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history, get_ticker_info
from utils.metrics import compute_return_metrics, METRIC_DESC, FUNDAMENTAL_DESC

st.set_page_config(page_title="Compare Stocks — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/compare_arrows: Compare Stocks")
st.caption("Pick 2–5 tickers and compare returns, risk, fundamentals, and correlation side by side.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    tickers_raw = st.text_input(
        "Tickers (comma-separated)",
        value="AAPL, MSFT, GOOGL",
        help="Enter 2–5 ticker symbols separated by commas",
    )
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]

    if len(tickers) < 2:
        st.warning("Enter at least 2 tickers to compare.")
        st.stop()
    if len(tickers) > 5:
        st.warning("Maximum 5 tickers for comparison. Using the first 5.")
        tickers = tickers[:5]

    horizon_map = {
        "1 Month": "1mo", "3 Months": "3mo", "6 Months": "6mo",
        "1 Year": "1y", "2 Years": "2y", "5 Years": "5y",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=3)

    risk_free_rate = st.number_input(
        "Annual risk-free rate", min_value=0.0, max_value=0.20,
        value=0.05, step=0.01, format="%.2f",
    )

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
all_prices = {}
all_metrics = {}
all_info = {}
errors = []

with st.spinner("Fetching data…"):
    for t in tickers:
        hist = get_price_history(t, horizon_map[horizon])
        if hist.empty:
            errors.append(t)
            continue
        all_prices[t] = hist["Close"]
        all_metrics[t] = compute_return_metrics(hist["Close"], risk_free_rate)
        all_info[t] = get_ticker_info(t)

if errors:
    st.warning(f"Could not fetch data for: {', '.join(errors)}")

valid = [t for t in tickers if t in all_metrics]
if len(valid) < 2:
    st.error("Need at least 2 valid tickers. Check symbols and try again.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_perf, tab_risk, tab_fund, tab_corr = st.tabs(
    ["Performance", "Risk Metrics", "Fundamentals", "Correlation"]
)

# ========================== PERFORMANCE =====================================
with tab_perf:
    st.subheader("Normalised Price (Start = 1.0)")
    st.caption("Compares cumulative performance regardless of share price. A stock at 1.2 is up 20% from the start date.")

    price_df = pd.DataFrame(all_prices)
    norm = price_df.div(price_df.iloc[0])
    plot = norm.reset_index().melt(id_vars=["Date"], var_name="Ticker", value_name="Normalised Price")

    chart = (
        alt.Chart(plot).mark_line()
        .encode(
            x="Date:T",
            y=alt.Y("Normalised Price:Q").scale(zero=False),
            color="Ticker:N",
            tooltip=["Date:T", "Ticker:N", alt.Tooltip("Normalised Price:Q", format=".4f")],
        ).properties(height=400)
    )
    st.altair_chart(chart, use_container_width=True)

    # Total return comparison
    st.subheader("Total Return")
    ret_data = {t: f"{all_metrics[t]['total_return']:.2f}%" for t in valid}
    cols = st.columns(len(valid))
    for i, t in enumerate(valid):
        val = all_metrics[t]["total_return"]
        cols[i].metric(t, f"{val:.2f}%")
        cols[i].caption("Cumulative gain/loss over the selected period.")

# ========================== RISK METRICS ====================================
with tab_risk:
    st.subheader("Risk & Return Comparison")

    rows = {}
    for t in valid:
        m = all_metrics[t]
        rows[t] = {
            "Total Return (%)": round(m["total_return"], 2),
            "Avg Daily Return (%)": round(m["avg_daily"], 4),
            "Std Deviation (%)": round(m["std_daily"], 4),
            "Annualised Vol (%)": round(m["ann_vol"], 2),
            "Sharpe Ratio": round(m["sharpe"], 2),
            "Sortino Ratio": round(m["sortino"], 2),
            "Max Drawdown (%)": round(m["max_drawdown"], 2),
            "VaR 95% (%)": round(m["var_95"], 2),
            "Skewness": round(m["skewness"], 2),
            "Kurtosis": round(m["kurtosis"], 2),
        }

    comp_df = pd.DataFrame(rows)
    st.dataframe(comp_df, use_container_width=True)

    with st.expander("What do these metrics mean?"):
        for key, desc in METRIC_DESC.items():
            st.markdown(f"**{key.replace('_', ' ').title()}:** {desc}")

    # Risk-return scatter
    st.subheader("Risk vs. Return")
    st.caption("Ideal position is upper-left: high return, low volatility.")

    scatter_data = pd.DataFrame({
        "Ticker": valid,
        "Annualised Vol (%)": [all_metrics[t]["ann_vol"] for t in valid],
        "Total Return (%)": [all_metrics[t]["total_return"] for t in valid],
    })
    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(size=120)
        .encode(
            x=alt.X("Annualised Vol (%):Q", title="Annualised Volatility (%)"),
            y=alt.Y("Total Return (%):Q"),
            color="Ticker:N",
            tooltip=["Ticker:N", "Annualised Vol (%):Q", "Total Return (%):Q"],
        )
        .properties(height=350)
    )
    labels = scatter.mark_text(align="left", dx=8).encode(text="Ticker:N")
    st.altair_chart(scatter + labels, use_container_width=True)

# ========================== FUNDAMENTALS ====================================
with tab_fund:
    st.subheader("Key Fundamentals")
    st.caption("Snapshot of current valuation, quality, and growth metrics from Yahoo Finance.")

    fund_fields = {
        "shortName": "Company",
        "sector": "Sector",
        "marketCap": "Market Cap",
        "trailingPE": "P/E",
        "forwardPE": "Fwd P/E",
        "priceToBook": "P/B",
        "enterpriseToEbitda": "EV/EBITDA",
        "pegRatio": "PEG",
        "dividendYield": "Div Yield",
        "returnOnEquity": "ROE",
        "profitMargins": "Margin",
        "revenueGrowth": "Rev Growth",
        "debtToEquity": "D/E",
        "beta": "Beta",
    }

    fund_rows = {}
    for t in valid:
        info = all_info.get(t, {})
        row = {}
        for k, label in fund_fields.items():
            val = info.get(k)
            if val is None:
                row[label] = "—"
            elif k == "marketCap":
                row[label] = f"${val / 1e9:.1f}B"
            elif k in ("dividendYield", "returnOnEquity", "profitMargins", "revenueGrowth"):
                row[label] = f"{val * 100:.1f}%"
            elif k == "debtToEquity":
                row[label] = f"{val:.0f}"
            else:
                row[label] = f"{val:.2f}" if isinstance(val, float) else str(val)
        fund_rows[t] = row

    fund_df = pd.DataFrame(fund_rows)
    st.dataframe(fund_df, use_container_width=True)

    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in fund_fields:
                st.markdown(f"**{fund_fields[key]}:** {desc}")

# ========================== CORRELATION =====================================
with tab_corr:
    st.subheader("Return Correlation Matrix")
    st.caption(
        "Measures how closely stocks move together. "
        "Values near 1 mean they move in sync; near 0 means independent; "
        "negative means they tend to move opposite. Lower correlation = better diversification."
    )

    returns_df = pd.DataFrame({t: all_metrics[t]["daily_ret_pct"] for t in valid})
    corr = returns_df.corr().round(3)

    st.dataframe(
        corr.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1),
        use_container_width=True,
    )
