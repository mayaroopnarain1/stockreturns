# -*- coding: utf-8 -*-
"""
Page 2 — Stock Screener
Scan S&P 500 for undervalued, high-quality stocks with a composite value score.
"""

import streamlit as st
import pandas as pd
import numpy as np
from utils.data import SP500_TICKERS, fetch_fundamentals_bulk
from utils.metrics import FUNDAMENTAL_DESC

st.set_page_config(page_title="Stock Screener — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/filter_list: Stock Screener")
st.caption("Screen the S&P 500 for undervalued, high-quality stocks. Adjust filters in the sidebar.")

with st.sidebar:
    st.header("Filters")
    st.subheader("Valuation")
    max_pe = st.slider("Max Trailing P/E", 0, 100, 25, help=FUNDAMENTAL_DESC["trailingPE"])
    max_pb = st.slider("Max Price/Book", 0.0, 20.0, 5.0, 0.5, help=FUNDAMENTAL_DESC["priceToBook"])
    max_ev = st.slider("Max EV/EBITDA", 0.0, 50.0, 15.0, 0.5, help=FUNDAMENTAL_DESC["enterpriseToEbitda"])
    max_peg = st.slider("Max PEG", 0.0, 5.0, 2.0, 0.1, help=FUNDAMENTAL_DESC["pegRatio"])

    st.subheader("Quality")
    min_roe = st.slider("Min ROE (%)", 0, 50, 10, help=FUNDAMENTAL_DESC["returnOnEquity"]) / 100
    max_de = st.slider("Max D/E", 0.0, 10.0, 3.0, 0.5, help=FUNDAMENTAL_DESC["debtToEquity"])
    min_margin = st.slider("Min Profit Margin (%)", -20, 60, 5, help=FUNDAMENTAL_DESC["profitMargins"]) / 100

    st.subheader("Growth")
    min_rev = st.slider("Min Revenue Growth (%)", -50, 100, 0) / 100

    st.subheader("Other")
    min_mcap = st.number_input("Min Market Cap ($B)", value=1.0, step=1.0) * 1e9
    show_desc = st.checkbox("Show metric descriptions", value=True)

with st.spinner("Fetching S&P 500 fundamentals — first time takes 3–8 min, then cached 12h…"):
    raw = fetch_fundamentals_bulk(SP500_TICKERS)

if raw.empty:
    st.error("Could not fetch data. Yahoo Finance may be rate-limiting. Try again in a few minutes.")
    st.stop()

df = raw.copy()
if "currentPrice" in df.columns and "fiftyTwoWeekHigh" in df.columns:
    df["pct_below_52w_high"] = ((df["fiftyTwoWeekHigh"] - df["currentPrice"]) / df["fiftyTwoWeekHigh"] * 100).round(1)
df["marketCapB"] = (df["marketCap"] / 1e9).round(2)
df["dividendYieldPct"] = (df["dividendYield"].fillna(0) * 100).round(2)

# Apply filters
mask = pd.Series(True, index=df.index)
if "trailingPE" in df.columns: mask &= df["trailingPE"].fillna(999) <= max_pe
if "priceToBook" in df.columns: mask &= df["priceToBook"].fillna(999) <= max_pb
if "enterpriseToEbitda" in df.columns: mask &= df["enterpriseToEbitda"].fillna(999) <= max_ev
if "pegRatio" in df.columns: mask &= df["pegRatio"].fillna(999) <= max_peg
if "returnOnEquity" in df.columns: mask &= df["returnOnEquity"].fillna(0) >= min_roe
if "debtToEquity" in df.columns: mask &= df["debtToEquity"].fillna(999) <= max_de * 100
if "profitMargins" in df.columns: mask &= df["profitMargins"].fillna(-999) >= min_margin
if "revenueGrowth" in df.columns: mask &= df["revenueGrowth"].fillna(-999) >= min_rev
if "marketCap" in df.columns: mask &= df["marketCap"].fillna(0) >= min_mcap

filtered = df[mask].copy()

# Composite value score
def rank_pct(s, ascending=True):
    return s.rank(pct=True, ascending=ascending, na_option="bottom") * 100

if len(filtered) > 1:
    sc = pd.DataFrame(index=filtered.index)
    sc["PE"] = rank_pct(filtered["trailingPE"], True)
    sc["PB"] = rank_pct(filtered["priceToBook"], True)
    sc["EV"] = rank_pct(filtered["enterpriseToEbitda"], True)
    sc["PEG"] = rank_pct(filtered["pegRatio"], True)
    sc["ROE"] = rank_pct(filtered["returnOnEquity"], False)
    sc["Margin"] = rank_pct(filtered["profitMargins"], False)
    sc["RevG"] = rank_pct(filtered["revenueGrowth"], False)
    filtered["Value Score"] = (
        0.50 * sc[["PE","PB","EV","PEG"]].mean(axis=1)
        + 0.30 * sc[["ROE","Margin"]].mean(axis=1)
        + 0.20 * sc["RevG"]
    ).round(1)
    filtered = filtered.sort_values("Value Score", ascending=False)

st.subheader(f"Results — {len(filtered)} of {len(df)} stocks pass filters")

if filtered.empty:
    st.warning("No stocks match. Try loosening the filters.")
    st.stop()

display_cols = {
    "shortName": "Company", "sector": "Sector", "marketCapB": "Mkt Cap ($B)",
    "currentPrice": "Price", "trailingPE": "P/E", "forwardPE": "Fwd P/E",
    "priceToBook": "P/B", "enterpriseToEbitda": "EV/EBITDA", "pegRatio": "PEG",
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
            "**Value Score** (0–100) ranks each stock relative to others that passed "
            "your filters:\n\n"
            "- **50% Valuation** — P/E, P/B, EV/EBITDA, PEG (lower = higher score)\n"
            "- **30% Quality** — ROE, profit margin (higher = better)\n"
            "- **20% Growth** — revenue growth (higher = better)\n\n"
            "A score of 80+ ≈ top 20% of your filtered universe."
        )
