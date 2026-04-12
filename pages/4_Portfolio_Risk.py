# -*- coding: utf-8 -*-
"""
Page 4 — Portfolio Risk
Pick holdings via multiselect, assign weights → portfolio-level risk,
diversification, risk contributions.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history_batch, SP500_TICKERS
from utils.metrics import compute_return_metrics, metric_card

st.set_page_config(page_title="Portfolio Risk — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title(":material/account_balance_wallet: Portfolio Risk")
st.caption("Pick holdings, assign weights, and get portfolio-level risk metrics and per-stock risk contributions.")

# ---------------------------------------------------------------------------
# Sidebar — ticker selection + weight assignment
# ---------------------------------------------------------------------------
QUICK_GROUPS = {
    "Mag 7": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
    "Big Banks": ["JPM", "BAC", "GS", "MS", "WFC", "C"],
    "Healthcare": ["UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
}

with st.sidebar:
    st.subheader("Holdings")

    # Quick-add buttons for common groups
    st.caption("Quick add a group:")
    _qg_cols = st.columns(2)
    for idx, (grp_name, grp_tickers) in enumerate(QUICK_GROUPS.items()):
        if _qg_cols[idx % 2].button(grp_name, key=f"qg_{grp_name}", use_container_width=True):
            st.session_state["portfolio_tickers"] = grp_tickers
            st.rerun()

    _port_default = st.session_state.get("portfolio_tickers", ["AAPL", "MSFT", "GOOGL"])
    _opts = sorted(set(SP500_TICKERS) | set(_port_default))
    tickers = st.multiselect(
        "Select stocks",
        options=_opts,
        default=_port_default,
        max_selections=30,
        accept_new_options=True,
        placeholder="Search or type tickers",
    )
    st.caption("Not limited to S&P 500 — type any valid ticker.")
    tickers = [t.upper() for t in tickers]

    # Persist selected tickers so Compare Stocks can read them
    st.session_state["portfolio_tickers"] = list(tickers)

    if len(tickers) < 2:
        st.warning("Pick at least 2 holdings.")
        st.stop()

    # Dynamic weight inputs for each selected ticker
    st.divider()
    st.caption("Assign weights (must sum to 100%).")
    weights = []
    # Suggest equal weight as default
    equal_w = round(100 / len(tickers))
    for i, t in enumerate(tickers):
        # Last ticker gets the remainder so defaults sum to exactly 100
        default_w = equal_w if i < len(tickers) - 1 else 100 - equal_w * (len(tickers) - 1)
        w = st.number_input(
            f"{t}", min_value=0, max_value=100,
            value=max(0, default_w), key=f"pw_{t}",
        )
        weights.append(w)

    total_w = sum(weights)
    if total_w == 100:
        st.success(f"Weights sum to 100%.")
    else:
        st.warning(f"Weights sum to {total_w}%.")

    st.divider()
    horizon_map = {"3M": "3mo", "6M": "6mo", "1Y": "1y", "2Y": "2y", "5Y": "5y"}
    _saved_horizon = st.session_state.get("shared_horizon", "1Y")
    _h_default = _saved_horizon if _saved_horizon in horizon_map else "1Y"
    horizon = st.pills("Time horizon", list(horizon_map.keys()), default=_h_default)
    if not horizon:
        horizon = "1Y"
    st.session_state["shared_horizon"] = horizon
    _saved_rf = st.session_state.get("shared_rf", 0.05)
    rf = st.number_input("Risk-free rate", 0.0, 0.20, _saved_rf, 0.01, format="%.2f")
    st.session_state["shared_rf"] = rf
    st.caption("Default 5% approximates the current short-term Treasury yield.")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if total_w != 100:
    st.warning(f"Weights sum to **{total_w}%** — adjust in the sidebar so they total 100%.")
    st.stop()

# ---------------------------------------------------------------------------
# Fetch data (single batch call)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Portfolio calculations
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
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
        strokeDash=alt.condition(alt.datum.Holding == "Portfolio", alt.value([1, 0]), alt.value([6, 3])),
        tooltip=["Date:T", "Holding:N", alt.Tooltip("Cumulative:Q", format=".4f")]
    ).properties(height=400)
    st.altair_chart(ch, width="stretch")

with tab_cont:
    st.subheader("Risk Contribution by Holding")
    st.caption("A stock can contribute more risk than its weight if it's volatile or correlated with the rest.")
    cdf = pd.DataFrame({
        "Ticker": tickers, "Weight (%)": [w * 100 for w in w_arr],
        "Ann. Vol (%)": [indiv_vols[t] * 100 for t in tickers],
        "Risk Contribution (%)": ctr_pct,
    }).set_index("Ticker").round(2)
    st.dataframe(cdf, width="stretch")

    bd = cdf[["Weight (%)", "Risk Contribution (%)"]].reset_index().melt(id_vars="Ticker", var_name="Measure", value_name="Pct")
    bc = alt.Chart(bd).mark_bar().encode(
        x="Ticker:N", y="Pct:Q", color="Measure:N", xOffset="Measure:N",
        tooltip=["Ticker:N", "Measure:N", alt.Tooltip("Pct:Q", format=".1f")]
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
            "Weight (%)": round(w_arr[tickers.index(t)] * 100, 1),
            "Total Return (%)": round(m["total_return"], 2),
            "Ann. Vol (%)": round(m["ann_vol"], 2),
            "Sharpe": round(m["sharpe"], 2),
            "Sortino": round(m["sortino"], 2),
            "Max DD (%)": round(m["max_drawdown"], 2),
        }
    st.dataframe(pd.DataFrame(rows), width="stretch")
