# -*- coding: utf-8 -*-
"""
Page 4 — Portfolio Risk

Enter holdings and weights, get:
  - Portfolio-level risk/return metrics (incl. alpha/beta vs. SPY)
  - Per-holding risk contributions
  - Sector allocation breakdown
  - Diversification verdict
  - Suggested weight schemes (equal-weight, inverse-volatility)
  - Cumulative performance vs. SPY benchmark
"""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from utils.data import get_price_history, get_ticker_info
from utils.metrics import METRIC_DESC, compute_return_metrics, metric_card
from utils.watchlist import load_watchlist

st.set_page_config(
    page_title="Portfolio Risk — StockLens",
    page_icon=":material/account_balance_wallet:",
    layout="wide",
)

st.title(":material/account_balance_wallet: Portfolio Risk")
st.caption(
    "Enter your holdings and allocation weights to get portfolio-level "
    "risk metrics, sector breakdown, diversification benefit, per-stock "
    "risk contributions, and benchmark-relative stats."
)


# ---------------------------------------------------------------------------
# Pre-fill helpers — load from watchlist
# ---------------------------------------------------------------------------
if "pf_tickers" not in st.session_state:
    st.session_state["pf_tickers"] = ["AAPL", "MSFT", "GOOGL"]
    st.session_state["pf_weights"] = [40, 35, 25]

load_cols = st.columns([2, 2, 1, 1])
with load_cols[0]:
    st.markdown("**Quick-start options**")
with load_cols[1]:
    if st.button(":material/visibility: Load from Watchlist", width="stretch"):
        wl = load_watchlist()
        if not wl:
            st.toast("Your watchlist is empty.", icon="ℹ️")
        else:
            ts = [it["ticker"] for it in wl][:10]
            # Equal weight across the load
            eqw = [round(100 / len(ts), 1)] * len(ts)
            # Fix rounding drift: last item absorbs the remainder
            eqw[-1] = round(100 - sum(eqw[:-1]), 1)
            st.session_state["pf_tickers"] = ts
            st.session_state["pf_weights"] = eqw
            st.rerun()
with load_cols[2]:
    if st.button("Equal weight", width="stretch"):
        n = len(st.session_state["pf_tickers"])
        if n:
            eqw = [round(100 / n, 1)] * n
            eqw[-1] = round(100 - sum(eqw[:-1]), 1)
            st.session_state["pf_weights"] = eqw
            st.rerun()
with load_cols[3]:
    if st.button("Reset", width="stretch"):
        st.session_state["pf_tickers"] = ["AAPL", "MSFT", "GOOGL"]
        st.session_state["pf_weights"] = [40, 35, 25]
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar — portfolio input
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Portfolio holdings")
    st.caption("Enter tickers and weights (must sum to 100%).")

    current_n = len(st.session_state["pf_tickers"])
    num_holdings = st.number_input(
        "Number of holdings", min_value=2, max_value=15,
        value=max(2, current_n), step=1,
    )

    # Extend or truncate state to match num_holdings
    if int(num_holdings) > current_n:
        st.session_state["pf_tickers"].extend(
            [""] * (int(num_holdings) - current_n)
        )
        st.session_state["pf_weights"].extend(
            [0] * (int(num_holdings) - current_n)
        )
    elif int(num_holdings) < current_n:
        st.session_state["pf_tickers"] = st.session_state["pf_tickers"][: int(num_holdings)]
        st.session_state["pf_weights"] = st.session_state["pf_weights"][: int(num_holdings)]

    tickers = []
    weights = []
    for i in range(int(num_holdings)):
        c1, c2 = st.columns([2, 1])
        t = c1.text_input(
            f"Ticker {i+1}",
            value=st.session_state["pf_tickers"][i] if i < len(st.session_state["pf_tickers"]) else "",
            key=f"t_{i}",
        ).upper()
        w = c2.number_input(
            "Weight %",
            value=float(st.session_state["pf_weights"][i]) if i < len(st.session_state["pf_weights"]) else 0.0,
            min_value=0.0, max_value=100.0, step=1.0, key=f"w_{i}",
        )
        if t:
            tickers.append(t)
            weights.append(w)

    total_weight = sum(weights)
    if abs(total_weight - 100) > 0.5:
        st.warning(f"Weights sum to {total_weight:.1f}% — must equal 100%.")

    horizon_map = {
        "3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y",
        "2 Years": "2y", "5 Years": "5y",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=2)

    risk_free_rate = st.number_input(
        "Annual risk-free rate", min_value=0.0, max_value=0.20,
        value=0.05, step=0.01, format="%.2f",
    )


