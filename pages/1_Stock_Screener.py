# -*- coding: utf-8 -*-
"""
Page 1 — Stock Screener
Scan the S&P 500 for undervalued stocks using valuation multiples,
quality metrics, and a composite value score.
"""

import streamlit as st
import pandas as pd
import numpy as np
from utils.data import SP500_TICKERS, fetch_fundamentals_bulk
from utils.metrics import FUNDAMENTAL_DESC

st.set_page_config(page_title="Stock Screener — StockLens", page_icon=":chart_with_upwards_trend:", layout="wide")

st.title(":material/search: Stock Screener")
st.caption(
    "Screen the S&P 500 for undervalued, high-quality stocks. "
    "Adjust filters in the sidebar, then sort or explore the results."
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")

    st.subheader("Valuation")
    max_pe = st.slider("Max Trailing P/E", 0, 100, 25, help=FUNDAMENTAL_DESC["trailingPE"])
    max_pb = st.slider("Max Price/Book", 0.0, 20.0, 5.0, step=0.5, help=FUNDAMENTAL_DESC["priceToBook"])
    max_ev_ebitda = st.slider("Max EV/EBITDA", 0.0, 50.0, 15.0, step=0.5, help=FUNDAMENTAL_DESC["enterpriseToEbitda"])
    max_peg = st.slider("Max PEG Ratio", 0.0, 5.0, 2.0, step=0.1, help=FUNDAMENTAL_DESC["pegRatio"])

    st.subheader("Quality")
    min_roe = st.slider("Min Return on Equity (%)", 0, 50, 10, help=FUNDAMENTAL_DESC["returnOnEquity"]) / 100
    max_de = st.slider("Max Debt/Equity", 0.0, 10.0, 3.0, step=0.5, help=FUNDAMENTAL_DESC["debtToEquity"])
    min_margin = st.slider("Min Profit Margin (%)", -20, 60, 5, help=FUNDAMENTAL_DESC["profitMargins"]) / 100

    st.subheader("Growth")
    min_rev_growth = st.slider("Min Revenue Growth (%)", -50, 100, 0, help=FUNDAMENTAL_DESC["revenueGrowth"]) / 100

    st.subheader("Other")
    min_mcap = st.number_input("Min Market Cap ($B)", value=1.0, step=1.0) * 1e9

    show_descriptions = st.checkbox("Show metric descriptions", value=True)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with st.spinner("Fetching S&P 500 fundamentals — this takes 3–8 minutes the first time, then results are cached for 12 hours…"):
    raw = fetch_fundamentals_bulk(SP500_TICKERS)

if raw.empty:
    st.error("Could not fetch fundamental data. Yahoo Finance may be rate-limiting. Try again in a few minutes.")
    st.stop()

df = raw.copy()

# Derived columns
if "currentPrice" in df.columns and "fiftyTwoWeekHigh" in df.columns:
    df["pct_below_52w_high"] = ((df["fiftyTwoWeekHigh"] - df["currentPrice"]) / df["fiftyTwoWeekHigh"] * 100).round(1)

# Format market cap for display
df["marketCapB"] = (df["marketCap"] / 1e9).round(2)
df["dividendYieldPct"] = (df["dividendYield"].fillna(0) * 100).round(2)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
mask = pd.Series(True, index=df.index)

if "trailingPE" in df.columns:
    mask &= df["trailingPE"].fillna(999) <= max_pe
if "priceToBook" in df.columns:
    mask &= df["priceToBook"].fillna(999) <= max_pb
if "enterpriseToEbitda" in df.columns:
    mask &= df["enterpriseToEbitda"].fillna(999) <= max_ev_ebitda
if "pegRatio" in df.columns:
    mask &= df["pegRatio"].fillna(999) <= max_peg
if "returnOnEquity" in df.columns:
    mask &= df["returnOnEquity"].fillna(0) >= min_roe
if "debtToEquity" in df.columns:
    mask &= df["debtToEquity"].fillna(999) <= max_de * 100  # yfinance returns D/E as percentage
if "profitMargins" in df.columns:
    mask &= df["profitMargins"].fillna(-999) >= min_margin
if "revenueGrowth" in df.columns:
    mask &= df["revenueGrowth"].fillna(-999) >= min_rev_growth
if "marketCap" in df.columns:
    mask &= df["marketCap"].fillna(0) >= min_mcap

filtered = df[mask].copy()

# ---------------------------------------------------------------------------
# Composite value score (rank-based)
# ---------------------------------------------------------------------------
# Lower is "cheaper" for valuation ratios → invert ranks so cheap = high score
# Higher is "better" for quality ratios → keep rank direction

def rank_pct(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Rank as percentile 0–100. ascending=True means lower raw value → higher score."""
    return series.rank(pct=True, ascending=ascending, na_option="bottom") * 100

if len(filtered) > 1:
    scores = pd.DataFrame(index=filtered.index)

    # Valuation (lower = better → ascending=True gives higher rank to lower values)
    scores["PE_score"] = rank_pct(filtered["trailingPE"], ascending=True)
    scores["PB_score"] = rank_pct(filtered["priceToBook"], ascending=True)
    scores["EVEBITDA_score"] = rank_pct(filtered["enterpriseToEbitda"], ascending=True)
    scores["PEG_score"] = rank_pct(filtered["pegRatio"], ascending=True)

    # Quality (higher = better → ascending=False)
    scores["ROE_score"] = rank_pct(filtered["returnOnEquity"], ascending=False)
    scores["Margin_score"] = rank_pct(filtered["profitMargins"], ascending=False)

    # Growth (higher = better)
    scores["RevGrowth_score"] = rank_pct(filtered["revenueGrowth"], ascending=False)

    # Composite: 50% valuation, 30% quality, 20% growth
    filtered["Value Score"] = (
        0.50 * scores[["PE_score", "PB_score", "EVEBITDA_score", "PEG_score"]].mean(axis=1)
        + 0.30 * scores[["ROE_score", "Margin_score"]].mean(axis=1)
        + 0.20 * scores["RevGrowth_score"]
    ).round(1)

    filtered = filtered.sort_values("Value Score", ascending=False)

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
st.subheader(f"Results — {len(filtered)} of {len(df)} stocks pass filters")

if filtered.empty:
    st.warning("No stocks match the current filters. Try loosening the criteria.")
    st.stop()

# Build display table
display_cols = {
    "shortName": "Company",
    "sector": "Sector",
    "marketCapB": "Mkt Cap ($B)",
    "currentPrice": "Price",
    "trailingPE": "P/E",
    "forwardPE": "Fwd P/E",
    "priceToBook": "P/B",
    "enterpriseToEbitda": "EV/EBITDA",
    "pegRatio": "PEG",
    "dividendYieldPct": "Div Yield %",
    "returnOnEquity": "ROE",
    "profitMargins": "Margin",
    "revenueGrowth": "Rev Growth",
    "debtToEquity": "D/E",
    "beta": "Beta",
    "pct_below_52w_high": "% Below 52w High",
}

if "Value Score" in filtered.columns:
    display_cols["Value Score"] = "Value Score"

available = {k: v for k, v in display_cols.items() if k in filtered.columns}
display = filtered[list(available.keys())].rename(columns=available)

# Format percentages for readability
for col in ["ROE", "Margin", "Rev Growth"]:
    if col in display.columns:
        display[col] = (display[col] * 100).round(2).astype(str) + "%"

st.dataframe(
    display,
    use_container_width=True,
    height=600,
)

# Metric descriptions
if show_descriptions:
    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in display_cols:
                st.markdown(f"**{display_cols.get(key, key)}:** {desc}")

# Value score explanation
if "Value Score" in filtered.columns:
    with st.expander("How is the Value Score calculated?"):
        st.markdown(
            "The **Value Score** (0–100) ranks each stock relative to others that "
            "passed your filters using a weighted composite:\n\n"
            "- **50% Valuation** — average percentile rank across P/E, P/B, EV/EBITDA, and PEG "
            "(lower multiples = higher score)\n"
            "- **30% Quality** — average percentile rank of ROE and profit margin "
            "(higher = better)\n"
            "- **20% Growth** — percentile rank of revenue growth (higher = better)\n\n"
            "A score of 80+ means the stock ranks in roughly the top 20% of your "
            "filtered universe on this blended measure."
        )
