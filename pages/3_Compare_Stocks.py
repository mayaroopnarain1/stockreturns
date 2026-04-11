# -*- coding: utf-8 -*-
"""
Page 3 — Compare Stocks
Side-by-side 2–5 ticker comparison: performance, risk, fundamentals,
correlation, and peer/sector average analysis.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history_batch, get_price_history, get_ticker_info, SECTOR_ETFS
from utils.metrics import compute_return_metrics, METRIC_DESC, FUNDAMENTAL_DESC

st.set_page_config(page_title="Compare Stocks — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title(":material/compare_arrows: Compare Stocks")
st.caption("Pick 2–5 tickers and compare returns, risk, fundamentals, and relative performance.")

with st.sidebar:
    raw = st.text_input("Tickers (comma-separated)", "AAPL, MSFT, GOOGL")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    if len(tickers) < 2:
        st.warning("Enter at least 2 tickers.")
        st.stop()
    if len(tickers) > 5:
        tickers = tickers[:5]
        st.info("Using first 5 tickers.")
    horizon_map = {
        "3M": "3mo", "6M": "6mo", "1Y": "1y", "2Y": "2y", "5Y": "5y",
    }
    horizon = st.pills("Time horizon", list(horizon_map.keys()), default="1Y")
    if not horizon:
        horizon = "1Y"
    rf = st.number_input("Risk-free rate", 0.0, 0.20, 0.05, 0.01, format="%.2f")

# ---------------------------------------------------------------------------
# Batch fetch all prices at once (single API call)
# ---------------------------------------------------------------------------
with st.spinner("Fetching…"):
    price_df = get_price_history_batch(tickers, horizon_map[horizon])
    infos = {t: get_ticker_info(t) for t in tickers}

empty_cols = [t for t in tickers if t not in price_df.columns or price_df[t].isna().all()]
if empty_cols:
    st.warning(f"No data for: {', '.join(empty_cols)}")
valid = [t for t in tickers if t in price_df.columns and not price_df[t].isna().all()]
if len(valid) < 2:
    st.error("Need 2+ valid tickers.")
    st.stop()

prices = price_df[valid].dropna()
mets = {t: compute_return_metrics(prices[t], rf) for t in valid}

# ---------------------------------------------------------------------------
# Fetch sector ETFs for sector comparison tab
# ---------------------------------------------------------------------------
sectors_in_use = {}
for t in valid:
    sec = infos.get(t, {}).get("sector", "")
    etf = SECTOR_ETFS.get(sec)
    if etf and sec not in sectors_in_use:
        sectors_in_use[sec] = etf

sector_prices = {}
if sectors_in_use:
    etf_tickers = list(set(sectors_in_use.values()))
    etf_df = get_price_history_batch(etf_tickers, horizon_map[horizon])
    if not etf_df.empty:
        for sec, etf in sectors_in_use.items():
            if etf in etf_df.columns and not etf_df[etf].isna().all():
                sector_prices[sec] = etf_df[etf]

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_perf, tab_peer, tab_risk, tab_fund, tab_corr = st.tabs(
    ["Performance", "vs. Peer & Sector", "Risk Metrics", "Fundamentals", "Correlation"]
)

# ========================== PERFORMANCE ======================================
with tab_perf:
    st.subheader("Normalized Price (Start = 1.0)")
    st.caption("Compares cumulative performance regardless of share price.")
    norm = prices.div(prices.iloc[0])
    plot = norm.reset_index().melt(id_vars="Date", var_name="Ticker", value_name="Norm")
    c = alt.Chart(plot).mark_line().encode(
        x="Date:T", y=alt.Y("Norm:Q").scale(zero=False), color="Ticker:N",
        tooltip=["Date:T", "Ticker:N", alt.Tooltip("Norm:Q", format=".4f")]
    ).properties(height=400)
    st.altair_chart(c, width="stretch")

    cols = st.columns(len(valid))
    for i, t in enumerate(valid):
        cols[i].metric(t, f"{mets[t]['total_return']:.2f}%")

# ========================== PEER & SECTOR AVG ================================
with tab_peer:
    st.subheader("Individual Stocks vs. Peer & Sector Averages")
    st.caption(
        "**Peer average** = average of the other selected stocks (excluding itself). "
        "**Sector average** = SPDR sector ETF for each stock's sector."
    )

    norm = prices.div(prices.iloc[0])

    NUM_COLS = 2
    chart_cols = st.columns(NUM_COLS)

    for i, ticker in enumerate(valid):
        # Peer average (excluding current stock)
        peers = norm.drop(columns=[ticker])
        peer_avg = peers.mean(axis=1)

        # Build plot data
        series_data = {
            "Date": norm.index,
            ticker: norm[ticker],
            "Peer Avg": peer_avg,
        }
        color_domain = [ticker, "Peer Avg"]
        color_range = ["#e74c3c", "#888888"]

        # Sector ETF line (if available)
        stock_sector = infos.get(ticker, {}).get("sector", "")
        if stock_sector in sector_prices:
            sec_series = sector_prices[stock_sector]
            # Align and normalize to same start date
            aligned = sec_series.reindex(norm.index).dropna()
            if len(aligned) > 10:
                sec_norm = aligned / aligned.iloc[0]
                etf_name = SECTOR_ETFS[stock_sector]
                series_data[f"Sector ({etf_name})"] = sec_norm
                color_domain.append(f"Sector ({etf_name})")
                color_range.append("#3498db")

        plot_df = pd.DataFrame(series_data).melt(
            id_vars=["Date"], var_name="Series", value_name="Normalized"
        )

        chart = (
            alt.Chart(plot_df).mark_line().encode(
                alt.X("Date:T"),
                alt.Y("Normalized:Q").scale(zero=False),
                alt.Color(
                    "Series:N",
                    scale=alt.Scale(domain=color_domain, range=color_range),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=["Date:T", "Series:N", alt.Tooltip("Normalized:Q", format=".4f")],
            ).properties(title=f"{ticker} vs peers & sector", height=300)
        )

        # Delta chart: stock minus peer average (split into pos/neg layers)
        delta_raw = norm[ticker] - peer_avg
        delta_df = pd.DataFrame({
            "Date": norm.index,
            "Delta": delta_raw,
        })
        delta_pos = delta_df.copy()
        delta_pos.loc[delta_pos["Delta"] < 0, "Delta"] = 0
        delta_neg = delta_df.copy()
        delta_neg.loc[delta_neg["Delta"] > 0, "Delta"] = 0

        base_x = alt.X("Date:T")
        base_y = alt.Y("Delta:Q")
        pos_area = alt.Chart(delta_pos).mark_area(opacity=0.5, color="#2ecc71").encode(
            base_x, base_y, tooltip=["Date:T", alt.Tooltip("Delta:Q", format=".4f")]
        )
        neg_area = alt.Chart(delta_neg).mark_area(opacity=0.5, color="#e74c3c").encode(
            base_x, base_y, tooltip=["Date:T", alt.Tooltip("Delta:Q", format=".4f")]
        )
        zero_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            strokeDash=[4, 4], color="gray"
        ).encode(y="y:Q")
        delta_chart = (pos_area + neg_area + zero_rule).properties(
            title=f"{ticker} minus peer avg", height=200
        )

        col_idx = i % NUM_COLS
        with chart_cols[col_idx]:
            cell = st.container(border=True)
            cell.altair_chart(chart, use_container_width=True)
            cell.altair_chart(delta_chart, use_container_width=True)
            # Summary metric
            final_delta = (norm[ticker].iloc[-1] - peer_avg.iloc[-1]) * 100
            cell.caption(
                f"{'Outperformed' if final_delta > 0 else 'Underperformed'} peers by "
                f"**{abs(final_delta):.1f}pp** over the period"
            )

# ========================== RISK METRICS =====================================
with tab_risk:
    st.subheader("Risk & Return Comparison")
    rows = {}
    for t in valid:
        m = mets[t]
        rows[t] = {
            "Total Return (%)": round(m["total_return"], 2),
            "Ann. Vol (%)": round(m["ann_vol"], 2),
            "Sharpe": round(m["sharpe"], 2),
            "Sortino": round(m["sortino"], 2),
            "Calmar": round(m["calmar"], 2),
            "Max Drawdown (%)": round(m["max_drawdown"], 2),
            "VaR 95% (%)": round(m["var_95"], 2),
            "CVaR 95% (%)": round(m["cvar_95"], 2),
        }
    st.dataframe(pd.DataFrame(rows), width="stretch")

    with st.expander("What do these metrics mean?"):
        for k, d in METRIC_DESC.items():
            st.markdown(f"**{k.replace('_', ' ').title()}:** {d}")

    st.subheader("Risk vs. Return")
    st.caption("Ideal: upper-left (high return, low vol).")
    sd = pd.DataFrame({
        "Ticker": valid,
        "Ann. Vol (%)": [mets[t]["ann_vol"] for t in valid],
        "Total Return (%)": [mets[t]["total_return"] for t in valid],
    })
    sc = alt.Chart(sd).mark_circle(size=120).encode(
        x=alt.X("Ann. Vol (%):Q"), y="Total Return (%):Q", color="Ticker:N",
        tooltip=["Ticker:N", "Ann. Vol (%):Q", "Total Return (%):Q"]
    ).properties(height=350)
    lb = sc.mark_text(align="left", dx=8).encode(text="Ticker:N")
    st.altair_chart(sc + lb, width="stretch")

# ========================== FUNDAMENTALS =====================================
with tab_fund:
    st.subheader("Key Fundamentals")
    ff = {
        "shortName": "Company", "sector": "Sector", "marketCap": "Mkt Cap",
        "trailingPE": "P/E", "forwardPE": "Fwd P/E", "enterpriseToEbitda": "EV/EBITDA",
        "dividendYield": "Div Yield", "returnOnEquity": "ROE",
        "profitMargins": "Margin", "grossMargins": "Gross Margin",
        "revenueGrowth": "Rev Growth", "debtToEquity": "D/E", "beta": "Beta",
    }
    fr = {}
    for t in valid:
        info = infos.get(t, {})
        row = {}
        for k, l in ff.items():
            v = info.get(k)
            if v is None:
                row[l] = "—"
            elif k == "marketCap":
                row[l] = f"${v / 1e9:.1f}B"
            elif k in ("dividendYield", "returnOnEquity", "profitMargins", "grossMargins", "revenueGrowth"):
                row[l] = f"{v * 100:.1f}%"
            elif k == "debtToEquity":
                row[l] = f"{v:.0f}"
            else:
                row[l] = f"{v:.2f}" if isinstance(v, float) else str(v)
        fr[t] = row
    st.dataframe(pd.DataFrame(fr), width="stretch")

# ========================== CORRELATION ======================================
with tab_corr:
    st.subheader("Return Correlation Matrix")
    st.caption("Near 1 = move together; near 0 = independent; negative = move opposite. Lower = better diversification.")
    rdf = pd.DataFrame({t: mets[t]["daily_ret_pct"] for t in valid})
    corr = rdf.corr().round(3)
    st.dataframe(corr.style.background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1), width="stretch")