if abs(total_weight - 100) > 0.5 or len(tickers) < 2:
    st.info("Configure your portfolio in the sidebar (weights must sum to 100%).")
    st.stop()


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
w_arr = np.array(weights) / 100  # decimal weights
all_prices = {}
all_info = {}
errors = []

with st.spinner("Fetching price data…"):
    for t in tickers:
        hist = get_price_history(t, horizon_map[horizon])
        if hist.empty:
            errors.append(t)
        else:
            all_prices[t] = hist["Close"]
            all_info[t] = get_ticker_info(t) or {}

    # Benchmark
    spy_hist = get_price_history("SPY", horizon_map[horizon])
    spy_prices = spy_hist["Close"] if not spy_hist.empty else None


if errors:
    st.error(f"Could not fetch data for: {', '.join(errors)}. Fix tickers and try again.")
    st.stop()


price_df = pd.DataFrame(all_prices).dropna()
if len(price_df) < 20:
    st.error("Not enough overlapping price data. Try a shorter horizon or check tickers.")
    st.stop()


# ---------------------------------------------------------------------------
# Portfolio calculations
# ---------------------------------------------------------------------------
ret_df = price_df.pct_change().dropna()
port_ret = (ret_df * w_arr).sum(axis=1)
port_cumulative = (1 + port_ret).cumprod()
indiv_cum = (1 + ret_df).cumprod()

cov_annual = ret_df.cov() * 252
port_var = float(w_arr @ cov_annual.values @ w_arr)
port_vol = np.sqrt(port_var) * 100

indiv_vols = ret_df.std() * np.sqrt(252)
undiversified_vol = float((w_arr * indiv_vols.values).sum()) * 100
div_benefit = undiversified_vol - port_vol
div_ratio = div_benefit / undiversified_vol if undiversified_vol else 0.0

port_metrics = compute_return_metrics(port_cumulative, risk_free_rate)

# Marginal contribution to risk
mctr = (cov_annual.values @ w_arr) / np.sqrt(port_var) if port_var > 0 else np.zeros_like(w_arr)
ctr = w_arr * mctr
ctr_pct = (ctr / ctr.sum() * 100) if ctr.sum() else np.zeros_like(w_arr)


# Benchmark-relative stats
bench_metrics = None
alpha_ann = beta = corr_spy = None
if spy_prices is not None:
    spy_ret = spy_prices.pct_change().dropna()
    # Align lengths
    aligned = pd.concat([port_ret, spy_ret], axis=1, join="inner").dropna()
    aligned.columns = ["port", "spy"]
    if len(aligned) > 10:
        # Beta = cov(port, spy) / var(spy)
        cov_ps = aligned.cov().loc["port", "spy"]
        var_spy = aligned["spy"].var()
        beta = float(cov_ps / var_spy) if var_spy else None
        corr_spy = float(aligned.corr().loc["port", "spy"])
        # Jensen's alpha (annualized): αp = rp - (rf + β(rm - rf))
        rf_daily = (1 + risk_free_rate) ** (1 / 252) - 1
        port_excess = aligned["port"].mean() - rf_daily
        spy_excess = aligned["spy"].mean() - rf_daily
        if beta is not None:
            alpha_daily = port_excess - beta * spy_excess
            alpha_ann = alpha_daily * 252 * 100  # in pp
    bench_cumulative = (1 + spy_ret).cumprod()


