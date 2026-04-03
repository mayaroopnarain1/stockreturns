# -*- coding: utf-8 -*-
"""
Page 4 — Portfolio Risk
Enter holdings and weights to see portfolio-level risk/return metrics,
individual contributions, and diversification benefit.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history
from utils.metrics import compute_return_metrics, METRIC_DESC, metric_card

st.set_page_config(page_title="Portfolio Risk — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/account_balance_wallet: Portfolio Risk")
st.caption(
    "Enter your stock holdings and allocation weights to get portfolio-level "
    "risk metrics, diversification benefit, and per-stock risk contributions."
)

# ---------------------------------------------------------------------------
# Sidebar — portfolio input
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Portfolio Holdings")
    st.caption("Enter tickers and weights (must sum to 100%).")

    num_holdings = st.number_input("Number of holdings", min_value=2, max_value=10, value=3, step=1)

    tickers = []
    weights = []
    defaults_t = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "JNJ"]
    defaults_w = [40, 35, 25, 0, 0, 0, 0, 0, 0, 0]

    for i in range(int(num_holdings)):
        c1, c2 = st.columns([2, 1])
        t = c1.text_input(f"Ticker {i+1}", value=defaults_t[i] if i < len(defaults_t) else "", key=f"t_{i}").upper()
        w = c2.number_input(f"Weight %", value=defaults_w[i] if i < len(defaults_w) else 0, min_value=0, max_value=100, key=f"w_{i}")
        if t:
            tickers.append(t)
            weights.append(w)

    total_weight = sum(weights)
    if total_weight != 100:
        st.warning(f"Weights sum to {total_weight}% — must equal 100%.")

    horizon_map = {
        "3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y",
        "2 Years": "2y", "5 Years": "5y",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=2)

    risk_free_rate = st.number_input(
        "Annual risk-free rate", min_value=0.0, max_value=0.20,
        value=0.05, step=0.01, format="%.2f",
    )

if total_weight != 100 or len(tickers) < 2:
    st.info("Configure your portfolio in the sidebar (weights must sum to 100%).")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
w_arr = np.array(weights) / 100  # decimal weights
all_prices = {}
errors = []

with st.spinner("Fetching price data…"):
    for t in tickers:
        hist = get_price_history(t, horizon_map[horizon])
        if hist.empty:
            errors.append(t)
        else:
            all_prices[t] = hist["Close"]

if errors:
    st.error(f"Could not fetch data for: {', '.join(errors)}. Fix tickers and try again.")
    st.stop()

# Align dates across all tickers
price_df = pd.DataFrame(all_prices).dropna()
if len(price_df) < 20:
    st.error("Not enough overlapping price data. Try a shorter horizon or check tickers.")
    st.stop()

# Daily returns
ret_df = price_df.pct_change().dropna()

# ---------------------------------------------------------------------------
# Portfolio calculations
# ---------------------------------------------------------------------------
# Weighted portfolio return series
port_ret = (ret_df * w_arr).sum(axis=1)
port_ret_pct = port_ret * 100

# Portfolio cumulative return
port_cumulative = (1 + port_ret).cumprod()

# Individual cumulative returns
indiv_cum = (1 + ret_df).cumprod()

# Covariance matrix (annualised)
cov_annual = ret_df.cov() * 252

# Portfolio variance and vol
port_var = w_arr @ cov_annual.values @ w_arr
port_vol = np.sqrt(port_var) * 100  # annualised %

# Weighted average of individual vols (undiversified)
indiv_vols = ret_df.std() * np.sqrt(252)
undiversified_vol = (w_arr * indiv_vols.values).sum() * 100

# Diversification benefit
div_benefit = undiversified_vol - port_vol

# Portfolio metrics via shared function
port_prices = port_cumulative  # treat cumulative as a "price" series
port_metrics = compute_return_metrics(port_prices, risk_free_rate)

# Marginal contribution to risk (MCTR)
mctr = (cov_annual.values @ w_arr) / np.sqrt(port_var)
ctr = w_arr * mctr  # component contribution
ctr_pct = ctr / ctr.sum() * 100  # percentage of total risk

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
tab_overview, tab_contrib, tab_holdings = st.tabs(
    ["Portfolio Overview", "Risk Contributions", "Individual Holdings"]
)

# ========================== OVERVIEW ========================================
with tab_overview:
    st.subheader("Portfolio Summary")

    r1 = st.columns(4)
    metric_card(r1[0], "Portfolio Return", f"{port_metrics['total_return']:.2f}%", "total_return")
    metric_card(r1[1], "Portfolio Vol (ann.)", f"{port_vol:.2f}%", "ann_vol")
    metric_card(r1[2], "Sharpe Ratio", f"{port_metrics['sharpe']:.2f}", "sharpe")
    metric_card(r1[3], "Max Drawdown", f"{port_metrics['max_drawdown']:.2f}%", "max_drawdown")

    r2 = st.columns(4)
    r2[0].metric("Undiversified Vol", f"{undiversified_vol:.2f}%")
    r2[0].caption("Sum of weighted individual volatilities — what you'd get with perfect correlation.")
    r2[1].metric("Diversification Benefit", f"{div_benefit:.2f}%")
    r2[1].caption("Volatility saved by holding multiple stocks that don't move in perfect sync.")
    metric_card(r2[2], "Sortino Ratio", f"{port_metrics['sortino']:.2f}", "sortino")
    metric_card(r2[3], "VaR (95%)", f"{port_metrics['var_95']:.2f}%", "var_95")

    # Cumulative performance chart
    st.divider()
    st.subheader("Cumulative Performance")
    st.caption("Portfolio (weighted) vs. individual holdings, all starting at 1.0.")

    cum_df = indiv_cum.copy()
    cum_df["Portfolio"] = port_cumulative
    plot = cum_df.reset_index().melt(id_vars=["Date"], var_name="Holding", value_name="Cumulative Return")

    cum_chart = (
        alt.Chart(plot).mark_line()
        .encode(
            x="Date:T",
            y=alt.Y("Cumulative Return:Q").scale(zero=False),
            color="Holding:N",
            strokeDash=alt.condition(
                alt.datum.Holding == "Portfolio",
                alt.value([1, 0]),  # solid
                alt.value([6, 3]),  # dashed for individual
            ),
            tooltip=["Date:T", "Holding:N", alt.Tooltip("Cumulative Return:Q", format=".4f")],
        ).properties(height=400)
    )
    st.altair_chart(cum_chart, use_container_width=True)

# ========================== RISK CONTRIBUTIONS ==============================
with tab_contrib:
    st.subheader("Risk Contribution by Holding")
    st.caption(
        "Shows how much of the portfolio's total volatility each stock is responsible for. "
        "A stock can contribute more risk than its weight if it's volatile or highly correlated with the rest."
    )

    contrib_df = pd.DataFrame({
        "Ticker": tickers,
        "Weight (%)": [w * 100 for w in w_arr],
        "Ann. Vol (%)": [indiv_vols[t] * 100 for t in tickers],
        "Risk Contribution (%)": ctr_pct,
    }).set_index("Ticker").round(2)

    st.dataframe(contrib_df, use_container_width=True)

    # Bar chart comparing weight vs risk contribution
    bar_data = contrib_df[["Weight (%)", "Risk Contribution (%)"]].reset_index().melt(
        id_vars="Ticker", var_name="Measure", value_name="Percent"
    )
    bar_chart = (
        alt.Chart(bar_data).mark_bar()
        .encode(
            x="Ticker:N",
            y="Percent:Q",
            color="Measure:N",
            xOffset="Measure:N",
            tooltip=["Ticker:N", "Measure:N", alt.Tooltip("Percent:Q", format=".1f")],
        ).properties(height=350)
    )
    st.altair_chart(bar_chart, use_container_width=True)
    st.caption("If a stock's risk contribution exceeds its weight, it's a disproportionate source of portfolio volatility.")

    # Correlation matrix
    st.divider()
    st.subheader("Correlation Matrix")
    st.caption("Lower correlation between holdings = better diversification.")
    corr = ret_df.corr().round(3)
    st.dataframe(
        corr.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1),
        use_container_width=True,
    )

# ========================== INDIVIDUAL HOLDINGS =============================
with tab_holdings:
    st.subheader("Individual Holding Metrics")

    rows = {}
    for t in tickers:
        m = compute_return_metrics(price_df[t], risk_free_rate)
        rows[t] = {
            "Weight (%)": round(w_arr[tickers.index(t)] * 100, 1),
            "Total Return (%)": round(m["total_return"], 2),
            "Ann. Vol (%)": round(m["ann_vol"], 2),
            "Sharpe": round(m["sharpe"], 2),
            "Sortino": round(m["sortino"], 2),
            "Max Drawdown (%)": round(m["max_drawdown"], 2),
            "VaR 95% (%)": round(m["var_95"], 2),
        }

    hold_df = pd.DataFrame(rows)
    st.dataframe(hold_df, use_container_width=True)

    with st.expander("What do these metrics mean?"):
        for key, desc in METRIC_DESC.items():
            st.markdown(f"**{key.replace('_', ' ').title()}:** {desc}")
