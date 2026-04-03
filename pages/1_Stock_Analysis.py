# -*- coding: utf-8 -*-
"""
Page 1 — Stock Analysis
Enter a ticker → get a Buy/Hold/Sell signal backed by fundamentals,
risk metrics, momentum, and benchmark comparison. All data on one page.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.data import get_price_history, get_ticker_info
from utils.metrics import (
    compute_return_metrics, compute_benchmark_metrics, compute_signal,
    monthly_returns_table, metric_card, METRIC_DESC, FUNDAMENTAL_DESC,
)

st.set_page_config(page_title="Stock Analysis — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/search: Stock Analysis")
st.caption("Enter a ticker to get a data-driven Buy / Hold / Sell signal with full supporting analysis.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    ticker = st.text_input("Stock ticker", value="AAPL").upper()
    benchmark = st.selectbox("Benchmark", ["SPY", "QQQ"], index=0)

    horizon_map = {
        "3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y",
        "2 Years": "2y", "5 Years": "5y",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=2)
    rf = st.number_input("Risk-free rate", 0.0, 0.20, 0.05, 0.01, format="%.2f")

if not ticker:
    st.info("Enter a ticker in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with st.spinner("Fetching data…"):
    data = get_price_history(ticker, horizon_map[horizon])
    info = get_ticker_info(ticker)
    bench_data = get_price_history(benchmark, horizon_map[horizon])

if data.empty:
    st.error(f"No data for **{ticker}**. Check the symbol.")
    st.stop()

metrics = compute_return_metrics(data["Close"], rf)
returns = metrics["daily_ret_pct"]

bench_m = None
bench_comp = None
if not bench_data.empty:
    bench_m = compute_return_metrics(bench_data["Close"], rf)
    bench_comp = compute_benchmark_metrics(metrics["daily_ret"], bench_m["daily_ret"], rf)

# ---------------------------------------------------------------------------
# SIGNAL — the headline
# ---------------------------------------------------------------------------
sig = compute_signal(info, metrics, bench_comp)

signal_colors = {"Buy": "#2ecc71", "Hold": "#f39c12", "Sell": "#e74c3c"}
signal_emoji = {"Buy": ":material/trending_up:", "Hold": ":material/trending_flat:", "Sell": ":material/trending_down:"}

st.markdown("---")
col_sig, col_score, col_note = st.columns([1, 1, 2])

with col_sig:
    color = signal_colors[sig["signal"]]
    st.markdown(
        f"<div style='text-align:center; padding:20px; border-radius:12px; "
        f"background-color:{color}20; border:2px solid {color};'>"
        f"<span style='font-size:3rem; font-weight:700; color:{color};'>"
        f"{sig['signal'].upper()}</span></div>",
        unsafe_allow_html=True,
    )

with col_score:
    st.metric("Composite Score", f"{sig['score']} / 100")
    st.caption("Weighted blend of valuation, quality, momentum, and risk scores.")

with col_note:
    st.markdown(
        f"**{ticker}** scores **{sig['score']}** based on the quantitative factors below. "
        f"This is a data-driven signal, not financial advice — it tells you what the "
        f"numbers say, not what the market will do."
    )
    # Score breakdown bar
    bd = sig["breakdown"]
    breakdown_df = pd.DataFrame({
        "Dimension": list(bd.keys()),
        "Score": [round(v, 1) for v in bd.values()],
        "Weight": ["30%", "25%", "20%", "25%"],
    })
    st.dataframe(breakdown_df.set_index("Dimension"), width="stretch")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs with full supporting data
# ---------------------------------------------------------------------------
tab_fund, tab_risk, tab_bench, tab_returns, tab_dist, tab_monthly = st.tabs(
    ["Fundamentals", "Risk Metrics", "vs. Benchmark", "Returns", "Distribution", "Monthly Heatmap"]
)

# ========================== FUNDAMENTALS ====================================
with tab_fund:
    st.subheader(f"{ticker} — Fundamentals")
    name = info.get("shortName", ticker)
    sector = info.get("sector", "—")
    industry = info.get("industry", "—")
    st.caption(f"{name}  ·  {sector}  ·  {industry}")

    r1 = st.columns(4)
    pe = info.get("trailingPE")
    r1[0].metric("P/E Ratio", f"{pe:.1f}" if pe else "—")
    r1[0].caption(FUNDAMENTAL_DESC["trailingPE"])

    fpe = info.get("forwardPE")
    r1[1].metric("Forward P/E", f"{fpe:.1f}" if fpe else "—")
    r1[1].caption(FUNDAMENTAL_DESC["forwardPE"])

    pb = info.get("priceToBook")
    r1[2].metric("Price/Book", f"{pb:.2f}" if pb else "—")
    r1[2].caption(FUNDAMENTAL_DESC["priceToBook"])

    eve = info.get("enterpriseToEbitda")
    r1[3].metric("EV/EBITDA", f"{eve:.1f}" if eve else "—")
    r1[3].caption(FUNDAMENTAL_DESC["enterpriseToEbitda"])

    r2 = st.columns(4)
    peg = info.get("pegRatio")
    r2[0].metric("PEG Ratio", f"{peg:.2f}" if peg else "—")
    r2[0].caption(FUNDAMENTAL_DESC["pegRatio"])

    dy = info.get("dividendYield")
    r2[1].metric("Dividend Yield", f"{dy*100:.2f}%" if dy else "—")
    r2[1].caption(FUNDAMENTAL_DESC["dividendYield"])

    roe = info.get("returnOnEquity")
    r2[2].metric("Return on Equity", f"{roe*100:.1f}%" if roe else "—")
    r2[2].caption(FUNDAMENTAL_DESC["returnOnEquity"])

    pm = info.get("profitMargins")
    r2[3].metric("Profit Margin", f"{pm*100:.1f}%" if pm else "—")
    r2[3].caption(FUNDAMENTAL_DESC["profitMargins"])

    r3 = st.columns(4)
    de = info.get("debtToEquity")
    r3[0].metric("Debt/Equity", f"{de:.0f}" if de else "—")
    r3[0].caption(FUNDAMENTAL_DESC["debtToEquity"])

    cr = info.get("currentRatio")
    r3[1].metric("Current Ratio", f"{cr:.2f}" if cr else "—")
    r3[1].caption(FUNDAMENTAL_DESC["currentRatio"])

    rg = info.get("revenueGrowth")
    r3[2].metric("Revenue Growth", f"{rg*100:.1f}%" if rg else "—")
    r3[2].caption(FUNDAMENTAL_DESC["revenueGrowth"])

    eg = info.get("earningsGrowth")
    r3[3].metric("Earnings Growth", f"{eg*100:.1f}%" if eg else "—")
    r3[3].caption(FUNDAMENTAL_DESC["earningsGrowth"])

# ========================== RISK METRICS ====================================
with tab_risk:
    st.subheader(f"{ticker} — Risk & Return")

    r1 = st.columns(4)
    metric_card(r1[0], "Total Return", f"{metrics['total_return']:.2f}%", "total_return")
    metric_card(r1[1], "Ann. Return", f"{metrics['ann_return']:.2f}%", "ann_return")
    metric_card(r1[2], "Ann. Volatility", f"{metrics['ann_vol']:.2f}%", "ann_vol")
    metric_card(r1[3], "Sharpe Ratio", f"{metrics['sharpe']:.2f}", "sharpe")

    r2 = st.columns(4)
    metric_card(r2[0], "Sortino Ratio", f"{metrics['sortino']:.2f}", "sortino")
    metric_card(r2[1], "Calmar Ratio", f"{metrics['calmar']:.2f}", "calmar")
    metric_card(r2[2], "Max Drawdown", f"{metrics['max_drawdown']:.2f}%", "max_drawdown")
    metric_card(r2[3], "VaR (95%)", f"{metrics['var_95']:.2f}%", "var_95")

    r3 = st.columns(4)
    metric_card(r3[0], "CVaR (95%)", f"{metrics['cvar_95']:.2f}%", "cvar_95")
    metric_card(r3[1], "Skewness", f"{metrics['skewness']:.2f}", "skewness")
    metric_card(r3[2], "Kurtosis", f"{metrics['kurtosis']:.2f}", "kurtosis")

    # Drawdown chart
    st.divider()
    st.subheader("Drawdown Over Time")
    st.caption("How far the stock has fallen from its running peak at any point. Deeper troughs = more pain.")
    dd = metrics["drawdown_series"].reset_index()
    dd.columns = ["Date", "Drawdown (%)"]
    dd_chart = (
        alt.Chart(dd).mark_area(opacity=0.4, color="#e74c3c")
        .encode(
            x="Date:T", y=alt.Y("Drawdown (%):Q"),
            tooltip=["Date:T", alt.Tooltip("Drawdown (%):Q", format=".2f")],
        ).properties(height=250)
    )
    dd_line = alt.Chart(dd).mark_line(color="#e74c3c", strokeWidth=1).encode(x="Date:T", y="Drawdown (%):Q")
    st.altair_chart(dd_chart + dd_line, width="stretch")

# ========================== BENCHMARK =======================================
with tab_bench:
    st.subheader(f"{ticker} vs. {benchmark}")

    if bench_comp:
        r1 = st.columns(3)
        metric_card(r1[0], "Alpha (ann.)", f"{bench_comp['alpha']:.2f}%", "alpha")
        metric_card(r1[1], "Beta", f"{bench_comp['beta']:.2f}", "beta")
        metric_card(r1[2], "R-Squared", f"{bench_comp['r_squared']:.2f}", "r_squared")

        r2 = st.columns(3)
        metric_card(r2[0], "Treynor Ratio", f"{bench_comp['treynor']:.2f}", "treynor")
        metric_card(r2[1], "Upside Capture", f"{bench_comp['up_capture']:.1f}%", "up_capture")
        metric_card(r2[2], "Downside Capture", f"{bench_comp['down_capture']:.1f}%", "down_capture")

        # Side-by-side table
        st.divider()
        comp_table = pd.DataFrame({
            ticker: {
                "Total Return (%)": f"{metrics['total_return']:.2f}",
                "Ann. Volatility (%)": f"{metrics['ann_vol']:.2f}",
                "Sharpe": f"{metrics['sharpe']:.2f}",
                "Sortino": f"{metrics['sortino']:.2f}",
                "Max Drawdown (%)": f"{metrics['max_drawdown']:.2f}",
            },
            benchmark: {
                "Total Return (%)": f"{bench_m['total_return']:.2f}",
                "Ann. Volatility (%)": f"{bench_m['ann_vol']:.2f}",
                "Sharpe": f"{bench_m['sharpe']:.2f}",
                "Sortino": f"{bench_m['sortino']:.2f}",
                "Max Drawdown (%)": f"{bench_m['max_drawdown']:.2f}",
            },
        })
        st.dataframe(comp_table, width="stretch")

        # Normalised chart
        st.divider()
        st.subheader("Normalised Performance")
        norm = pd.DataFrame({
            ticker: data["Close"] / data["Close"].iloc[0],
            benchmark: bench_data["Close"] / bench_data["Close"].iloc[0],
        })
        plot = norm.reset_index().melt(id_vars="Date", var_name="Ticker", value_name="Normalised")
        chart = (
            alt.Chart(plot).mark_line()
            .encode(x="Date:T", y=alt.Y("Normalised:Q").scale(zero=False), color="Ticker:N")
            .properties(height=350)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.warning("Benchmark data unavailable.")

# ========================== RETURNS =========================================
with tab_returns:
    st.subheader("Daily Returns")
    ret_df = returns.reset_index()
    ret_df.columns = ["Date", "Daily Return (%)"]
    bar = (
        alt.Chart(ret_df).mark_bar()
        .encode(
            x="Date:T", y="Daily Return (%):Q",
            color=alt.condition(alt.datum["Daily Return (%)"] >= 0, alt.value("#2ecc71"), alt.value("#e74c3c")),
            tooltip=["Date:T", alt.Tooltip("Daily Return (%):Q", format=".4f")],
        ).properties(height=350)
    )
    st.altair_chart(bar, width="stretch")

    # Rolling vol
    st.subheader("Rolling 30-Day Volatility")
    rvol = returns.rolling(30).std().dropna().reset_index()
    rvol.columns = ["Date", "Rolling Vol (%)"]
    vol_area = alt.Chart(rvol).mark_area(opacity=0.25, color="#3498db").encode(x="Date:T", y="Rolling Vol (%):Q").properties(height=250)
    vol_line = alt.Chart(rvol).mark_line(color="#3498db", strokeWidth=1.5).encode(x="Date:T", y="Rolling Vol (%):Q")
    if bench_m:
        br = bench_m["daily_ret_pct"].rolling(30).std().dropna().reset_index()
        br.columns = ["Date", "Rolling Vol (%)"]
        bl = alt.Chart(br).mark_line(color="#e67e22", strokeWidth=1.5, strokeDash=[6,3]).encode(x="Date:T", y="Rolling Vol (%):Q")
        st.altair_chart(vol_area + vol_line + bl, width="stretch")
        st.caption(f"Blue = {ticker}  ·  Orange dashed = {benchmark}")
    else:
        st.altair_chart(vol_area + vol_line, width="stretch")

# ========================== DISTRIBUTION ====================================
with tab_dist:
    st.subheader("Return Distribution")
    st.caption("If bars extend further left than the orange curve, the stock has fatter downside tails than normal.")
    ret_df = returns.reset_index()
    ret_df.columns = ["Date", "Daily Return (%)"]
    avg, std = metrics["avg_daily"], metrics["std_daily"]

    hist = alt.Chart(ret_df).mark_bar(opacity=0.75).encode(
        alt.X("Daily Return (%):Q", bin=alt.Bin(maxbins=50)), alt.Y("count()"), tooltip=["count()"]
    ).properties(height=350)

    x_rng = np.linspace(returns.min(), returns.max(), 200)
    npdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_rng - avg) / std) ** 2)
    bw = (returns.max() - returns.min()) / 50
    ndf = pd.DataFrame({"Daily Return (%)": x_rng, "Normal": npdf * len(returns) * bw})
    nline = alt.Chart(ndf).mark_line(color="orange", strokeDash=[6,3], strokeWidth=2).encode(
        x="Daily Return (%):Q", y=alt.Y("Normal:Q", title="Frequency")
    )
    mrule = alt.Chart(pd.DataFrame({"x": [avg]})).mark_rule(color="red", strokeDash=[4,4], strokeWidth=2).encode(x="x:Q")
    st.altair_chart(hist + nline + mrule, width="stretch")
    st.caption("Orange = normal distribution  ·  Red = mean return")

# ========================== MONTHLY HEATMAP =================================
with tab_monthly:
    st.subheader("Monthly Returns Heatmap")
    st.caption("Each cell shows the total return for that month. Green = positive, red = negative.")

    mt = monthly_returns_table(data["Close"])
    if not mt.empty:
        # Add YTD column
        mt["YTD"] = mt.sum(axis=1).round(2)
        st.dataframe(
            mt.style.background_gradient(cmap="RdYlGn", axis=None, vmin=-10, vmax=10)
            .format("{:.1f}%", na_rep="—"),
            width="stretch",
        )
    else:
        st.info("Not enough data for a monthly breakdown.")