# Sector allocation
sector_allocations: dict[str, float] = {}
for t, w in zip(tickers, w_arr):
    sec = all_info.get(t, {}).get("sector") or "Unknown"
    sector_allocations[sec] = sector_allocations.get(sec, 0) + float(w) * 100
sector_df = (
    pd.Series(sector_allocations, name="Weight %")
    .sort_values(ascending=False)
    .reset_index()
    .rename(columns={"index": "Sector"})
)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
tab_overview, tab_contrib, tab_sector, tab_holdings = st.tabs(
    ["Overview", "Risk Contributions", "Sector Allocation", "Individual Holdings"]
)


# ---------- OVERVIEW ----------
with tab_overview:
    st.subheader("Portfolio summary")

    r1 = st.columns(4)
    metric_card(r1[0], "Portfolio Return", f"{port_metrics['total_return']:.2f}%", "total_return")
    metric_card(r1[1], "Annualized Vol", f"{port_vol:.2f}%", "ann_vol")
    metric_card(r1[2], "Sharpe Ratio", f"{port_metrics['sharpe']:.2f}", "sharpe")
    metric_card(r1[3], "Max Drawdown", f"{port_metrics['max_drawdown']:.2f}%", "max_drawdown")

    r2 = st.columns(4)
    r2[0].metric("Undiversified Vol", f"{undiversified_vol:.2f}%")
    r2[0].caption("Sum of weighted individual vols — what you'd get at perfect correlation.")
    r2[1].metric("Diversification Benefit", f"{div_benefit:.2f}%")
    r2[1].caption(f"≈ {div_ratio * 100:.0f}% of the undiversified vol is saved by diversification.")
    metric_card(r2[2], "Sortino Ratio", f"{port_metrics['sortino']:.2f}", "sortino")
    metric_card(r2[3], "VaR (95%)", f"{port_metrics['var_95']:.2f}%", "var_95")

    # Diversification verdict
    if div_ratio >= 0.25:
        st.success(
            f":material/check_circle: **Well-diversified** — diversification removes "
            f"~{div_ratio * 100:.0f}% of the naive weighted volatility."
        )
    elif div_ratio >= 0.10:
        st.info(
            f":material/info: **Moderately diversified** — {div_ratio * 100:.0f}% vol "
            "reduction vs. perfectly correlated baseline. Consider adding names from "
            "less-correlated sectors."
        )
    else:
        st.warning(
            f":material/warning: **Concentrated** — only {div_ratio * 100:.0f}% vol "
            "reduction; your holdings move too similarly. Mix in names from other "
            "sectors or a defensive ETF."
        )

    # Benchmark panel
    if bench_metrics is None and spy_prices is not None:
        bench_metrics = compute_return_metrics(spy_prices, risk_free_rate)
    if spy_prices is not None:
        st.divider()
        st.subheader(":material/ssid_chart: vs. SPY benchmark")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric(
            "Excess return",
            f"{port_metrics['total_return'] - bench_metrics['total_return']:+.2f} pp",
            help="Portfolio total return minus SPY total return over the same horizon.",
        )
        b2.metric(
            "Beta",
            f"{beta:.2f}" if beta is not None else "—",
            help="Portfolio sensitivity to SPY. 1.0 = moves with the market; >1 = more volatile.",
        )
        b3.metric(
            "Alpha (annualized)",
            f"{alpha_ann:+.2f}%" if alpha_ann is not None else "—",
            help="Return above what CAPM would predict given your beta.",
        )
        b4.metric(
            "Correlation to SPY",
            f"{corr_spy:.2f}" if corr_spy is not None else "—",
        )

    # Cumulative chart
    st.divider()
    st.subheader("Cumulative performance")
    st.caption(
        "Solid = portfolio, dashed = individual holdings, dotted = SPY benchmark. "
        "All series start at 1.0."
    )
    cum_df = indiv_cum.copy()
    cum_df["Portfolio"] = port_cumulative
    if spy_prices is not None:
        cum_df["SPY"] = (1 + spy_prices.pct_change().dropna()).cumprod()
    cum_df = cum_df.dropna(how="all")
    plot = cum_df.reset_index().melt(
        id_vars=["Date"], var_name="Holding", value_name="Cumulative Return"
    )
    # Altair doesn't allow nested conditions on strokeDash, so we tag each row
    # with its visual "kind" and drive a categorical strokeDash scale.
    def _kind(h: str) -> str:
        if h == "Portfolio":
            return "portfolio"
        if h == "SPY":
            return "benchmark"
        return "holding"

    plot = plot.copy()
    plot["Kind"] = plot["Holding"].map(_kind)

    kind_domain = ["portfolio", "holding", "benchmark"]
    # Dash patterns: portfolio solid, individual holdings dashed, SPY dotted
    dash_range = [[1, 0], [6, 3], [2, 2]]
    size_range = [3.0, 1.5, 1.5]

    cum_chart = (
        alt.Chart(plot).mark_line()
        .encode(
            x="Date:T",
            y=alt.Y("Cumulative Return:Q").scale(zero=False),
            color=alt.Color("Holding:N"),
            strokeDash=alt.StrokeDash(
                "Kind:N",
                scale=alt.Scale(domain=kind_domain, range=dash_range),
                legend=None,
            ),
            size=alt.Size(
                "Kind:N",
                scale=alt.Scale(domain=kind_domain, range=size_range),
                legend=None,
            ),
            tooltip=[
                "Date:T", "Holding:N",
                alt.Tooltip("Cumulative Return:Q", format=".4f"),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(cum_chart, width="stretch")


# ---------- RISK CONTRIBUTIONS ----------
with tab_contrib:
    st.subheader("Risk contribution by holding")
    st.caption(
        "Shows how much of portfolio volatility each stock drives. A stock can "
        "contribute more risk than its weight if it's volatile or highly "
        "correlated with the rest."
    )

    contrib_df = pd.DataFrame({
        "Ticker": tickers,
        "Weight (%)": [w * 100 for w in w_arr],
        "Ann. Vol (%)": [float(indiv_vols[t] * 100) for t in tickers],
        "Risk Contribution (%)": ctr_pct,
    }).set_index("Ticker").round(2)

    st.dataframe(contrib_df, width="stretch")

    # Weight vs risk contribution
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
        )
        .properties(height=350)
    )
    st.altair_chart(bar_chart, width="stretch")
    st.caption(
        "If a stock's risk contribution exceeds its weight, it's a disproportionate "
        "source of portfolio volatility."
    )

    # Alternative weighting suggestions
    st.divider()
    st.subheader(":material/tune: Alternative weight schemes")

    eq_weights = [round(100 / len(tickers), 1)] * len(tickers)
    eq_weights[-1] = round(100 - sum(eq_weights[:-1]), 1)

    # Inverse-volatility weights: proportional to 1/vol, normalized
    inv_vol = 1 / np.array([float(indiv_vols[t]) for t in tickers])
    inv_vol_weights = (inv_vol / inv_vol.sum() * 100).round(1)
    inv_vol_weights[-1] = round(100 - sum(inv_vol_weights[:-1]), 1)

    suggest_df = pd.DataFrame({
        "Ticker": tickers,
        "Current (%)": [round(w * 100, 1) for w in w_arr],
        "Equal-weight (%)": eq_weights,
        "Inverse-vol (%)": inv_vol_weights,
    }).set_index("Ticker")
    st.dataframe(suggest_df, width="stretch")
    st.caption(
        "**Equal-weight** spreads risk equally by position count. **Inverse-vol** "
        "caps exposure to each name so each contributes similar standalone risk."
    )

    # Correlation matrix
    st.divider()
    st.subheader("Correlation matrix")
    corr = ret_df.corr().round(3)
    corr_tickers = list(corr.columns)
    heat = (
        corr.stack()
        .reset_index()
        .rename(columns={"level_0": "A", "level_1": "B", 0: "Corr"})
    )
    heatmap = (
        alt.Chart(heat)
        .mark_rect()
        .encode(
            x=alt.X("A:N", title=None, sort=corr_tickers),
            y=alt.Y("B:N", title=None, sort=corr_tickers),
            color=alt.Color(
                "Corr:Q",
                scale=alt.Scale(
                    domain=[-1, 0, 1],
                    range=["#2166ac", "#f7f7f7", "#b2182b"],
                ),
                legend=alt.Legend(title="Corr"),
            ),
            tooltip=["A:N", "B:N", alt.Tooltip("Corr:Q", format=".3f")],
        )
        .properties(height=max(240, 40 * len(corr_tickers)))
    )
    labels = (
        alt.Chart(heat)
        .mark_text(fontSize=12, fontWeight=600)
        .encode(
            x=alt.X("A:N", sort=corr_tickers),
            y=alt.Y("B:N", sort=corr_tickers),
            text=alt.Text("Corr:Q", format=".2f"),
            color=alt.condition(
                "abs(datum.Corr) > 0.5",
                alt.value("white"),
                alt.value("#111"),
            ),
        )
    )
    st.altair_chart(heatmap + labels, width="stretch")


# ---------- SECTOR ALLOCATION ----------
with tab_sector:
    st.subheader("Sector allocation")
    st.caption(
        "How your weights break out by sector. Concentrated sector exposure is "
        "one of the biggest drivers of correlation and drawdown risk."
    )

    alloc_chart = (
        alt.Chart(sector_df).mark_bar()
        .encode(
            x=alt.X("Weight %:Q", title="Weight (%)"),
            y=alt.Y("Sector:N", sort="-x"),
            color=alt.Color("Sector:N", legend=None),
            tooltip=["Sector:N", alt.Tooltip("Weight %:Q", format=".1f")],
        )
        .properties(height=300)
    )
    st.altair_chart(alloc_chart, width="stretch")

    st.dataframe(
        sector_df.rename(columns={"Weight %": "Weight (%)"}).set_index("Sector").round(1),
        width="stretch",
    )

    # Concentration reading
    max_sec = sector_df.iloc[0]
    if max_sec["Weight %"] >= 60:
        st.warning(
            f":material/warning: **{max_sec['Sector']}** alone is "
            f"{max_sec['Weight %']:.1f}% of the portfolio. Highly concentrated "
            "in one sector — a sector-wide shock will dominate returns."
        )
    elif max_sec["Weight %"] >= 40:
        st.info(
            f"**{max_sec['Sector']}** is your largest sector at "
            f"{max_sec['Weight %']:.1f}%. Meaningful concentration — worth "
            "monitoring the sector backdrop."
        )
    else:
        st.success(
            f":material/check_circle: No single sector dominates — largest is "
            f"**{max_sec['Sector']}** at {max_sec['Weight %']:.1f}%."
        )


# ---------- INDIVIDUAL HOLDINGS ----------
with tab_holdings:
    st.subheader("Individual holding metrics")

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
    st.dataframe(hold_df, width="stretch")

    with st.expander("What do these metrics mean?"):
        for key, desc in METRIC_DESC.items():
            st.markdown(f"**{key.replace('_', ' ').title()}:** {desc}")


# ---------------------------------------------------------------------------
# CTAs
# ---------------------------------------------------------------------------
st.divider()
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link("pages/3_Compare_Stocks.py", label="Compare these names", icon=":material/compare_arrows:")
with c2:
    st.page_link("pages/2_Stock_Analysis.py", label="Analyze a single name", icon=":material/query_stats:")
with c3:
    st.page_link("pages/5_Watchlist.py", label="Manage Watchlist", icon=":material/visibility:")
