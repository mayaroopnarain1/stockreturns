# -*- coding: utf-8 -*-
"""
Page 1 — Stock Screener

Scan the S&P 500 for stocks that match your criteria. Key upgrades from v1:
  - Investor profile selector reweights the composite score for Value / Growth /
    Income / Balanced investors.
  - Sector filter (multi-select) for targeted searches.
  - "Run screen" button defers the slow S&P-500 bulk fetch so landing on the
    page doesn't trigger a 3-8 minute wait.
  - Quick "Add to watchlist" button per result row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from utils.data import SP500_TICKERS, fetch_fundamentals_bulk
from utils.metrics import FUNDAMENTAL_DESC
from utils.watchlist import add_ticker as watchlist_add
from utils.watchlist import get_tickers as watchlist_get

st.set_page_config(
    page_title="Stock Screener — StockLens",
    page_icon=":material/search:",
    layout="wide",
)

st.title(":material/search: Stock Screener")
st.caption(
    "Screen the S&P 500 for stocks matching your criteria. Adjust filters in "
    "the sidebar, choose an investor profile to reweight the composite score, "
    "then run the screen."
)


# ---------------------------------------------------------------------------
# Investor-profile-aware composite weights
# ---------------------------------------------------------------------------
# Three score components — valuation, quality, growth — with per-profile
# weights. Sum to 1.0 for each profile.
PROFILE_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "Balanced":  {"valuation": 0.40, "quality": 0.35, "growth": 0.25},
    "Value":     {"valuation": 0.60, "quality": 0.30, "growth": 0.10},
    "Growth":    {"valuation": 0.15, "quality": 0.30, "growth": 0.55},
    "Income":    {"valuation": 0.40, "quality": 0.45, "growth": 0.15},
}

PROFILE_BLURBS = {
    "Balanced": "Equal-ish emphasis on cheap multiples, solid profitability, and decent growth.",
    "Value":    "Leans heavily on low multiples — ranks Graham-style cheapness first.",
    "Growth":   "Prioritizes revenue growth and earnings trajectory over price.",
    "Income":   "Weights quality and dividend sustainability; muted growth emphasis.",
}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Investor profile")
    profile = st.selectbox(
        "Composite score weighting",
        list(PROFILE_SCORE_WEIGHTS.keys()),
        index=0,
        help="Reweights the Value Score. Default is Balanced.",
    )
    st.caption(PROFILE_BLURBS[profile])

    w = PROFILE_SCORE_WEIGHTS[profile]
    st.caption(
        f"Weights → Valuation {int(w['valuation'] * 100)}% · "
        f"Quality {int(w['quality'] * 100)}% · Growth {int(w['growth'] * 100)}%"
    )

    st.divider()
    st.subheader("Valuation filters")
    max_pe = st.slider("Max Trailing P/E", 0, 100, 25, help=FUNDAMENTAL_DESC["trailingPE"])
    max_pb = st.slider("Max Price/Book", 0.0, 20.0, 5.0, step=0.5, help=FUNDAMENTAL_DESC["priceToBook"])
    max_ev_ebitda = st.slider("Max EV/EBITDA", 0.0, 50.0, 15.0, step=0.5, help=FUNDAMENTAL_DESC["enterpriseToEbitda"])
    max_peg = st.slider("Max PEG Ratio", 0.0, 5.0, 2.0, step=0.1, help=FUNDAMENTAL_DESC["pegRatio"])

    st.subheader("Quality filters")
    min_roe = st.slider("Min Return on Equity (%)", 0, 50, 10, help=FUNDAMENTAL_DESC["returnOnEquity"]) / 100
    max_de = st.slider("Max Debt/Equity", 0.0, 10.0, 3.0, step=0.5, help=FUNDAMENTAL_DESC["debtToEquity"])
    min_margin = st.slider("Min Profit Margin (%)", -20, 60, 5, help=FUNDAMENTAL_DESC["profitMargins"]) / 100

    st.subheader("Growth & income filters")
    min_rev_growth = st.slider("Min Revenue Growth (%)", -50, 100, 0, help=FUNDAMENTAL_DESC["revenueGrowth"]) / 100
    min_div_yield = st.slider("Min Dividend Yield (%)", 0.0, 10.0, 0.0, step=0.25) / 100

    st.subheader("Other")
    min_mcap = st.number_input("Min Market Cap ($B)", value=1.0, step=1.0) * 1e9

    # Sector filter — populated after fetch; show a placeholder note
    st.caption("Sector filter appears after the first screen run.")

    show_descriptions = st.checkbox("Show metric descriptions", value=False)


# ---------------------------------------------------------------------------
# Deferred data load — only fetch when the user clicks "Run screen"
# ---------------------------------------------------------------------------
if "screener_loaded" not in st.session_state:
    st.session_state["screener_loaded"] = False

cta_cols = st.columns([3, 1])
with cta_cols[0]:
    st.markdown(
        "First run takes **3–8 minutes** (S&P 500 bulk fetch). "
        "Subsequent runs are cached for 12 hours."
    )
with cta_cols[1]:
    if st.button(
        "Run screen" if not st.session_state["screener_loaded"] else "Refresh data",
        type="primary",
        width="stretch",
    ):
        st.session_state["screener_loaded"] = True

if not st.session_state["screener_loaded"]:
    st.info(
        "Click **Run screen** to fetch S&P 500 fundamentals and apply your filters.",
        icon=":material/play_circle:",
    )
    st.stop()


with st.spinner("Fetching S&P 500 fundamentals — this takes 3–8 minutes the first time, then cached for 12 hours…"):
    raw = fetch_fundamentals_bulk(SP500_TICKERS)

if raw.empty:
    st.error("Could not fetch fundamental data. Yahoo Finance may be rate-limiting. Try again in a few minutes.")
    st.stop()


df = raw.copy()
if "currentPrice" in df.columns and "fiftyTwoWeekHigh" in df.columns:
    df["pct_below_52w_high"] = (
        (df["fiftyTwoWeekHigh"] - df["currentPrice"]) / df["fiftyTwoWeekHigh"] * 100
    ).round(1)
df["marketCapB"] = (df["marketCap"] / 1e9).round(2)
df["dividendYieldPct"] = (df["dividendYield"].fillna(0) * 100).round(2)


# ---------------------------------------------------------------------------
# Sector filter (needs data to populate options)
# ---------------------------------------------------------------------------
all_sectors = sorted([s for s in df.get("sector", pd.Series()).dropna().unique() if s])
with st.sidebar:
    st.divider()
    sector_filter = st.multiselect(
        "Sector filter",
        all_sectors,
        default=[],
        help="Leave empty for all sectors.",
    )


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
    # yfinance reports D/E as a percentage (e.g. 150 for 1.5x)
    mask &= df["debtToEquity"].fillna(999) <= max_de * 100
if "profitMargins" in df.columns:
    mask &= df["profitMargins"].fillna(-999) >= min_margin
if "revenueGrowth" in df.columns:
    mask &= df["revenueGrowth"].fillna(-999) >= min_rev_growth
if "dividendYield" in df.columns:
    mask &= df["dividendYield"].fillna(0) >= min_div_yield
if "marketCap" in df.columns:
    mask &= df["marketCap"].fillna(0) >= min_mcap
if sector_filter and "sector" in df.columns:
    mask &= df["sector"].isin(sector_filter)

filtered = df[mask].copy()


# ---------------------------------------------------------------------------
# Composite score (investor-profile aware)
# ---------------------------------------------------------------------------
def rank_pct(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Rank as percentile 0–100. ascending=True → lower raw value scores higher."""
    return series.rank(pct=True, ascending=ascending, na_option="bottom") * 100


