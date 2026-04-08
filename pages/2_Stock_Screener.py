# -*- coding: utf-8 -*-
"""
Page 2 — Stock Screener
Scan S&P 500 with quick-pick presets and intuitive dropdown filters.
"""

import streamlit as st
import pandas as pd
import numpy as np
from utils.data import SP500_TICKERS, fetch_fundamentals_bulk
from utils.metrics import FUNDAMENTAL_DESC

st.set_page_config(page_title="Stock Screener — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/filter_list: Stock Screener")
st.caption("Screen the S&P 500 for undervalued, high-quality stocks. Pick a preset or customize filters.")

# ── Quick-pick presets ────────────────────────────────────────────────────
PRESETS = {
    "Custom": {},
    "Value Plays": {"max_pe": 18, "max_pb": 3.0, "max_ev": 12.0, "min_roe": 0.10, "max_de": 2.0, "min_margin": 0.05, "min_rev": -0.10, "min_mcap": 5.0},
    "Quality Growth": {"max_pe": 40, "max_pb": 15.0, "max_ev": 25.0, "min_roe": 0.15, "max_de": 2.0, "min_margin": 0.10, "min_rev": 0.05, "min_mcap": 10.0},
    "Dividend Income": {"max_pe": 25, "max_pb": 5.0, "max_ev": 15.0, "min_roe": 0.08, "max_de": 3.0, "min_margin": 0.05, "min_rev": -0.10, "min_mcap": 5.0, "min_div": 2.0},
    "Beaten Down": {"max_pe": 100, "max_pb": 20.0, "max_ev": 50.0, "min_roe": 0.0, "max_de": 5.0, "min_margin": -0.10, "min_rev": -0.50, "min_mcap": 1.0, "min_below_high": 20.0},
}
PRESET_DESCRIPTIONS = {
    "Custom": "Set your own filters below.",
    "Value Plays": "Low P/E, low P/B, reasonable EV/EBITDA. Classic value investing.",
    "Quality Growth": "High ROE, strong margins, positive revenue growth. Growth at a reasonable price.",
    "Dividend Income": "Dividend yield ≥ 2%, reasonable valuation, profitable companies.",
    "Beaten Down": "Stocks ≥ 20% below their 52-week high. Potential turnaround plays — or value traps.",
}

