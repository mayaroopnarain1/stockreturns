# -*- coding: utf-8 -*-
"""
Page 3 — Compare Stocks

Side-by-side comparison of 2–5 tickers with benchmark overlay:
  - Performance: normalized price (including SPY benchmark), total returns
  - Risk: standard suite of risk/return metrics, risk vs. return scatter
  - Fundamentals: relative-colored table (green = best-in-cohort)
  - Correlation: heatmap
  - Verdict: prescription-engine Buy/Hold/Avoid per ticker (quick read)
"""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from utils.data import (
    get_macro_snapshot,
    get_price_history,
    get_ticker_info,
)
from utils.metrics import (
    FUNDAMENTAL_DESC,
    METRIC_DESC,
    compute_return_metrics,
    compute_technical_signals,
)
from utils.prescription import (
    PROFILE_DESCRIPTIONS,
    generate_prescription,
)
from utils.watchlist import add_ticker as watchlist_add

st.set_page_config(
    page_title="Compare Stocks — StockLens",
    page_icon=":material/compare_arrows:",
    layout="wide",
)

st.title(":material/compare_arrows: Compare Stocks")
st.caption(
    "Pick 2–5 tickers and compare performance, risk, fundamentals, and "
    "verdicts side by side. SPY is shown as a benchmark."
)


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

    st.divider()
    show_benchmark = st.checkbox("Include SPY benchmark", value=True)
    profile = st.selectbox(
        "Investor profile (for verdicts)",
        list(PROFILE_DESCRIPTIONS.keys()),
        index=0,
    )
    st.caption(PROFILE_DESCRIPTIONS.get(profile, ""))


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
all_prices: dict[str, pd.Series] = {}
all_metrics: dict[str, dict] = {}
all_info: dict[str, dict] = {}
errors: list[str] = []

with st.spinner("Fetching data…"):
    for t in tickers:
        hist = get_price_history(t, horizon_map[horizon])
        if hist.empty:
            errors.append(t)
            continue
        all_prices[t] = hist["Close"]
        all_metrics[t] = compute_return_metrics(hist["Close"], risk_free_rate)
        all_info[t] = get_ticker_info(t) or {}

    if show_benchmark:
        spy_hist = get_price_history("SPY", horizon_map[horizon])
        if not spy_hist.empty:
            all_prices["SPY"] = spy_hist["Close"]
            all_metrics["SPY"] = compute_return_metrics(spy_hist["Close"], risk_free_rate)

    macro = get_macro_snapshot()


if errors:
    st.warning(f"Could not fetch data for: {', '.join(errors)}")

valid = [t for t in tickers if t in all_metrics]
if len(valid) < 2:
    st.error("Need at least 2 valid tickers. Check symbols and try again.")
    st.stop()


# ---------------------------------------------------------------------------
# Verdict row — compact prescription summary up top
# ---------------------------------------------------------------------------
st.subheader(":material/gavel: Verdicts (quick read)")

verdicts: dict[str, dict] = {}
for t in valid:
    info = all_info.get(t, {})
    signals = compute_technical_signals(all_prices[t])
    verdicts[t] = generate_prescription(info, signals, macro, profile=profile)

