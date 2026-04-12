# -*- coding: utf-8 -*-
"""
Page 1 — Stock Analysis
Enter a ticker → get a Buy/Hold/Sell signal backed by fundamentals,
risk metrics, momentum, benchmark comparison, and analyst consensus.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from datetime import date, timedelta
from utils.data import get_price_history, get_price_history_dates, get_ticker_info, fetch_macro_context, SP500_TICKERS
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
    _recent = st.session_state.get("recent_tickers", [])
    _analysis_default = [_recent[0]] if _recent else ["AAPL"]
    ticker_sel = st.multiselect(
        "Stock ticker",
        options=sorted(SP500_TICKERS),
        default=_analysis_default,
        max_selections=1,
        accept_new_options=True,
        placeholder="Search or type a ticker",
    )
    ticker = ticker_sel[0].upper() if ticker_sel else ""
    _saved_bench = st.session_state.get("shared_benchmark", "SPY")
    benchmark = st.selectbox("Benchmark", ["SPY", "QQQ"], index=["SPY", "QQQ"].index(_saved_bench) if _saved_bench in ["SPY", "QQQ"] else 0)
    st.session_state["shared_benchmark"] = benchmark

    horizon_map = {
        "3M": "3mo", "6M": "6mo", "1Y": "1y",
        "2Y": "2y", "5Y": "5y", "Custom": "custom",
    }
    _saved_horizon = st.session_state.get("shared_horizon", "1Y")
    horizon = st.pills("Time horizon", list(horizon_map.keys()), default=_saved_horizon)
    if not horizon:
        horizon = "1Y"
    st.session_state["shared_horizon"] = horizon
    use_custom = horizon_map[horizon] == "custom"
    custom_start = custom_end = None
    if use_custom:
        custom_start = st.date_input("Start date", value=date.today() - timedelta(days=365))
        custom_end = st.date_input("End date", value=date.today())
        if custom_start >= custom_end:
            st.error("Start must be before end.")
            st.stop()

    with st.expander("Settings"):
        _saved_rf = st.session_state.get("shared_rf", 0.05)
        rf = st.number_input("Risk-free rate", 0.0, 0.20, _saved_rf, 0.01, format="%.2f")
        st.session_state["shared_rf"] = rf
        st.caption("Default 5% approximates the current short-term Treasury yield.")
        roll_win = st.selectbox("Rolling vol window (days)", [21, 30, 60], index=1)

if not ticker:
    st.info("Enter a ticker in the sidebar.")
    st.stop()

# Track recently analyzed tickers for cross-page convenience
_recent = st.session_state.get("recent_tickers", [])
if ticker not in _recent:
    _recent = [ticker] + _recent[:9]  # Keep last 10
    st.session_state["recent_tickers"] = _recent

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def _load(sym):
    if use_custom:
        return get_price_history_dates(sym, str(custom_start), str(custom_end))
    return get_price_history(sym, horizon_map[horizon])

with st.spinner("Fetching data…"):
    data = _load(ticker)
    info = get_ticker_info(ticker)
    bench_data = _load(benchmark)

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
# MACRO CONTEXT — market environment at a glance
# ---------------------------------------------------------------------------
macro = fetch_macro_context()
if macro["tnx"] is not None or macro["vix"] is not None:
    mc1, mc2 = st.columns(2)
    if macro["tnx"] is not None:
        mc1.metric("10-Year Treasury Yield", f"{macro['tnx']:.2f}%")
        mc1.caption(macro["tnx_desc"])
    if macro["vix"] is not None:
        mc2.metric("VIX (Fear Index)", f"{macro['vix']:.1f}")
        mc2.caption(macro["vix_desc"])

# ---------------------------------------------------------------------------
# SIGNAL — the headline
# ---------------------------------------------------------------------------
sig = compute_signal(info, metrics, bench_comp)

signal_colors = {"Buy": "#2ecc71", "Hold": "#f39c12", "Sell": "#e74c3c"}

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
    st.caption("Weighted blend of valuation, quality, momentum, risk, and analyst consensus.")

with col_note:
    st.markdown(sig.get("why", ""))
    st.caption("This is a data-driven signal, not financial advice — it tells you what the numbers say, not what the market will do.")
    # Score breakdown bar with weights
    bd = sig["breakdown"]
    wt = sig.get("weights", {})
    breakdown_df = pd.DataFrame({
        "Dimension": list(bd.keys()),
        "Score": [round(v, 1) for v in bd.values()],
        "Weight": [f"{wt.get(d, 0)*100:.0f}%" for d in bd.keys()],
    })
    st.dataframe(breakdown_df.set_index("Dimension"), width="stretch")

# Analyst consensus + earnings date
consensus_col, earnings_col = st.columns(2)
with consensus_col:
    target_price = info.get("targetMeanPrice")
    rec = info.get("recommendationMean")
    cur = info.get("currentPrice")
    if target_price and cur:
        upside = (target_price / cur - 1) * 100
        st.metric("Wall Street Price Target", f"${target_price:.2f}", f"{upside:+.1f}% upside")
    if rec:
        rec_labels = {1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Sell", 5: "Strong Sell"}
        nearest = rec_labels.get(round(rec), f"{rec:.1f}")
        st.caption(f"Analyst consensus: **{nearest}** ({rec:.1f}/5)")
    n_analysts = info.get("numberOfAnalystOpinions")
    if n_analysts:
        st.caption(f"Based on {n_analysts} analyst{'s' if n_analysts > 1 else ''}")

with earnings_col:
    from datetime import datetime
    raw_earnings = info.get("earningsTimestamp") or info.get("earningsDate")
    earnings_dt = None
    if isinstance(raw_earnings, (int, float)) and raw_earnings > 0:
        earnings_dt = datetime.fromtimestamp(raw_earnings)
    elif isinstance(raw_earnings, list) and raw_earnings:
        try:
            earnings_dt = datetime.fromtimestamp(raw_earnings[0])
        except Exception:
            pass
    if earnings_dt:
        days_until = (earnings_dt - datetime.now()).days
        if days_until >= 0:
            st.metric("Next Earnings", earnings_dt.strftime("%b %d, %Y"), f"in {days_until} days")
            if days_until <= 14:
                st.caption("Earnings are imminent — the signal is based on trailing data and could shift significantly.")
        else:
            st.metric("Last Earnings", earnings_dt.strftime("%b %d, %Y"))
    else:
        st.caption("Earnings date not available.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs with full supporting data
# ---------------------------------------------------------------------------
tab_fund, tab_risk, tab_bench, tab_returns, tab_monthly = st.tabs(
    ["Fundamentals", "Risk Metrics", "vs. Benchmark", "Returns & Volatility", "Monthly Heatmap"]
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

    eve = info.get("enterpriseToEbitda")
    r1[2].metric("EV/EBITDA", f"{eve:.1f}" if eve else "—")
    r1[2].caption(FUNDAMENTAL_DESC["enterpriseToEbitda"])

    # FCF Yield — new metric
    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")
    if fcf and mcap and mcap > 0:
        fcf_yield = fcf / mcap * 100
        r1[3].metric("FCF Yield", f"{fcf_yield:.1f}%")
        r1[3].caption("Free cash flow ÷ market cap. Higher = more cash generated per dollar of market value. Above 5% is strong.")
    else:
        r1[3].metric("FCF Yield", "—")
        r1[3].caption("Free cash flow ÷ market cap.")

    r2 = st.columns(4)
    roe = info.get("returnOnEquity")
    r2[0].metric("Return on Equity", f"{roe*100:.1f}%" if roe else "—")
    r2[0].caption(FUNDAMENTAL_DESC["returnOnEquity"])

    pm = info.get("profitMargins")
    r2[1].metric("Profit Margin", f"{pm*100:.1f}%" if pm else "—")
    r2[1].caption(FUNDAMENTAL_DESC["profitMargins"])

    gm = info.get("grossMargins")
    r2[2].metric("Gross Margin", f"{gm*100:.1f}%" if gm else "—")
    r2[2].caption("Revenue minus cost of goods sold ÷ revenue. Higher gross margins often indicate pricing power and a durable competitive moat.")

    dy = info.get("dividendYield")
    r2[3].metric("Dividend Yield", f"{dy*100:.2f}%" if dy else "—")
    r2[3].caption(FUNDAMENTAL_DESC["dividendYield"])

    r3 = st.columns(4)
    de = info.get("debtToEquity")
    r3[0].metric("Debt/Equity", f"{de:.0f}" if de else "—")
    r3[0].caption(FUNDAMENTAL_DESC["debtToEquity"])

    rg = info.get("revenueGrowth")
    r3[1].metric("Revenue Growth", f"{rg*100:.1f}%" if rg else "—")
    r3[1].caption(FUNDAMENTAL_DESC["revenueGrowth"])

    eg = info.get("earningsGrowth")
    r3[2].metric("Earnings Growth", f"{eg*100:.1f}%" if eg else "—")
    r3[2].caption(FUNDAMENTAL_DESC["earningsGrowth"])

    beta_val = info.get("beta")
    r3[3].metric("Beta", f"{beta_val:.2f}" if beta_val else "—")
    r3[3].caption(FUNDAMENTAL_DESC["beta"])

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

        # Normalized chart
        st.divider()
        st.subheader("Normalized Performance")
        norm = pd.DataFrame({
            ticker: data["Close"] / data["Close"].iloc[0],
            benchmark: bench_data["Close"] / bench_data["Close"].iloc[0],
        })
        plot = norm.reset_index().melt(id_vars="Date", var_name="Ticker", value_name="Normalized")
        chart = (
            alt.Chart(plot).mark_line()
            .encode(x="Date:T", y=alt.Y("Normalized:Q").scale(zero=False), color="Ticker:N")
            .properties(height=350)
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.warning("Benchmark data unavailable.")

# ========================== RETURNS & VOLATILITY =============================
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

    # Rolling vol (merged from old Page 3)
    st.subheader(f"Rolling {roll_win}-Day Volatility")
    rvol = returns.rolling(roll_win).std().dropna().reset_index()
    rvol.columns = ["Date", "Rolling Vol (%)"]
    vol_area = alt.Chart(rvol).mark_area(opacity=0.25, color="#3498db").encode(x="Date:T", y="Rolling Vol (%):Q").properties(height=250)
    vol_line = alt.Chart(rvol).mark_line(color="#3498db", strokeWidth=1.5).encode(x="Date:T", y="Rolling Vol (%):Q")
    if bench_m:
        br = bench_m["daily_ret_pct"].rolling(roll_win).std().dropna().reset_index()
        br.columns = ["Date", "Rolling Vol (%)"]
        bl = alt.Chart(br).mark_line(color="#e67e22", strokeWidth=1.5, strokeDash=[6,3]).encode(x="Date:T", y="Rolling Vol (%):Q")
        st.altair_chart(vol_area + vol_line + bl, width="stretch")
        st.caption(f"Blue = {ticker}  ·  Orange dashed = {benchmark}")
    else:
        st.altair_chart(vol_area + vol_line, width="stretch")

    # Return distribution histogram
    st.divider()
    st.subheader("Return Distribution")
    st.caption("If bars extend further left than the orange curve, the stock has fatter downside tails than normal.")
    dist_df = returns.reset_index()
    dist_df.columns = ["Date", "Daily Return (%)"]
    avg, std = metrics["avg_daily"], metrics["std_daily"]

    hist = alt.Chart(dist_df).mark_bar(opacity=0.75).encode(
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