with st.sidebar:
    st.header("Quick Picks")
    preset = st.radio("Start from a preset", list(PRESETS.keys()), index=0, help="Select a preset to auto-fill the filters, or choose Custom to set your own.")
    p = PRESETS[preset]
    st.caption(PRESET_DESCRIPTIONS[preset])

    st.divider()
    st.header("Filters")

    # Valuation — dropdowns with meaningful labels
    st.subheader("Valuation")
    pe_options = {"Any": 100, "< 15 (Very Cheap)": 15, "< 20 (Cheap)": 20, "< 25 (Moderate)": 25, "< 35 (Growth)": 35, "< 50 (Expensive OK)": 50}
    pe_default = "< 25 (Moderate)"
    if "max_pe" in p:
        for label, val in pe_options.items():
            if val == p["max_pe"]:
                pe_default = label; break
    max_pe = pe_options[st.selectbox("Max P/E", list(pe_options.keys()), index=list(pe_options.keys()).index(pe_default), help=FUNDAMENTAL_DESC["trailingPE"])]

    pb_options = {"Any": 20.0, "< 2 (Deep Value)": 2.0, "< 3 (Value)": 3.0, "< 5 (Moderate)": 5.0, "< 10 (Growth)": 10.0}
    pb_default = "< 5 (Moderate)"
    if "max_pb" in p:
        for label, val in pb_options.items():
            if val == p["max_pb"]:
                pb_default = label; break
    max_pb = pb_options[st.selectbox("Max Price/Book", list(pb_options.keys()), index=list(pb_options.keys()).index(pb_default), help=FUNDAMENTAL_DESC["priceToBook"])]

    ev_options = {"Any": 50.0, "< 8 (Cheap)": 8.0, "< 12 (Value)": 12.0, "< 15 (Moderate)": 15.0, "< 25 (Growth)": 25.0}
    ev_default = "< 15 (Moderate)"
    if "max_ev" in p:
        for label, val in ev_options.items():
            if val == p["max_ev"]:
                ev_default = label; break
    max_ev = ev_options[st.selectbox("Max EV/EBITDA", list(ev_options.keys()), index=list(ev_options.keys()).index(ev_default), help=FUNDAMENTAL_DESC["enterpriseToEbitda"])]

    # Quality — dropdowns
    st.subheader("Quality")
    roe_options = {"Any": 0.0, "> 5% (Low Bar)": 0.05, "> 10% (Decent)": 0.10, "> 15% (Strong)": 0.15, "> 25% (Excellent)": 0.25}
    roe_default = "> 10% (Decent)"
    if "min_roe" in p:
        for label, val in roe_options.items():
            if val == p["min_roe"]:
                roe_default = label; break
    min_roe = roe_options[st.selectbox("Min ROE", list(roe_options.keys()), index=list(roe_options.keys()).index(roe_default), help=FUNDAMENTAL_DESC["returnOnEquity"])]

    de_options = {"Any": 10.0, "< 0.5 (Conservative)": 0.5, "< 1 (Low Leverage)": 1.0, "< 2 (Moderate)": 2.0, "< 3 (Flexible)": 3.0, "< 5 (High OK)": 5.0}
    de_default = "< 3 (Flexible)"
    if "max_de" in p:
        for label, val in de_options.items():
            if val == p["max_de"]:
                de_default = label; break
    max_de = de_options[st.selectbox("Max Debt/Equity", list(de_options.keys()), index=list(de_options.keys()).index(de_default), help=FUNDAMENTAL_DESC["debtToEquity"])]

    margin_options = {"Any": -0.20, "> 0% (Profitable)": 0.0, "> 5% (Decent)": 0.05, "> 10% (Strong)": 0.10, "> 20% (Excellent)": 0.20}
    margin_default = "> 5% (Decent)"
    if "min_margin" in p:
        for label, val in margin_options.items():
            if val == p["min_margin"]:
                margin_default = label; break
    min_margin = margin_options[st.selectbox("Min Profit Margin", list(margin_options.keys()), index=list(margin_options.keys()).index(margin_default), help=FUNDAMENTAL_DESC["profitMargins"])]

    # Growth
    st.subheader("Growth")
    rev_options = {"Any": -0.50, "> 0% (Growing)": 0.0, "> 5% (Solid)": 0.05, "> 10% (Strong)": 0.10, "> 20% (High Growth)": 0.20}
    rev_default = "> 0% (Growing)"
    if "min_rev" in p:
        for label, val in rev_options.items():
            if val == p["min_rev"]:
                rev_default = label; break
    min_rev = rev_options[st.selectbox("Min Revenue Growth", list(rev_options.keys()), index=list(rev_options.keys()).index(rev_default))]

    # Other
    st.subheader("Other")
    sector_filter = st.multiselect("Sectors", ["All"] + sorted([
        "Technology", "Financial Services", "Healthcare", "Industrials",
        "Consumer Cyclical", "Consumer Defensive", "Energy", "Utilities",
        "Communication Services", "Real Estate", "Basic Materials",
    ]), default=["All"])
    min_mcap = st.number_input("Min Market Cap ($B)", value=p.get("min_mcap", 1.0), step=1.0) * 1e9
    show_desc = st.checkbox("Show metric descriptions", value=True)

# ── Load data ─────────────────────────────────────────────────────────────
with st.spinner("Fetching S&P 500 fundamentals — first time takes 3–8 min, then cached 12h..."):
    raw = fetch_fundamentals_bulk(SP500_TICKERS)

if raw.empty:
    st.error("Could not fetch data. Yahoo Finance may be rate-limiting. Try again in a few minutes.")
    st.stop()

df = raw.copy()
if "currentPrice" in df.columns and "fiftyTwoWeekHigh" in df.columns:
    df["pct_below_52w_high"] = ((df["fiftyTwoWeekHigh"] - df["currentPrice"]) / df["fiftyTwoWeekHigh"] * 100).round(1)
df["marketCapB"] = (df["marketCap"] / 1e9).round(2)
df["dividendYieldPct"] = (df["dividendYield"].fillna(0) * 100).round(2)