if len(filtered) > 1:
    scores = pd.DataFrame(index=filtered.index)
    # Valuation (lower = better)
    scores["PE"] = rank_pct(filtered["trailingPE"], ascending=True)
    scores["PB"] = rank_pct(filtered["priceToBook"], ascending=True)
    scores["EVEBITDA"] = rank_pct(filtered["enterpriseToEbitda"], ascending=True)
    scores["PEG"] = rank_pct(filtered["pegRatio"], ascending=True)
    # Quality (higher = better)
    scores["ROE"] = rank_pct(filtered["returnOnEquity"], ascending=False)
    scores["Margin"] = rank_pct(filtered["profitMargins"], ascending=False)
    # Growth (higher = better)
    scores["RevGrowth"] = rank_pct(filtered["revenueGrowth"], ascending=False)

    valuation_score = scores[["PE", "PB", "EVEBITDA", "PEG"]].mean(axis=1)
    quality_score = scores[["ROE", "Margin"]].mean(axis=1)
    growth_score = scores["RevGrowth"]

    wt = PROFILE_SCORE_WEIGHTS[profile]
    filtered["Value Score"] = (
        wt["valuation"] * valuation_score
        + wt["quality"] * quality_score
        + wt["growth"] * growth_score
    ).round(1)
    filtered["_val_sub"] = valuation_score.round(0)
    filtered["_qual_sub"] = quality_score.round(0)
    filtered["_grow_sub"] = growth_score.round(0)

    filtered = filtered.sort_values("Value Score", ascending=False)