v_cols = st.columns(len(valid))
for i, t in enumerate(valid):
    v = verdicts[t]
    verdict_label = v["verdict"]
    score = v["composite_score"]
    thesis = v.get("thesis", "")
    if "Buy" in verdict_label:
        border, bg = "#16a34a", "#f0fdf4"
    elif "Hold" in verdict_label:
        border, bg = "#d97706", "#fffbeb"
    else:
        border, bg = "#dc2626", "#fef2f2"
    with v_cols[i]:
        st.markdown(
            f"""
            <div style="border:2px solid {border};background:{bg};border-radius:8px;
                        padding:12px;min-height:128px;">
              <div style="font-weight:700;font-size:18px;">{t}</div>
              <div style="font-weight:700;font-size:16px;color:{border};margin-top:2px;">
                {verdict_label}
              </div>
              <div style="font-size:12px;color:#4b5563;margin-top:4px;">
                Score: <b>{score:.0f}</b> / 100
              </div>
              <div style="font-size:11px;color:#6b7280;margin-top:6px;line-height:1.3;">
                {thesis}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.caption(f"Verdicts use the **{profile}** profile. Toggle in the sidebar to reweight.")

st.divider()


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_perf, tab_risk, tab_fund, tab_corr = st.tabs(
    ["Performance", "Risk Metrics", "Fundamentals", "Correlation"]
)


# --------------------------- PERFORMANCE -----------------------------------
with tab_perf:
    st.subheader("Normalized Price (Start = 1.0)")
    st.caption(
        "Compares cumulative performance regardless of share price. A stock "
        "at 1.2 is up 20% from the start date. SPY benchmark shown as a "
        "dashed reference line."
    )

    price_keys = list(all_prices.keys())
    price_df = pd.DataFrame(all_prices).dropna(how="all")
    if not price_df.empty:
        # Forward-fill any small gaps before normalizing
        price_df = price_df.ffill().dropna()
        norm = price_df.div(price_df.iloc[0])
        plot = norm.reset_index().melt(
            id_vars=["Date"], var_name="Ticker", value_name="Normalized Price"
        )

        # Conditional dashing: SPY dashed, everything else solid
        if "SPY" in norm.columns:
            line = (
                alt.Chart(plot).mark_line()
                .encode(
                    x="Date:T",
                    y=alt.Y("Normalized Price:Q").scale(zero=False),
                    color=alt.Color("Ticker:N"),
                    strokeDash=alt.condition(
                        alt.datum.Ticker == "SPY",
                        alt.value([6, 3]),
                        alt.value([1, 0]),
                    ),
                    tooltip=[
                        "Date:T", "Ticker:N",
                        alt.Tooltip("Normalized Price:Q", format=".4f"),
                    ],
                )
                .properties(height=400)
            )
        else:
            line = (
                alt.Chart(plot).mark_line()
                .encode(
                    x="Date:T",
                    y=alt.Y("Normalized Price:Q").scale(zero=False),
                    color="Ticker:N",
                    tooltip=[
                        "Date:T", "Ticker:N",
                        alt.Tooltip("Normalized Price:Q", format=".4f"),
                    ],
                )
                .properties(height=400)
            )
        st.altair_chart(line, width="stretch")

    # Total return comparison
    st.subheader("Total Return")
    tr_cols = st.columns(len(valid) + (1 if "SPY" in all_metrics else 0))
    for i, t in enumerate(valid + (["SPY"] if "SPY" in all_metrics else [])):
        val = all_metrics[t]["total_return"]
        color = "normal"
        tr_cols[i].metric(t, f"{val:.2f}%")
        if t == "SPY":
            tr_cols[i].caption("Benchmark")
        else:
            # Delta vs SPY if available
            if "SPY" in all_metrics:
                d = val - all_metrics["SPY"]["total_return"]
                tr_cols[i].caption(f"vs SPY: **{d:+.2f}pp**")


# --------------------------- RISK METRICS ----------------------------------
with tab_risk:
    st.subheader("Risk & Return Comparison")

    metric_cols_order = [
        "Total Return (%)", "Avg Daily Return (%)", "Std Deviation (%)",
        "Annualized Vol (%)", "Sharpe Ratio", "Sortino Ratio",
        "Max Drawdown (%)", "VaR 95% (%)", "Skewness", "Kurtosis",
    ]

    tickers_for_risk = valid + (["SPY"] if "SPY" in all_metrics else [])
    rows = {}
    for t in tickers_for_risk:
        m = all_metrics[t]
        rows[t] = {
            "Total Return (%)": round(m["total_return"], 2),
            "Avg Daily Return (%)": round(m["avg_daily"], 4),
            "Std Deviation (%)": round(m["std_daily"], 4),
            "Annualized Vol (%)": round(m["ann_vol"], 2),
            "Sharpe Ratio": round(m["sharpe"], 2),
            "Sortino Ratio": round(m["sortino"], 2),
            "Max Drawdown (%)": round(m["max_drawdown"], 2),
            "VaR 95% (%)": round(m["var_95"], 2),
            "Skewness": round(m["skewness"], 2),
            "Kurtosis": round(m["kurtosis"], 2),
        }

    comp_df = pd.DataFrame(rows).loc[metric_cols_order]
    st.dataframe(comp_df, width="stretch")

    with st.expander("What do these metrics mean?"):
        for key, desc in METRIC_DESC.items():
            st.markdown(f"**{key.replace('_', ' ').title()}:** {desc}")

    # Risk-return scatter
    st.subheader("Risk vs. Return")
    st.caption("Ideal position is upper-left: high return, low volatility.")

    scatter_data = pd.DataFrame({
        "Ticker": tickers_for_risk,
        "Annualized Vol (%)": [all_metrics[t]["ann_vol"] for t in tickers_for_risk],
        "Total Return (%)": [all_metrics[t]["total_return"] for t in tickers_for_risk],
    })
    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(size=180)
        .encode(
            x=alt.X("Annualized Vol (%):Q", title="Annualized Volatility (%)"),
            y=alt.Y("Total Return (%):Q"),
            color=alt.Color("Ticker:N"),
            tooltip=["Ticker:N", "Annualized Vol (%):Q", "Total Return (%):Q"],
        )
        .properties(height=350)
    )
    labels = scatter.mark_text(align="left", dx=10, fontSize=12, fontWeight=600).encode(text="Ticker:N")
    st.altair_chart(scatter + labels, width="stretch")


# --------------------------- FUNDAMENTALS ----------------------------------
with tab_fund:
    st.subheader("Key Fundamentals")
    st.caption(
        "Snapshot from Yahoo Finance. Best value in each row is highlighted green."
    )

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

    # Direction for "best" — lower is better on valuation/D/E, higher on quality/growth
    lower_is_better = {"P/E", "Fwd P/E", "P/B", "EV/EBITDA", "PEG", "D/E"}

    fund_rows_display: dict[str, dict] = {}
    fund_rows_raw: dict[str, dict] = {}
    for t in valid:
        info = all_info.get(t, {})
        display_row, raw_row = {}, {}
        for k, label in fund_fields.items():
            val = info.get(k)
            raw_row[label] = val
            if val is None:
                display_row[label] = "—"
            elif k == "marketCap":
                display_row[label] = f"${val / 1e9:.1f}B"
            elif k in ("dividendYield", "returnOnEquity", "profitMargins", "revenueGrowth"):
                display_row[label] = f"{val * 100:.1f}%"
            elif k == "debtToEquity":
                display_row[label] = f"{val:.0f}"
            else:
                display_row[label] = f"{val:.2f}" if isinstance(val, float) else str(val)
        fund_rows_display[t] = display_row
        fund_rows_raw[t] = raw_row

    fund_df = pd.DataFrame(fund_rows_display)
    raw_df = pd.DataFrame(fund_rows_raw)

    # Style: best-in-row gets green background
    def style_best(row: pd.Series) -> list[str]:
        label = row.name
        if label not in (set(fund_fields.values()) - {"Company", "Sector", "Market Cap"}):
            return ["" for _ in row]
        raw_vals = raw_df.loc[label] if label in raw_df.index else None
        if raw_vals is None or raw_vals.isna().all():
            return ["" for _ in row]
        numeric = pd.to_numeric(raw_vals, errors="coerce")
        if numeric.isna().all():
            return ["" for _ in row]
        if label in lower_is_better:
            best = numeric.min()
        else:
            best = numeric.max()
        return [
            "background-color: #dcfce7; font-weight: 600;"
            if (not pd.isna(v) and v == best) else ""
            for v in numeric
        ]

    try:
        styled = fund_df.style.apply(style_best, axis=1)
        st.dataframe(styled, width="stretch")
    except Exception:
        st.dataframe(fund_df, width="stretch")

    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in fund_fields:
                st.markdown(f"**{fund_fields[key]}:** {desc}")


# --------------------------- CORRELATION -----------------------------------
with tab_corr:
    st.subheader("Return Correlation Matrix")
    st.caption(
        "Measures how closely stocks move together. Values near 1 mean they "
        "move in sync; near 0 means independent; negative means they tend to "
        "move opposite. Lower correlation = better diversification potential."
    )

    corr_tickers = valid + (["SPY"] if "SPY" in all_metrics else [])
    returns_df = pd.DataFrame({t: all_metrics[t]["daily_ret_pct"] for t in corr_tickers})
    corr = returns_df.corr().round(3)

    # Render as Altair heatmap (avoids the pandas Styler jinja2 dependency
    # and looks better than a colored table).
    heat = (
        corr.stack().reset_index()
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
                scale=alt.Scale(domain=[-1, 0, 1], range=["#2166ac", "#f7f7f7", "#b2182b"]),
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

    # Quick diversification read
    # (exclude self-correlation and SPY-self)
    off_diag = []
    names = [c for c in corr.columns if c != "SPY"]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            off_diag.append(corr.loc[a, b])
    if off_diag:
        avg_corr = float(np.mean(off_diag))
        if avg_corr >= 0.8:
            st.warning(
                f":material/warning: Average pairwise correlation is **{avg_corr:.2f}** — "
                "these stocks move very similarly. Diversification benefit is limited."
            )
        elif avg_corr >= 0.6:
            st.info(
                f"Average pairwise correlation is **{avg_corr:.2f}** — "
                "moderately correlated. Some diversification benefit."
            )
        else:
            st.success(
                f":material/check_circle: Average pairwise correlation is **{avg_corr:.2f}** — "
                "well-diversified cohort."
            )


# ---------------------------------------------------------------------------
# CTAs
# ---------------------------------------------------------------------------
st.divider()
st.subheader(":material/route: Next steps")
c1, c2, c3 = st.columns(3)
with c1:
    if st.button(":material/bookmark_add: Add all to watchlist", width="stretch"):
        added, skipped = [], []
        for t in valid:
            if watchlist_add(t):
                added.append(t)
            else:
                skipped.append(t)
        if added:
            st.success(f"Added: {', '.join(added)}")
        if skipped:
            st.info(f"Already watching: {', '.join(skipped)}")
with c2:
    st.page_link("pages/4_Portfolio_Risk.py", label="Build a portfolio", icon=":material/account_balance_wallet:")
    st.caption("Enter weights and see risk contribution.")
with c3:
    st.page_link("pages/2_Stock_Analysis.py", label="Drill into a single name", icon=":material/query_stats:")
    st.caption("Full verdict + technicals + fundamentals.")