# ── Apply filters (missing data = pass) ───────────────────────────────────
mask = pd.Series(True, index=df.index)
if "trailingPE" in df.columns: mask &= df["trailingPE"].isna() | (df["trailingPE"] <= max_pe)
if "priceToBook" in df.columns: mask &= df["priceToBook"].isna() | (df["priceToBook"] <= max_pb)
if "enterpriseToEbitda" in df.columns: mask &= df["enterpriseToEbitda"].isna() | (df["enterpriseToEbitda"] <= max_ev)
if "returnOnEquity" in df.columns: mask &= df["returnOnEquity"].isna() | (df["returnOnEquity"] >= min_roe)
if "debtToEquity" in df.columns: mask &= df["debtToEquity"].isna() | (df["debtToEquity"] <= max_de * 100)
if "profitMargins" in df.columns: mask &= df["profitMargins"].isna() | (df["profitMargins"] >= min_margin)
if "revenueGrowth" in df.columns: mask &= df["revenueGrowth"].isna() | (df["revenueGrowth"] >= min_rev)
if "marketCap" in df.columns: mask &= df["marketCap"].fillna(0) >= min_mcap

# Sector filter
if "All" not in sector_filter and sector_filter:
    mask &= df["sector"].isin(sector_filter)

# Preset-specific filters
if "min_div" in p and "dividendYieldPct" in df.columns:
    mask &= df["dividendYieldPct"] >= p["min_div"]
if "min_below_high" in p and "pct_below_52w_high" in df.columns:
    mask &= df["pct_below_52w_high"].fillna(0) >= p["min_below_high"]

filtered = df[mask].copy()

# ── Composite value score ─────────────────────────────────────────────────
def rank_pct(s, ascending=True):
    return s.rank(pct=True, ascending=ascending, na_option="bottom") * 100

if len(filtered) > 1:
    sc = pd.DataFrame(index=filtered.index)
    sc["PE"] = rank_pct(filtered["trailingPE"], True)
    sc["PB"] = rank_pct(filtered["priceToBook"], True)
    sc["EV"] = rank_pct(filtered["enterpriseToEbitda"], True)
    sc["ROE"] = rank_pct(filtered["returnOnEquity"], False)
    sc["Margin"] = rank_pct(filtered["profitMargins"], False)
    sc["RevG"] = rank_pct(filtered["revenueGrowth"], False)
    filtered["Value Score"] = (
        0.50 * sc[["PE","PB","EV"]].mean(axis=1)
        + 0.30 * sc[["ROE","Margin"]].mean(axis=1)
        + 0.20 * sc["RevG"]
    ).round(1)
    filtered = filtered.sort_values("Value Score", ascending=False)

st.subheader(f"Results — {len(filtered)} of {len(df)} stocks pass filters")

if filtered.empty:
    st.warning("No stocks match. Try loosening the filters or choosing a different preset.")
    st.stop()

display_cols = {
    "shortName": "Company", "sector": "Sector", "marketCapB": "Mkt Cap ($B)",
    "currentPrice": "Price", "trailingPE": "P/E", "forwardPE": "Fwd P/E",
    "priceToBook": "P/B", "enterpriseToEbitda": "EV/EBITDA",
    "dividendYieldPct": "Div Yield %", "returnOnEquity": "ROE",
    "profitMargins": "Margin", "revenueGrowth": "Rev Growth",
    "debtToEquity": "D/E", "beta": "Beta", "pct_below_52w_high": "% Below 52w High",
}
if "Value Score" in filtered.columns:
    display_cols["Value Score"] = "Value Score"

available = {k: v for k, v in display_cols.items() if k in filtered.columns}
display = filtered[list(available.keys())].rename(columns=available)
for col in ["ROE", "Margin", "Rev Growth"]:
    if col in display.columns:
        display[col] = (display[col] * 100).round(2).astype(str) + "%"

st.dataframe(display, width="stretch", height=600)

if show_desc:
    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in display_cols:
                st.markdown(f"**{display_cols.get(key, key)}:** {desc}")

if "Value Score" in filtered.columns:
    with st.expander("How is the Value Score calculated?"):
        st.markdown(
            "**Value Score** (0-100) ranks each stock relative to others that passed "
            "your filters:\n\n"
            "- **50% Valuation** — P/E, P/B, EV/EBITDA (lower = higher score)\n"
            "- **30% Quality** — ROE, profit margin (higher = better)\n"
            "- **20% Growth** — revenue growth (higher = better)\n\n"
            "A score of 80+ = top 20% of your filtered universe."
        )
