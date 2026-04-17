# -*- coding: utf-8 -*-
"""
Page 2 — Stock Analysis

The research hub of StockLens. For a given ticker, delivers:
  - Overview: verdict, dimension cards, macro regime, key stats, CTAs
  - Fundamentals: valuation / quality / growth with peer & history context
  - Technicals: RSI, MACD, Bollinger, MAs, signal summary
  - Risk: Sharpe/Sortino/MaxDD/VaR, rolling vol, return distribution
  - Price & Events: price chart with earnings, dividends, and outlier-day overlays

The Overview tab is verdict-first: the user should understand the take in
10 seconds. Every tab has interpretations, not just numbers, and every tab
has a clear hook into another page (Compare, Portfolio Lab, Watchlist).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from datetime import date, timedelta

from utils.data import (
    get_price_history,
    get_price_history_dates,
    get_ticker_info,
    get_macro_snapshot,
    get_earnings_dates,
    get_dividends,
    get_sector_etf,
    get_sector_peers,
    fetch_fundamentals_bulk,
    get_financials,
    SP500_TICKERS,
)
from utils.financials import (
    dupont_roe,
    margin_decomposition,
    roic_analysis,
    revenue_quality,
    earnings_quality,
    accruals_analysis,
    fcf_conversion,
    leverage_liquidity,
    quality_scorecard,
)
from utils.metrics import (
    compute_return_metrics,
    compute_technical_signals,
    rsi,
    macd,
    bollinger_bands,
    moving_averages,
    detect_outlier_days,
    METRIC_DESC,
    FUNDAMENTAL_DESC,
    TECHNICAL_DESC,
    metric_card,
)
from utils.prescription import (
    generate_prescription,
    INVESTOR_PROFILES,
    PROFILE_DESCRIPTIONS,
)
from utils.watchlist import (
    add_ticker as watchlist_add,
    get_tickers as watchlist_get,
)


# ===========================================================================
# Page config
# ===========================================================================
st.set_page_config(
    page_title="Stock Analysis — StockLens",
    page_icon=":material/query_stats:",
    layout="wide",
)

st.title(":material/query_stats: Stock Analysis")
st.caption(
    "Deep-dive research for a single ticker — verdict, fundamentals, technicals, risk, and price context. "
    "Every number comes with an interpretation."
)


# ===========================================================================
# Sidebar
# ===========================================================================
with st.sidebar:
    # If we were routed from the Watchlist page, honor that pre-fill once.
    default_ticker = st.session_state.pop("analysis_ticker", "AAPL")
    ticker = st.text_input("Stock ticker", value=default_ticker).upper().strip()

    horizon_map = {
        "3 Months": "3mo",
        "6 Months": "6mo",
        "1 Year": "1y",
        "2 Years": "2y",
        "5 Years": "5y",
        "10 Years": "10y",
        "Custom range": "custom",
    }
    horizon = st.selectbox("Time horizon", list(horizon_map.keys()), index=2)

    use_custom = horizon_map[horizon] == "custom"
    custom_start = custom_end = None
    if use_custom:
        custom_start = st.date_input("Start date", value=date.today() - timedelta(days=365))
        custom_end = st.date_input("End date", value=date.today())
        if custom_start >= custom_end:
            st.error("Start date must be before end date.")
            st.stop()

    st.divider()
    st.subheader("Investor profile")
    profile = st.selectbox(
        "Style",
        list(INVESTOR_PROFILES.keys()),
        index=0,
        help="Shapes how the prescription weights valuation vs. growth vs. quality vs. macro.",
    )
    st.caption(PROFILE_DESCRIPTIONS.get(profile, ""))

    with st.expander("Settings"):
        risk_free_rate = st.number_input(
            "Annual risk-free rate", min_value=0.0, max_value=0.20,
            value=0.05, step=0.01, format="%.2f",
            help="Used for Sharpe and Sortino calculations.",
        )
        rolling_window = st.selectbox("Rolling volatility window (days)", [21, 30, 60], index=1)
        outlier_z = st.slider(
            "Outlier day threshold (|z|)", min_value=2.0, max_value=4.0, value=3.0, step=0.5,
            help="Days where |daily return z-score| exceeds this are flagged on the price chart.",
        )


# ===========================================================================
# If the Watchlist page routed the user here, pre-fill ticker
# ===========================================================================
# (The Watchlist page stashes the chosen ticker in st.session_state before
# calling st.switch_page; we don't want to override the user's own entry.)

if not ticker:
    st.info("Enter a stock ticker in the sidebar to get started.")
    st.stop()


# ===========================================================================
# Load data
# ===========================================================================

def _load_prices(symbol: str) -> pd.DataFrame:
    if use_custom:
        return get_price_history_dates(symbol, str(custom_start), str(custom_end))
    return get_price_history(symbol, horizon_map[horizon])


with st.spinner(f"Loading {ticker}…"):
    prices_df = _load_prices(ticker)
    info = get_ticker_info(ticker) or {}
    macro = get_macro_snapshot()

if prices_df.empty:
    st.error(f"No price data found for **{ticker}**. Check the ticker symbol and try again.")
    st.stop()

close = prices_df["Close"]
ret_metrics = compute_return_metrics(close, risk_free_rate)
tech_signals = compute_technical_signals(close)

prescription = generate_prescription(info, tech_signals, macro, profile=profile)


# ===========================================================================
# Hero strip — ticker, price, today's change, action buttons
# ===========================================================================
current_price = float(close.iloc[-1])
prev_price = float(close.iloc[-2]) if len(close) > 1 else current_price
day_change_pct = (current_price - prev_price) / prev_price * 100 if prev_price else 0.0
day_change_abs = current_price - prev_price

company_name = info.get("shortName") or info.get("longName") or ticker
sector = info.get("sector") or "—"
industry = info.get("industry") or "—"

week_high = info.get("fiftyTwoWeekHigh")
week_low = info.get("fiftyTwoWeekLow")
pct_of_range = None
if week_high and week_low and week_high > week_low:
    pct_of_range = (current_price - week_low) / (week_high - week_low) * 100

hero_l, hero_r = st.columns([3, 2])
with hero_l:
    st.subheader(f"{ticker} · {company_name}")
    st.caption(f"{sector} · {industry}")
    price_col, change_col = st.columns([1, 1])
    price_col.metric("Price", f"${current_price:,.2f}")
    change_col.metric(
        "Today",
        f"${day_change_abs:+,.2f}",
        f"{day_change_pct:+.2f}%",
    )
    if week_high and week_low:
        st.caption(
            f"52-week range: ${week_low:,.2f} – ${week_high:,.2f}"
            + (f"  ·  currently {pct_of_range:.0f}% of range" if pct_of_range is not None else "")
        )
        # Simple range bar via progress
        if pct_of_range is not None:
            st.progress(min(max(pct_of_range / 100, 0.0), 1.0))

with hero_r:
    st.write("")  # spacer
    btn_a, btn_b = st.columns(2)
    if btn_a.button(":material/bookmark_add: Add to Watchlist", width="stretch", key="wl_btn"):
        added = watchlist_add(ticker)
        if added:
            st.toast(f"{ticker} added to watchlist", icon="✅")
        else:
            st.toast(f"{ticker} already on watchlist", icon="ℹ️")
    if btn_b.button(":material/account_balance_wallet: Add to Portfolio", width="stretch", key="pf_btn"):
        st.toast("Jump to Portfolio Risk page to compose your portfolio.", icon="📊")
    current_watchlist = watchlist_get()
    if current_watchlist:
        st.caption(f"Watching: {', '.join(current_watchlist)}")

st.divider()


# ===========================================================================
# VERDICT CARD — the money shot
# ===========================================================================
verdict = prescription["verdict"]
confidence = prescription["confidence"]
composite = prescription["composite_score"]

verdict_color = {
    "Buy":   ("#1e8449", "🟢"),
    "Hold":  ("#b9770e", "🟡"),
    "Avoid": ("#a93226", "🔴"),
}[verdict]

vc_col, vs_col = st.columns([2, 3])

with vc_col:
    st.markdown(
        f"""
        <div style="
            border: 2px solid {verdict_color[0]};
            border-radius: 12px;
            padding: 18px 22px;
            background: {verdict_color[0]}15;
        ">
            <div style="font-size: 13px; color: #666; text-transform: uppercase; letter-spacing: 0.08em;">
                Verdict · {profile} investor
            </div>
            <div style="font-size: 42px; font-weight: 700; color: {verdict_color[0]}; line-height: 1.1;">
                {verdict_color[1]} {verdict}
            </div>
            <div style="font-size: 13px; color: #555; margin-top: 4px;">
                Confidence: <b>{confidence}</b>  ·  Composite score: <b>{composite:.0f}/100</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with vs_col:
    st.markdown(
        f"""
        <div style="
            border-radius: 12px;
            padding: 18px 22px;
            background: #f8f9fa;
            height: 100%;
            display: flex;
            align-items: center;
        ">
            <div>
                <div style="font-size: 13px; color: #666; text-transform: uppercase; letter-spacing: 0.08em;">Thesis</div>
                <div style="font-size: 16px; line-height: 1.5; margin-top: 4px;">{prescription['thesis']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


with st.expander(":material/tune: How was this verdict calculated? (click to see the math)"):
    weights = prescription["weights"]
    score_rows = [
        ("Valuation", prescription["valuation_score"], weights["valuation"], prescription["valuation_rationale"]),
        ("Quality",   prescription["quality_score"],   weights["quality"],   prescription["quality_rationale"]),
        ("Momentum",  prescription["momentum_score"],  weights["momentum"],  prescription["momentum_rationale"]),
        ("Macro",     prescription["macro_score"],     weights["macro"],     prescription["macro_rationale"]),
    ]
    st.caption(f"Weights reflect the **{profile}** profile. Each component is scored 0–100; composite is their weighted average.")
    for name, score, weight, rat in score_rows:
        c1, c2, c3 = st.columns([1, 1, 4])
        c1.metric(name, f"{score:.0f}/100")
        c2.caption(f"Weight: {weight*100:.0f}%")
        c3.markdown("  ·  ".join(rat) if rat else "—")
    st.caption(
        "Thresholds: Buy ≥ 60 · Hold 48–59 · Avoid < 48. "
        "The engine is rule-based and transparent — switch profiles in the sidebar to see the verdict adapt."
    )


st.divider()


# ===========================================================================
# Tabs
# ===========================================================================
tab_overview, tab_fund, tab_financials, tab_tech, tab_risk, tab_events = st.tabs(
    ["Overview", "Fundamentals", "Financial Analytics", "Technicals", "Risk", "Price & Events"]
)


# ========================== OVERVIEW ========================================
with tab_overview:
    st.subheader("Dimension cards")
    st.caption("Click into the dedicated tab to go deeper on any dimension.")

    dim_cols = st.columns(4)

    def _band(score: float) -> str:
        if score >= 70:
            return "Strong"
        if score >= 55:
            return "Solid"
        if score >= 45:
            return "Fair"
        if score >= 30:
            return "Weak"
        return "Poor"

    dims = [
        ("Valuation", prescription["valuation_score"], prescription["valuation_rationale"], "💰"),
        ("Quality",   prescription["quality_score"],   prescription["quality_rationale"],   "⚙️"),
        ("Momentum",  prescription["momentum_score"],  prescription["momentum_rationale"],  "📈"),
        ("Risk/Macro",prescription["macro_score"],     prescription["macro_rationale"],     "🌐"),
    ]
    for col, (name, score, rat, emoji) in zip(dim_cols, dims):
        label = _band(score)
        col.metric(f"{emoji} {name}", label, f"{score:.0f}/100")
        col.caption(" · ".join(rat[:2]) if rat else "—")

    st.divider()

    # ---- Macro regime strip ----
    st.subheader("Macro regime")
    st.caption("The backdrop against which any single-stock thesis plays out.")

    mcol1, mcol2, mcol3 = st.columns(3)
    vix = macro.get("^VIX", {})
    tnx = macro.get("^TNX", {})
    spy = macro.get("SPY", {})

    if vix.get("current") is not None:
        vix_v = vix["current"]
        vix_label = "Calm" if vix_v < 15 else "Elevated" if vix_v > 25 else "Moderate"
        mcol1.metric(f"VIX — {vix_label}", f"{vix_v:.1f}", f"{vix.get('change_pct', 0):+.1f}% 1d")
        mcol1.caption("Fear gauge. Low = risk-on market, high = fearful.")
    else:
        mcol1.metric("VIX", "—")

    if tnx.get("current") is not None:
        tnx_v = tnx["current"]
        tnx_label = "Accommodative" if tnx_v < 3 else "Restrictive" if tnx_v > 5 else "Neutral"
        mcol2.metric(f"10Y Treasury — {tnx_label}", f"{tnx_v:.2f}%", f"{tnx.get('change_pct', 0):+.2f}% 1d")
        mcol2.caption("Rising yields = headwind for growth stocks; falling = tailwind.")
    else:
        mcol2.metric("10Y Treasury", "—")

    if spy.get("current") is not None:
        spy_v = spy["current"]
        mcol3.metric("SPY", f"${spy_v:,.2f}", f"{spy.get('change_pct', 0):+.2f}% 1d")
        mcol3.caption("Broad market reference. Individual stock moves are best read vs. this.")
    else:
        mcol3.metric("SPY", "—")

    st.divider()

    # ---- Key stats grid ----
    st.subheader("Key stats")

    k1 = st.columns(4)
    mkt_cap = info.get("marketCap")
    k1[0].metric("Market cap", f"${mkt_cap/1e9:,.1f}B" if mkt_cap else "—")
    k1[1].metric("Beta", f"{info.get('beta'):.2f}" if info.get("beta") is not None else "—")
    div_yield = info.get("dividendYield")
    k1[2].metric("Dividend yield", f"{div_yield*100:.2f}%" if div_yield else "0.00%")
    k1[3].metric("Forward P/E", f"{info.get('forwardPE'):.1f}" if info.get("forwardPE") else "—")

    k2 = st.columns(4)
    pe = info.get("trailingPE")
    k2[0].metric("P/E (TTM)", f"{pe:.1f}" if pe else "—")
    roe = info.get("returnOnEquity")
    k2[1].metric("ROE", f"{roe*100:.1f}%" if roe is not None else "—")
    rev_g = info.get("revenueGrowth")
    k2[2].metric("Revenue growth", f"{rev_g*100:.1f}%" if rev_g is not None else "—")
    k2[3].metric("Total return (period)", f"{ret_metrics['total_return']:+.2f}%")

    # ---- Next steps ----
    st.divider()
    st.subheader("Next steps")
    ns_cols = st.columns(4)
    ns_cols[0].markdown("**Dig into fundamentals →** See valuation and quality with peer context.")
    ns_cols[1].markdown("**Check technicals →** Is momentum for you or against you?")
    ns_cols[2].markdown("**Compare head-to-head →** Open the Compare Stocks page to stack this against peers.")
    ns_cols[3].markdown("**Build with this →** Test portfolio impact in Portfolio Risk.")


# ========================== FUNDAMENTALS ====================================
with tab_fund:
    st.subheader("Fundamentals")
    st.caption("Each metric shown against the stock's sector median (where available) and the full-universe distribution.")

    # Check whether the sector percentile context is available (i.e. screener cache)
    show_peer_context = st.toggle(
        "Show sector & universe percentile context",
        value=False,
        help="Triggers a bulk fetch of S&P 500 fundamentals (first load ~3–8 minutes; then cached 12 hours). "
             "Uncheck to see raw fundamentals only.",
    )

    universe_df = pd.DataFrame()
    if show_peer_context:
        with st.spinner("Fetching S&P 500 fundamentals for peer context — this may take a few minutes on first load…"):
            universe_df = fetch_fundamentals_bulk(SP500_TICKERS)

    # --- Valuation section ---
    st.markdown("#### Valuation")
    st.caption("Is the stock cheap, fair, or expensive — by peer comparison and by its own history?")

    val_fields = [
        ("trailingPE",         "P/E (TTM)",   "lower"),
        ("forwardPE",          "Fwd P/E",     "lower"),
        ("priceToBook",        "P/B",         "lower"),
        ("enterpriseToEbitda", "EV/EBITDA",   "lower"),
        ("pegRatio",           "PEG",         "lower"),
        ("priceToSalesTrailing12Months", "P/S", "lower"),
    ]
    vcols = st.columns(3)
    for i, (key, label, direction) in enumerate(val_fields):
        val = info.get(key)
        with vcols[i % 3]:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                st.metric(label, "—")
            else:
                display = f"{val:.2f}"
                delta_text = None
                if show_peer_context and not universe_df.empty and key in universe_df.columns:
                    sector_df = universe_df[universe_df.get("sector") == sector]
                    if not sector_df.empty:
                        sector_median = sector_df[key].median()
                        if pd.notna(sector_median) and sector_median != 0:
                            pct_diff = (val - sector_median) / sector_median * 100
                            # For "lower=better" metrics, being below sector is good (negative delta = green)
                            delta_text = f"{pct_diff:+.1f}% vs sector (median {sector_median:.2f})"
                st.metric(label, display, delta_text, delta_color="inverse" if direction == "lower" else "normal")
                st.caption(FUNDAMENTAL_DESC.get(key, ""))

    # --- Quality ---
    st.markdown("#### Quality")
    st.caption("Is this a fundamentally healthy business?")

    q_fields = [
        ("returnOnEquity",  "ROE",              "higher", True),
        ("returnOnAssets",  "ROA",              "higher", True),
        ("profitMargins",   "Profit margin",    "higher", True),
        ("operatingMargins","Operating margin", "higher", True),
        ("debtToEquity",    "D/E",              "lower",  False),
        ("currentRatio",    "Current ratio",    "higher", False),
    ]
    qcols = st.columns(3)
    for i, (key, label, direction, is_pct) in enumerate(q_fields):
        val = info.get(key)
        with qcols[i % 3]:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                st.metric(label, "—")
            else:
                display = f"{val*100:.1f}%" if is_pct else f"{val:.2f}"
                delta_text = None
                if show_peer_context and not universe_df.empty and key in universe_df.columns:
                    sector_df = universe_df[universe_df.get("sector") == sector]
                    if not sector_df.empty:
                        sector_median = sector_df[key].median()
                        if pd.notna(sector_median):
                            if is_pct:
                                diff = (val - sector_median) * 100
                                delta_text = f"{diff:+.1f}pp vs sector"
                            else:
                                if sector_median != 0:
                                    pct_diff = (val - sector_median) / sector_median * 100
                                    delta_text = f"{pct_diff:+.1f}% vs sector"
                st.metric(
                    label, display, delta_text,
                    delta_color="normal" if direction == "higher" else "inverse",
                )
                st.caption(FUNDAMENTAL_DESC.get(key, ""))

    # --- Growth ---
    st.markdown("#### Growth")
    gcols = st.columns(3)
    g_fields = [
        ("revenueGrowth",  "Revenue growth"),
        ("earningsGrowth", "Earnings growth"),
    ]
    for i, (key, label) in enumerate(g_fields):
        val = info.get(key)
        with gcols[i]:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                st.metric(label, "—")
            else:
                st.metric(label, f"{val*100:+.1f}%")
                st.caption(FUNDAMENTAL_DESC.get(key, ""))
    fcf = info.get("freeCashflow")
    with gcols[2]:
        st.metric("Free cash flow", f"${fcf/1e9:,.2f}B" if fcf else "—")
        st.caption("Cash left after operating and capex — the fuel for dividends, buybacks, and investment.")

    # --- Percentile strip (if peer context on) ---
    if show_peer_context and not universe_df.empty:
        st.divider()
        st.markdown("#### Sector percentile ranking")
        st.caption(f"Where {ticker} sits within the {sector} sector across each metric (higher = better).")

        sector_df = universe_df[universe_df.get("sector") == sector].copy()
        if not sector_df.empty and ticker in sector_df.index:
            pct_rows = []
            percentile_metrics = {
                "trailingPE": ("P/E",         True),   # reverse: lower is better
                "priceToBook":("P/B",         True),
                "enterpriseToEbitda":("EV/EBITDA", True),
                "returnOnEquity":("ROE",      False),
                "profitMargins":("Margin",    False),
                "revenueGrowth":("Rev growth",False),
            }
            for key, (lbl, reverse) in percentile_metrics.items():
                if key in sector_df.columns and pd.notna(sector_df.loc[ticker, key]):
                    series = sector_df[key].dropna()
                    if len(series) > 1:
                        rank = series.rank(pct=True, ascending=not reverse)
                        if ticker in rank.index:
                            pct = rank.loc[ticker] * 100
                            pct_rows.append({"Metric": lbl, "Percentile": pct})
            if pct_rows:
                pct_df = pd.DataFrame(pct_rows)
                bar = (
                    alt.Chart(pct_df).mark_bar()
                    .encode(
                        x=alt.X("Percentile:Q", scale=alt.Scale(domain=[0, 100]), title="Sector percentile (100 = best in sector)"),
                        y=alt.Y("Metric:N", sort="-x"),
                        color=alt.Color(
                            "Percentile:Q",
                            scale=alt.Scale(scheme="redyellowgreen"),
                            legend=None,
                        ),
                        tooltip=["Metric:N", alt.Tooltip("Percentile:Q", format=".0f")],
                    ).properties(height=240)
                )
                st.altair_chart(bar, width="stretch")

        # Peer picks CTA
        peers = get_sector_peers(ticker, sector, universe_df, n=4)
        if peers:
            st.caption(f"Top {sector} peers by market cap: {', '.join(peers)}")
            st.info(
                f"**Compare head-to-head →** Open *Compare Stocks* with `{ticker}, {', '.join(peers)}` "
                "to stack fundamentals and returns side-by-side.",
                icon=":material/compare_arrows:",
            )
    else:
        st.info(
            "Enable **sector & universe percentile context** above to see how this stock ranks against its sector. "
            "(First load is slow; results cache for 12 hours.)",
            icon=":material/insights:",
        )


# ========================== FINANCIAL ANALYTICS =============================
with tab_financials:
    st.subheader("Financial Analytics")
    st.caption(
        "Analyses derived from the income statement, balance sheet, and cash flow "
        "statement. Each returns a trend across periods plus a one-line interpretation."
    )

    fin_freq_label = st.radio(
        "Period",
        ["Annual (4y)", "Quarterly (8q)"],
        horizontal=True,
        key="fin_freq",
    )
    fin_freq = "annual" if fin_freq_label.startswith("Annual") else "quarterly"

    with st.spinner("Loading financial statements…"):
        stmts = get_financials(ticker, freq=fin_freq)

    if all(stmts[k].empty for k in ("income", "balance", "cashflow")):
        st.warning(
            "No financial statements available for this ticker. "
            "Coverage is spotty for non-US stocks and some small caps."
        )
    else:
        # Compute analyses once — they share inputs.
        an_dupont   = dupont_roe(stmts)
        an_margins  = margin_decomposition(stmts)
        an_roic     = roic_analysis(stmts)
        an_revq     = revenue_quality(stmts)
        an_eq       = earnings_quality(stmts)
        an_accruals = accruals_analysis(stmts)
        an_fcf      = fcf_conversion(stmts)
        an_lev      = leverage_liquidity(stmts)
        scorecard   = quality_scorecard(
            an_dupont, an_margins, an_roic, an_eq, an_accruals, an_fcf, an_lev,
        )

        # ---------------- Quality Scorecard banner ----------------
        pillar_colors = {"Strong": "#1e8449", "Solid": "#2e86c1",
                         "Fair": "#b9770e", "Weak": "#a93226", "—": "#7f8c8d"}
        pillars = [
            ("Profitability",    scorecard["profitability"]),
            ("Earnings Quality", scorecard["earnings_quality"]),
            ("Balance Sheet",    scorecard["balance_sheet"]),
        ]
        sc_cols = st.columns(3)
        for col, (name, data) in zip(sc_cols, pillars):
            score = data["score"]
            label = data["label"]
            color = pillar_colors[label]
            score_txt = f"{score:.0f}/100" if pd.notna(score) else "—"
            col.markdown(
                f"""
                <div style="
                    border: 2px solid {color};
                    border-radius: 10px;
                    padding: 12px 16px;
                    background: {color}15;
                ">
                    <div style="font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.06em;">
                        {name}
                    </div>
                    <div style="font-size: 26px; font-weight: 700; color: {color}; line-height: 1.1;">
                        {label}
                    </div>
                    <div style="font-size: 13px; color: #555; margin-top: 2px;">
                        Score: <b>{score_txt}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        # ---------------- Helpers for rendering ----------------
        def _fmt_pct(v, digits=1):
            return f"{v*100:.{digits}f}%" if pd.notna(v) else "—"

        def _fmt_num(v, digits=2):
            return f"{v:.{digits}f}" if pd.notna(v) else "—"

        def _fmt_money(v):
            if pd.isna(v):
                return "—"
            a = abs(v)
            if a >= 1e9:
                return f"${v/1e9:,.2f}B"
            if a >= 1e6:
                return f"${v/1e6:,.1f}M"
            return f"${v:,.0f}"

        def _render_df(df: pd.DataFrame, formatters: dict[str, callable]):
            if df.empty:
                st.caption("—")
                return
            disp = df.copy()
            for row, fn in formatters.items():
                if row in disp.index:
                    disp.loc[row] = disp.loc[row].apply(fn)
            # Any rows without a formatter fall back to number formatting
            for row in disp.index:
                if row not in formatters:
                    disp.loc[row] = disp.loc[row].apply(lambda v: _fmt_num(v))
            st.dataframe(disp, width="stretch")

        # =============== Section A — Profitability Architecture ===============
        st.markdown("### Profitability Architecture")

        # ---- 1. DuPont ROE ----
        st.markdown("#### 1. DuPont ROE decomposition")
        st.caption(
            "ROE = Net Margin × Asset Turnover × Equity Multiplier. "
            "Shows whether returns come from pricing power, efficient asset use, or leverage."
        )
        _render_df(an_dupont["df"], {
            "Net Margin":        _fmt_pct,
            "Asset Turnover":    lambda v: _fmt_num(v, 2),
            "Equity Multiplier": lambda v: _fmt_num(v, 2),
            "ROE":               _fmt_pct,
        })
        latest_roe = an_dupont["latest_roe"]
        if pd.notna(latest_roe):
            st.caption(
                f"Latest ROE **{_fmt_pct(latest_roe)}** — primary driver: **{an_dupont['driver']}**."
            )

        # ---- 2. Margin decomposition ----
        st.markdown("#### 2. Margin decomposition")
        st.caption("Where profit leaks as revenue moves from top-line to bottom-line.")
        _render_df(an_margins["df"], {
            "Gross margin":     _fmt_pct,
            "Operating margin": _fmt_pct,
            "Pretax margin":    _fmt_pct,
            "Net margin":       _fmt_pct,
        })

        margins_df = an_margins["df"]
        if not margins_df.empty:
            mlong = margins_df.T.reset_index().melt(
                id_vars="index", var_name="Stage", value_name="Margin"
            ).rename(columns={"index": "Period"}).dropna()
            stage_order = ["Gross margin", "Operating margin", "Pretax margin", "Net margin"]
            margin_chart = (
                alt.Chart(mlong).mark_line(point=True)
                .encode(
                    x=alt.X("Period:N", title=None),
                    y=alt.Y("Margin:Q", axis=alt.Axis(format="%")),
                    color=alt.Color("Stage:N", sort=stage_order),
                    tooltip=["Period:N", "Stage:N", alt.Tooltip("Margin:Q", format=".2%")],
                ).properties(height=260)
            )
            st.altair_chart(margin_chart, width="stretch")
        if an_margins["biggest_leak"] != "—":
            st.caption(f"Biggest margin drop in latest period: **{an_margins['biggest_leak']}**.")

        # ---- 3. ROIC ----
        st.markdown("#### 3. ROIC (indirect NOPAT)")
        st.caption(
            "NOPAT = (NI + Tax + Interest − NonOpIncome) × (1 − tax rate). "
            "ROIC = NOPAT / avg (Debt + Equity − Cash)."
        )
        _render_df(an_roic["df"], {
            "NOPAT":              _fmt_money,
            "Invested Capital":   _fmt_money,
            "Effective tax rate": _fmt_pct,
            "ROIC":               _fmt_pct,
        })
        if pd.notna(an_roic["latest_roic"]):
            verdict = "**creates value**" if an_roic["creates_value"] else "**destroys value**"
            st.caption(
                f"Latest ROIC **{_fmt_pct(an_roic['latest_roic'])}** vs "
                f"WACC proxy {_fmt_pct(an_roic['wacc_proxy'], 0)} — {verdict}."
            )

        st.divider()

        # =============== Section B — Earnings Quality ===============
        st.markdown("### Earnings Quality")

        # ---- 4. Revenue quality ----
        st.markdown("#### 4. Revenue quality")
        st.caption(
            "Growth pace and whether rising revenue is collected as cash "
            "(AR growing faster than revenue = receivables building up)."
        )
        _render_df(an_revq["df"], {
            "Revenue":      _fmt_money,
            "Revenue YoY":  _fmt_pct,
            "AR / Revenue": _fmt_pct,
            "AR YoY":       _fmt_pct,
        })
        rq_bits = []
        if pd.notna(an_revq["cagr_3y"]):
            rq_bits.append(f"3y revenue CAGR: **{_fmt_pct(an_revq['cagr_3y'])}**")
        if pd.notna(an_revq["latest_yoy"]):
            rq_bits.append(f"latest YoY: **{_fmt_pct(an_revq['latest_yoy'])}**")
        if an_revq["ar_outpacing_revenue"]:
            rq_bits.append(":red[⚠ AR is growing >10pp faster than revenue — watch collections]")
        if rq_bits:
            st.caption(" · ".join(rq_bits))

        # ---- 5. Earnings quality (NI vs OCF) ----
        st.markdown("#### 5. Earnings quality — NI vs OCF divergence")
        st.caption(
            "Cash flow should track reported earnings. Persistent gaps suggest aggressive "
            "accrual accounting or working-capital drag."
        )
        eq_df = an_eq["df"]
        _render_df(eq_df, {
            "Net Income":          _fmt_money,
            "Operating Cash Flow": _fmt_money,
            "(OCF − NI) / |NI|":   _fmt_pct,
            "Effective tax rate":  _fmt_pct,
        })

        if not eq_df.empty and {"Net Income", "Operating Cash Flow"}.issubset(eq_df.index):
            ni_ocf = eq_df.loc[["Net Income", "Operating Cash Flow"]].T.reset_index()
            ni_ocf.columns = ["Period", "Net Income", "Operating Cash Flow"]
            ni_ocf_long = ni_ocf.melt(id_vars="Period", var_name="Series", value_name="Value").dropna()
            ni_ocf_chart = (
                alt.Chart(ni_ocf_long).mark_line(point=True)
                .encode(
                    x=alt.X("Period:N", title=None),
                    y=alt.Y("Value:Q", title="$"),
                    color=alt.Color("Series:N", scale=alt.Scale(
                        domain=["Net Income", "Operating Cash Flow"],
                        range=["#e67e22", "#2980b9"],
                    )),
                    tooltip=["Period:N", "Series:N", alt.Tooltip("Value:Q", format="$,.0f")],
                ).properties(height=260)
            )
            st.altair_chart(ni_ocf_chart, width="stretch")

        eq_bits = []
        if pd.notna(an_eq["latest_gap"]):
            eq_bits.append(f"Latest OCF−NI gap: **{_fmt_pct(an_eq['latest_gap'])}**")
        if an_eq["tax_unstable"]:
            eq_bits.append(f":orange[Effective tax rate volatile (σ={_fmt_pct(an_eq['tax_std'])})]")
        if eq_bits:
            st.caption(" · ".join(eq_bits))

        # ---- 6. Accruals ----
        st.markdown("#### 6. Accruals (Sloan ratio)")
        st.caption(
            "(NI − OCF) / avg Assets. Lower is better — high accruals historically "
            "predict weaker future returns (Sloan 1996)."
        )
        _render_df(an_accruals["df"], {"Sloan accrual ratio": _fmt_pct})
        if pd.notna(an_accruals["latest"]):
            band_color = {"Clean": "#1e8449", "Watch": "#b9770e", "Red flag": "#a93226"}.get(
                an_accruals["band"], "#7f8c8d"
            )
            st.markdown(
                f"Latest: **{_fmt_pct(an_accruals['latest'])}** · "
                f"<span style='color:{band_color};font-weight:600'>{an_accruals['band']}</span> "
                "(&lt; 5% clean · 5–10% watch · &gt; 10% red flag)",
                unsafe_allow_html=True,
            )

        # ---- 7. FCF conversion ----
        st.markdown("#### 7. FCF conversion")
        st.caption(
            "Free Cash Flow / Net Income. >100% means every dollar of earnings "
            "becomes a dollar of cash (and more); <70% sustained is a concern."
        )
        _render_df(an_fcf["df"], {
            "Net Income": _fmt_money,
            "FCF":        _fmt_money,
            "FCF / NI":   _fmt_pct,
        })
        fcf_df = an_fcf["df"]
        if not fcf_df.empty and "FCF / NI" in fcf_df.index:
            conv = fcf_df.loc["FCF / NI"].reset_index()
            conv.columns = ["Period", "FCF / NI"]
            conv = conv.dropna()
            if not conv.empty:
                conv_chart = (
                    alt.Chart(conv).mark_bar()
                    .encode(
                        x=alt.X("Period:N", title=None),
                        y=alt.Y("FCF / NI:Q", axis=alt.Axis(format="%")),
                        color=alt.condition(
                            alt.datum["FCF / NI"] >= 0.7,
                            alt.value("#27ae60"), alt.value("#e67e22"),
                        ),
                        tooltip=["Period:N", alt.Tooltip("FCF / NI:Q", format=".1%")],
                    ).properties(height=220)
                )
                st.altair_chart(conv_chart, width="stretch")

        st.divider()

        # =============== Section C — Capital Structure ===============
        st.markdown("### Capital Structure")

        # ---- 8. Leverage & liquidity ----
        st.markdown("#### 8. Leverage & liquidity (latest period)")
        st.caption("How much debt is on the balance sheet, and how easily can near-term obligations be met.")

        band_colors = {"good": "#1e8449", "fair": "#b9770e", "poor": "#a93226", "—": "#7f8c8d"}
        lev_metrics = an_lev["metrics"]
        lev_bands = an_lev["bands"]

        lev_order = [
            ("Debt / Equity",      lambda v: _fmt_num(v, 2)),
            ("Debt / Assets",      lambda v: _fmt_num(v, 2)),
            ("Net Debt / EBITDA",  lambda v: _fmt_num(v, 2)),
            ("Interest Coverage",  lambda v: _fmt_num(v, 1) + "×" if pd.notna(v) else "—"),
            ("Current Ratio",      lambda v: _fmt_num(v, 2)),
            ("Quick Ratio",        lambda v: _fmt_num(v, 2)),
            ("Cash Ratio",         lambda v: _fmt_num(v, 2)),
        ]
        lc1 = st.columns(4)
        lc2 = st.columns(4)
        for i, (name, fmt) in enumerate(lev_order):
            col = lc1[i] if i < 4 else lc2[i - 4]
            v = lev_metrics.get(name)
            band = lev_bands.get(name, "—")
            color = band_colors[band]
            col.markdown(
                f"""
                <div style="
                    border-left: 4px solid {color};
                    border-radius: 6px;
                    padding: 8px 12px;
                    background: #f8f9fa;
                    margin-bottom: 6px;
                ">
                    <div style="font-size: 11px; color: #666;">{name}</div>
                    <div style="font-size: 20px; font-weight: 700;">{fmt(v)}</div>
                    <div style="font-size: 11px; color: {color}; text-transform: uppercase;">{band}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption(
            "Bands are rough large-cap heuristics, not industry-specific. "
            "Banks, utilities, and REITs warrant sector-adjusted thresholds."
        )


# ========================== TECHNICALS ======================================
with tab_tech:
    st.subheader("Technical signals")

    if tech_signals.get("direction") == "Insufficient data":
        st.warning("Not enough price history for reliable technical signals. Try a longer time horizon.")
    else:
        direction = tech_signals["direction"]
        strength = tech_signals["strength"]
        dir_color = {"Bullish": "#1e8449", "Bearish": "#a93226", "Neutral": "#7f8c8d"}[direction]
        dir_emoji = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}[direction]

        # Summary banner
        st.markdown(
            f"""
            <div style="
                border: 2px solid {dir_color};
                border-radius: 10px;
                padding: 14px 18px;
                background: {dir_color}15;
                margin-bottom: 12px;
            ">
              <div style="font-size: 14px; color: #666; text-transform: uppercase;">Technical read</div>
              <div style="font-size: 28px; font-weight: 700; color: {dir_color};">{dir_emoji} {direction} · strength {strength:.0f}/100</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Signal table
        sig_rows = [
            {"Signal": name, "Direction": d, "Interpretation": text}
            for name, d, text in tech_signals.get("signals", [])
        ]
        if sig_rows:
            st.dataframe(pd.DataFrame(sig_rows), width="stretch", hide_index=True)

        st.divider()

        # --- Price + MA overlay chart ---
        st.markdown("#### Price with moving averages")
        mas = moving_averages(close, windows=(20, 50, 200))
        ma_df = pd.DataFrame({
            "Price": close,
            "MA20":  mas[20],
            "MA50":  mas[50],
            "MA200": mas[200],
        }).reset_index()
        ma_long = ma_df.melt(id_vars=["Date"], var_name="Series", value_name="Value").dropna()

        color_scale = alt.Scale(
            domain=["Price", "MA20", "MA50", "MA200"],
            range=["#2c3e50", "#3498db", "#e67e22", "#c0392b"],
        )
        price_chart = (
            alt.Chart(ma_long).mark_line()
            .encode(
                x="Date:T",
                y=alt.Y("Value:Q").scale(zero=False),
                color=alt.Color("Series:N", scale=color_scale),
                strokeDash=alt.condition(
                    alt.datum.Series == "Price",
                    alt.value([1, 0]),
                    alt.value([5, 3]),
                ),
                tooltip=["Date:T", "Series:N", alt.Tooltip("Value:Q", format="$.2f")],
            ).properties(height=350)
        )
        st.altair_chart(price_chart, width="stretch")
        st.caption(
            f"MA20 ${tech_signals.get('ma20') or 0:,.2f}  ·  "
            f"MA50 ${tech_signals.get('ma50') or 0:,.2f}  ·  "
            f"MA200 ${tech_signals.get('ma200') or 0:,.2f}"
        )

        # --- RSI ---
        st.markdown("#### RSI (14)")
        rsi_series = rsi(close).dropna()
        rsi_df = rsi_series.reset_index()
        rsi_df.columns = ["Date", "RSI"]
        rsi_line = (
            alt.Chart(rsi_df).mark_line(color="#8e44ad")
            .encode(x="Date:T", y=alt.Y("RSI:Q", scale=alt.Scale(domain=[0, 100])),
                    tooltip=["Date:T", alt.Tooltip("RSI:Q", format=".1f")])
            .properties(height=200)
        )
        ob_line = alt.Chart(pd.DataFrame({"y": [70]})).mark_rule(color="#e74c3c", strokeDash=[4, 4]).encode(y="y:Q")
        os_line = alt.Chart(pd.DataFrame({"y": [30]})).mark_rule(color="#27ae60", strokeDash=[4, 4]).encode(y="y:Q")
        st.altair_chart(rsi_line + ob_line + os_line, width="stretch")
        st.caption("Above 70 = overbought (red line); below 30 = oversold (green line).")

        # --- MACD ---
        st.markdown("#### MACD (12, 26, 9)")
        macd_line, signal_line, hist = macd(close)
        macd_df = pd.DataFrame({
            "MACD": macd_line, "Signal": signal_line, "Histogram": hist,
        }).reset_index()
        macd_long = macd_df[["Date", "MACD", "Signal"]].melt(
            id_vars=["Date"], var_name="Series", value_name="Value"
        ).dropna()
        macd_chart = (
            alt.Chart(macd_long).mark_line()
            .encode(
                x="Date:T",
                y="Value:Q",
                color=alt.Color("Series:N", scale=alt.Scale(
                    domain=["MACD", "Signal"], range=["#2980b9", "#e67e22"]
                )),
                tooltip=["Date:T", "Series:N", alt.Tooltip("Value:Q", format=".3f")],
            ).properties(height=200)
        )
        hist_df = macd_df[["Date", "Histogram"]].dropna()
        hist_bar = (
            alt.Chart(hist_df).mark_bar(opacity=0.5)
            .encode(
                x="Date:T", y="Histogram:Q",
                color=alt.condition(
                    alt.datum.Histogram > 0, alt.value("#27ae60"), alt.value("#c0392b"),
                ),
                tooltip=["Date:T", alt.Tooltip("Histogram:Q", format=".3f")],
            ).properties(height=150)
        )
        st.altair_chart(macd_chart, width="stretch")
        st.altair_chart(hist_bar, width="stretch")
        st.caption("MACD above signal line (blue above orange) = bullish momentum; histogram shows the distance.")

        # --- Bollinger Bands ---
        st.markdown("#### Bollinger Bands (20, 2σ)")
        upper, mid, lower = bollinger_bands(close)
        bb_df = pd.DataFrame({
            "Price": close, "Upper": upper, "Middle": mid, "Lower": lower,
        }).reset_index()
        bb_long = bb_df.melt(id_vars=["Date"], var_name="Band", value_name="Value").dropna()
        bb_chart = (
            alt.Chart(bb_long).mark_line()
            .encode(
                x="Date:T",
                y=alt.Y("Value:Q").scale(zero=False),
                color=alt.Color("Band:N", scale=alt.Scale(
                    domain=["Price", "Upper", "Middle", "Lower"],
                    range=["#2c3e50", "#e74c3c", "#95a5a6", "#27ae60"],
                )),
                strokeDash=alt.condition(
                    alt.datum.Band == "Price", alt.value([1, 0]), alt.value([4, 4])
                ),
                tooltip=["Date:T", "Band:N", alt.Tooltip("Value:Q", format="$.2f")],
            ).properties(height=300)
        )
        st.altair_chart(bb_chart, width="stretch")
        bb_pos = tech_signals.get("bb_position")
        if bb_pos is not None:
            bb_label = "at upper band — stretched" if bb_pos > 0.9 else "at lower band — compressed" if bb_pos < 0.1 else f"{bb_pos*100:.0f}% of band range — normal"
            st.caption(f"Current position: {bb_label}.")

        with st.expander("What do these indicators mean?"):
            for key, desc in TECHNICAL_DESC.items():
                st.markdown(f"**{key.upper().replace('_', ' ')}:** {desc}")


# ========================== RISK ============================================
with tab_risk:
    st.subheader("Risk & returns")
    st.caption("Ported from the prior Returns & Volatility analysis — now part of the unified Stock Analysis page.")

    # Row 1
    r1 = st.columns(4)
    metric_card(r1[0], "Trading days", str(ret_metrics["trading_days"]), "trading_days")
    metric_card(r1[1], "Total return", f"{ret_metrics['total_return']:+.2f}%", "total_return")
    metric_card(r1[2], "Avg daily return", f"{ret_metrics['avg_daily']:.4f}%", "avg_daily")
    metric_card(r1[3], "Annualised vol", f"{ret_metrics['ann_vol']:.2f}%", "ann_vol")

    # Row 2
    r2 = st.columns(4)
    metric_card(r2[0], "Sharpe", f"{ret_metrics['sharpe']:.2f}", "sharpe")
    metric_card(r2[1], "Sortino", f"{ret_metrics['sortino']:.2f}", "sortino")
    metric_card(r2[2], "Max drawdown", f"{ret_metrics['max_drawdown']:.2f}%", "max_drawdown")
    metric_card(r2[3], "VaR (95%)", f"{ret_metrics['var_95']:.2f}%", "var_95")

    # Row 3 — distributional shape
    r3 = st.columns(4)
    metric_card(r3[0], "Skewness", f"{ret_metrics['skewness']:.2f}", "skewness")
    metric_card(r3[1], "Kurtosis", f"{ret_metrics['kurtosis']:.2f}", "kurtosis")
    metric_card(r3[2], "Std (daily)", f"{ret_metrics['std_daily']:.4f}%", "std_daily")

    st.divider()

    # --- Rolling volatility chart ---
    st.markdown(f"#### Rolling {rolling_window}-day volatility")
    st.caption("Spikes highlight regime changes — earnings surprises, macro shocks, or broad market stress.")
    returns_pct = ret_metrics["daily_ret_pct"]
    rvol = returns_pct.rolling(window=rolling_window).std().dropna()
    rvol_df = rvol.reset_index()
    rvol_df.columns = ["Date", "Rolling std dev (%)"]
    vol_chart = (
        alt.Chart(rvol_df).mark_area(opacity=0.25, color="#3498db")
        .encode(x="Date:T", y="Rolling std dev (%):Q",
                tooltip=["Date:T", alt.Tooltip("Rolling std dev (%):Q", format=".4f")])
        .properties(height=260)
    )
    vol_line = (
        alt.Chart(rvol_df).mark_line(color="#3498db", strokeWidth=1.5)
        .encode(x="Date:T", y="Rolling std dev (%):Q")
    )
    st.altair_chart(vol_chart + vol_line, width="stretch")

    # --- Return distribution ---
    st.markdown("#### Return distribution")
    st.caption("If the bars extend further left than the orange normal curve, daily losses are fatter than theory predicts.")

    ret_df = returns_pct.reset_index()
    ret_df.columns = ["Date", "Daily return (%)"]
    avg, std = ret_metrics["avg_daily"], ret_metrics["std_daily"]

    hist_chart = (
        alt.Chart(ret_df).mark_bar(opacity=0.75)
        .encode(
            alt.X("Daily return (%):Q", bin=alt.Bin(maxbins=50)),
            alt.Y("count()", title="Frequency"),
            tooltip=["count()"],
        ).properties(height=300)
    )

    if std and not np.isnan(std):
        x_rng = np.linspace(returns_pct.min(), returns_pct.max(), 200)
        npdf = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_rng - avg) / std) ** 2)
        bw = (returns_pct.max() - returns_pct.min()) / 50
        ndf = pd.DataFrame({"Daily return (%)": x_rng, "Normal": npdf * len(returns_pct) * bw})
        nline = (
            alt.Chart(ndf).mark_line(color="orange", strokeDash=[6, 3], strokeWidth=2)
            .encode(x="Daily return (%):Q", y=alt.Y("Normal:Q", title="Frequency"))
        )
        mrule = (
            alt.Chart(pd.DataFrame({"x": [avg]}))
            .mark_rule(color="red", strokeDash=[4, 4], strokeWidth=2)
            .encode(x="x:Q")
        )
        st.altair_chart(hist_chart + nline + mrule, width="stretch")
        st.caption("Orange dashed = normal distribution  ·  Red dashed = mean return")
    else:
        st.altair_chart(hist_chart, width="stretch")