# ---------------------------------------------------------------------------
# Summary + display
# ---------------------------------------------------------------------------
n_total = len(df)
n_pass = len(filtered)

scol1, scol2, scol3 = st.columns(3)
scol1.metric("Stocks in universe", n_total)
scol2.metric("Pass filters", n_pass)
scol3.metric("Active profile", profile)

st.subheader(f"Results — {n_pass} of {n_total} stocks")

if filtered.empty:
    st.warning("No stocks match the current filters. Try loosening the criteria.")
    st.stop()


# Main display table
display_cols = {
    "Value Score": "Score",
    "_val_sub": "Val",
    "_qual_sub": "Qlty",
    "_grow_sub": "Grw",
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
available = {k: v for k, v in display_cols.items() if k in filtered.columns}
display = filtered[list(available.keys())].rename(columns=available)

# Pretty percentages
for col in ["ROE", "Margin", "Rev Growth"]:
    if col in display.columns:
        display[col] = (display[col] * 100).round(2).astype(str) + "%"

st.dataframe(
    display,
    width="stretch",
    height=550,
    column_config={
        "Score": st.column_config.ProgressColumn(
            "Score",
            min_value=0,
            max_value=100,
            format="%.0f",
            help="Composite score (0–100) based on selected investor profile weighting.",
        ),
    },
)


# ---------------------------------------------------------------------------
# Quick actions — add top N to watchlist
# ---------------------------------------------------------------------------
st.divider()
st.subheader(":material/bookmark_add: Quick actions")

current_wl = set(watchlist_get())
top_n = min(10, len(filtered))

qcol1, qcol2, qcol3 = st.columns([2, 2, 3])
with qcol1:
    n_add = st.number_input(
        "Add top N to watchlist", min_value=1, max_value=top_n, value=min(5, top_n), step=1
    )
with qcol2:
    if st.button(f"Add top {n_add}", type="primary", width="stretch"):
        added_tickers = []
        skipped = []
        for t in filtered.head(int(n_add)).index:
            ok = watchlist_add(t)
            if ok:
                added_tickers.append(t)
            else:
                skipped.append(t)
        if added_tickers:
            st.success(f"Added to watchlist: {', '.join(added_tickers)}")
        if skipped:
            st.info(f"Already on watchlist: {', '.join(skipped)}")
        st.rerun()
with qcol3:
    if current_wl:
        st.caption(f"Currently watching: {', '.join(sorted(current_wl))}")
    st.page_link("pages/5_Watchlist.py", label="Open Watchlist", icon=":material/visibility:")


# ---------------------------------------------------------------------------
# Metric descriptions & score explanation
# ---------------------------------------------------------------------------
if show_descriptions:
    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in display_cols:
                st.markdown(f"**{display_cols.get(key, key)}:** {desc}")

with st.expander("How is the score calculated?"):
    w = PROFILE_SCORE_WEIGHTS[profile]
    st.markdown(
        f"""
        The **Composite Score** ranks each stock from 0–100 against the others
        that passed your filters, using weights for the **{profile}** profile:

        - **Valuation ({int(w['valuation'] * 100)}%)** — average percentile rank across
          P/E, P/B, EV/EBITDA, and PEG. Lower multiples → higher score.
        - **Quality ({int(w['quality'] * 100)}%)** — average percentile rank of ROE and
          profit margin. Higher → better.
        - **Growth ({int(w['growth'] * 100)}%)** — percentile rank of revenue growth.

        The "Val / Qlty / Grw" columns show the sub-scores (each 0–100) so you
        can see *why* a stock scored the way it did. Change the investor profile
        in the sidebar to reweight the composite.
        """
    )