# ========================== PRICE & EVENTS ==================================
with tab_events:
    st.subheader("Price with event overlays")
    st.caption(
        "Why did it move? Overlay earnings dates, dividend ex-dates, and outlier days on the price chart "
        "to put spikes and drops in context."
    )

    # Layer toggles
    tcol1, tcol2, tcol3, tcol4 = st.columns(4)
    show_earnings = tcol1.checkbox("Earnings dates", value=True)
    show_dividends = tcol2.checkbox("Dividends", value=True)
    show_outliers = tcol3.checkbox(f"Outlier days (|z| > {outlier_z})", value=True)
    relative_to_sector = tcol4.checkbox("Relative to sector ETF", value=False)

    # Build display series (relative to sector if toggled)
    sector_etf = get_sector_etf(sector)
    display_series = close.copy()
    display_label = "Price ($)"

    if relative_to_sector and sector_etf:
        sect_df = _load_prices(sector_etf)
        if not sect_df.empty:
            # Align dates, normalize both to 1.0 at start, then take ratio
            aligned = pd.concat([close, sect_df["Close"]], axis=1, join="inner")
            aligned.columns = ["stock", "sector"]
            if len(aligned) > 1:
                norm_stock = aligned["stock"] / aligned["stock"].iloc[0]
                norm_sector = aligned["sector"] / aligned["sector"].iloc[0]
                display_series = norm_stock / norm_sector
                display_label = f"{ticker} / {sector_etf} (start = 1.0)"
        else:
            st.caption(f"Could not load {sector_etf}; showing absolute price.")

    # Base price chart
    price_plot_df = display_series.reset_index()
    price_plot_df.columns = ["Date", display_label]

    price_chart = (
        alt.Chart(price_plot_df).mark_line(color="#2c3e50", strokeWidth=1.8)
        .encode(
            x="Date:T",
            y=alt.Y(f"{display_label}:Q").scale(zero=False),
            tooltip=["Date:T", alt.Tooltip(f"{display_label}:Q", format=",.2f")],
        ).properties(height=420)
    )
    layers = [price_chart]

    # --- Earnings overlay ---
    if show_earnings:
        ed = get_earnings_dates(ticker)
        if not ed.empty:
            start_dt = close.index[0]
            end_dt = close.index[-1]
            # Normalise index comparison
            start_naive = pd.Timestamp(start_dt).tz_localize(None) if pd.Timestamp(start_dt).tz else pd.Timestamp(start_dt)
            end_naive = pd.Timestamp(end_dt).tz_localize(None) if pd.Timestamp(end_dt).tz else pd.Timestamp(end_dt)
            ed_in_range = ed[(ed.index >= start_naive) & (ed.index <= end_naive)]
            if not ed_in_range.empty:
                # Map each earnings date to its closest trading-day price for the marker
                price_map = display_series.copy()
                price_map.index = pd.to_datetime(price_map.index).tz_localize(None) if price_map.index.tz is not None else pd.to_datetime(price_map.index)
                e_rows = []
                for dt in ed_in_range.index:
                    # Find the nearest trading day on or after earnings
                    future = price_map.index[price_map.index >= dt]
                    match = future.min() if len(future) else None
                    if match is not None and not pd.isna(match):
                        e_rows.append({"Date": match, display_label: price_map.loc[match], "Event": "Earnings"})
                if e_rows:
                    e_df = pd.DataFrame(e_rows)
                    e_points = (
                        alt.Chart(e_df).mark_point(shape="triangle-up", size=180, color="#8e44ad", filled=True)
                        .encode(
                            x="Date:T", y=f"{display_label}:Q",
                            tooltip=["Event:N", "Date:T", alt.Tooltip(f"{display_label}:Q", format=",.2f")],
                        )
                    )
                    layers.append(e_points)

    # --- Dividends overlay ---
    if show_dividends:
        divs = get_dividends(ticker, period="10y")
        if not divs.empty:
            start_naive = pd.Timestamp(close.index[0]).tz_localize(None) if pd.Timestamp(close.index[0]).tz else pd.Timestamp(close.index[0])
            end_naive = pd.Timestamp(close.index[-1]).tz_localize(None) if pd.Timestamp(close.index[-1]).tz else pd.Timestamp(close.index[-1])
            divs_in_range = divs[(divs.index >= start_naive) & (divs.index <= end_naive)]
            if not divs_in_range.empty:
                price_map = display_series.copy()
                price_map.index = pd.to_datetime(price_map.index).tz_localize(None) if price_map.index.tz is not None else pd.to_datetime(price_map.index)
                d_rows = []
                for dt, amt in divs_in_range.items():
                    future = price_map.index[price_map.index >= dt]
                    match = future.min() if len(future) else None
                    if match is not None and not pd.isna(match):
                        d_rows.append({"Date": match, display_label: price_map.loc[match],
                                       "Event": f"Dividend ${amt:.2f}"})
                if d_rows:
                    d_df = pd.DataFrame(d_rows)
                    d_points = (
                        alt.Chart(d_df).mark_point(shape="circle", size=90, color="#27ae60", filled=True, opacity=0.8)
                        .encode(
                            x="Date:T", y=f"{display_label}:Q",
                            tooltip=["Event:N", "Date:T"],
                        )
                    )
                    layers.append(d_points)

    # --- Outlier days overlay ---
    if show_outliers:
        rets = close.pct_change().dropna()
        outliers = detect_outlier_days(rets, z_threshold=outlier_z)
        if not outliers.empty:
            price_map = display_series.copy()
            o_rows = []
            for dt, ret_val in outliers.items():
                if dt in price_map.index:
                    o_rows.append({
                        "Date": dt,
                        display_label: price_map.loc[dt],
                        "Event": f"Outlier: {ret_val*100:+.2f}%",
                        "Return": ret_val * 100,
                    })
            if o_rows:
                o_df = pd.DataFrame(o_rows)
                o_points = (
                    alt.Chart(o_df).mark_point(shape="diamond", size=130, filled=True, opacity=0.9)
                    .encode(
                        x="Date:T", y=f"{display_label}:Q",
                        color=alt.condition(alt.datum.Return > 0, alt.value("#2ecc71"), alt.value("#e74c3c")),
                        tooltip=["Event:N", "Date:T", alt.Tooltip(f"{display_label}:Q", format=",.2f")],
                    )
                )
                layers.append(o_points)

    st.altair_chart(alt.layer(*layers).interactive(), width="stretch")

    # Legend
    legend_parts = []
    if show_earnings: legend_parts.append("🔺 purple = earnings")
    if show_dividends: legend_parts.append("🟢 green = dividend ex-date")
    if show_outliers: legend_parts.append("🔶 diamond (green/red) = outlier day")
    if legend_parts:
        st.caption("Legend: " + "  ·  ".join(legend_parts))

    st.divider()

    # --- Event timeline ---
    st.markdown("#### Top price-move days")
    st.caption("Biggest one-day moves in the window — the moments most likely to have an explanation worth finding.")

    rets_pct = close.pct_change() * 100
    top_moves = rets_pct.dropna().abs().nlargest(10).index
    timeline_rows = []
    for dt in top_moves:
        timeline_rows.append({
            "Date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
            "Price": f"${close.loc[dt]:,.2f}",
            "Daily return": f"{rets_pct.loc[dt]:+.2f}%",
        })
    tl_df = pd.DataFrame(timeline_rows)
    st.dataframe(tl_df, width="stretch", hide_index=True)

    # --- Upcoming earnings ---
    ed = get_earnings_dates(ticker)
    if not ed.empty:
        today = pd.Timestamp.today().normalize()
        upcoming = ed[ed.index >= today]
        if not upcoming.empty:
            next_date = upcoming.index.min()
            days_until = (next_date - today).days
            st.info(
                f"**Next earnings:** {next_date.strftime('%B %d, %Y')}  ·  {days_until} days away.",
                icon=":material/event:",
            )


# ===========================================================================
# Footer — cross-page hooks
# ===========================================================================
st.divider()
st.caption(
    "**Keep going:** "
    "Screener → discover more candidates  ·  "
    "Compare Stocks → stack head-to-head  ·  "
    "Portfolio Risk → test the portfolio impact of adding this name."
)
