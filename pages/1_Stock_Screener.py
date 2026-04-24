# -*- coding: utf-8 -*-
"""
Page 1 — Stock Screener

Screen the S&P 500 for stocks matching simple, labeled filter ranges. Every
filter is a dropdown ("Any", "Value (< 15)", "Strong (> 15%)", etc.) so
users don't need to know what a reasonable P/E or Debt/Equity value looks
like before using the tool.

The first click on "Run screen" triggers a 3–8 minute bulk fetch of S&P 500
fundamentals; subsequent runs hit the 12h cache and are instant.
"""

from __future__ import annotations

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
    "Screen the S&P 500 for stocks matching your criteria. Pick from the "
    "labeled ranges in the sidebar, then run the screen."
)


# ---------------------------------------------------------------------------
# Filter presets — one labeled dropdown per metric
# ---------------------------------------------------------------------------
# Each entry: (label, min_inclusive_or_None, max_inclusive_or_None).
# "Any" means no filter; other options define a bound. A single bound on
# one side is the typical case; two-sided is used for market-cap tiers.
#
# yfinance reports debtToEquity as a percentage (150 = 1.5×). The preset
# bounds match that convention (< 50 = < 0.5×).

FILTER_PRESETS: dict[str, list[tuple[str, float | None, float | None]]] = {
    "marketCap": [
        ("Any",                     None,      None),
        ("Mega cap (> $200B)",      200e9,     None),
        ("Large cap ($10–200B)",    10e9,      200e9),
        ("Mid cap ($2–10B)",        2e9,       10e9),
        ("Small cap (< $2B)",       None,      2e9),
    ],
    "trailingPE": [
        ("Any",                     None,      None),
        ("Value (< 15)",            None,      15),
        ("Moderate (< 25)",         None,      25),
        ("Growthy (< 40)",          None,      40),
        ("Expensive (< 60)",        None,      60),
    ],
    "priceToBook": [
        ("Any",                     None,      None),
        ("Below book (< 1.0)",      None,      1.0),
        ("Cheap (< 2.0)",           None,      2.0),
        ("Moderate (< 4.0)",        None,      4.0),
        ("Premium (< 8.0)",         None,      8.0),
    ],
    "enterpriseToEbitda": [
        ("Any",                     None,      None),
        ("Bargain (< 8)",           None,      8),
        ("Fair (< 15)",             None,      15),
        ("Premium (< 25)",          None,      25),
    ],
    "pegRatio": [
        ("Any",                     None,      None),
        ("Undervalued (< 1.0)",     None,      1.0),
        ("Fair (< 2.0)",            None,      2.0),
        ("Rich (< 3.0)",            None,      3.0),
    ],
    "dividendYield": [
        ("Any",                     None,      None),
        ("Pays dividend (> 0%)",    0.0001,    None),
        ("Income (> 2%)",           0.02,      None),
        ("High yield (> 4%)",       0.04,      None),
        ("Very high (> 6%)",        0.06,      None),
    ],
    "returnOnEquity": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Decent (> 10%)",          0.10,      None),
        ("Strong (> 15%)",          0.15,      None),
        ("Elite (> 25%)",           0.25,      None),
    ],
    "profitMargins": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Healthy (> 10%)",         0.10,      None),
        ("Premium (> 20%)",         0.20,      None),
    ],
    "revenueGrowth": [
        ("Any",                     None,      None),
        ("Positive (> 0%)",         0.0,       None),
        ("Growing (> 5%)",          0.05,      None),
        ("Fast (> 15%)",            0.15,      None),
        ("Hyper (> 30%)",           0.30,      None),
    ],
    "debtToEquity": [
        ("Any",                     None,      None),
        ("Debt-free (< 0.25×)",     None,      25),
        ("Conservative (< 0.5×)",   None,      50),
        ("Moderate (< 1.0×)",       None,      100),
        ("Leveraged (< 2.0×)",      None,      200),
    ],
}


def _preset_labels(key: str) -> list[str]:
    return [label for label, _, _ in FILTER_PRESETS[key]]


def _preset_bounds(key: str, label: str) -> tuple[float | None, float | None]:
    for lbl, lo, hi in FILTER_PRESETS[key]:
        if lbl == label:
            return lo, hi
    return None, None


def _apply_bounds(series: pd.Series, lo: float | None, hi: float | None) -> pd.Series:
    """Build a boolean mask for a series against optional inclusive bounds.

    Rows with NaN values fail any active bound check (same semantics the
    slider-based version used via ``.fillna(sentinel)``). When both bounds
    are None the mask is all-True.
    """
    if lo is None and hi is None:
        return pd.Series(True, index=series.index)
    mask = series.notna()
    if lo is not None:
        mask &= series >= lo
    if hi is not None:
        mask &= series <= hi
    return mask


# Reset helper — resets all filter selectboxes to "Any" on next rerun.
RESET_FLAG_KEY = "_screener_reset_pending"
if st.session_state.get(RESET_FLAG_KEY):
    for key in FILTER_PRESETS:
        st.session_state[f"filter_{key}"] = "Any"
    st.session_state["sector_filter"] = []
    st.session_state[RESET_FLAG_KEY] = False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Market cap & valuation")
    sel_marketCap  = st.selectbox("Market cap tier",  _preset_labels("marketCap"),         key="filter_marketCap")
    sel_trailingPE = st.selectbox("Trailing P/E",     _preset_labels("trailingPE"),        key="filter_trailingPE", help=FUNDAMENTAL_DESC.get("trailingPE"))
    sel_priceToBook = st.selectbox("Price / Book",    _preset_labels("priceToBook"),       key="filter_priceToBook", help=FUNDAMENTAL_DESC.get("priceToBook"))
    sel_evEbitda   = st.selectbox("EV / EBITDA",      _preset_labels("enterpriseToEbitda"),key="filter_enterpriseToEbitda", help=FUNDAMENTAL_DESC.get("enterpriseToEbitda"))
    sel_peg        = st.selectbox("PEG ratio",        _preset_labels("pegRatio"),          key="filter_pegRatio", help=FUNDAMENTAL_DESC.get("pegRatio"))

    st.subheader("Quality")
    sel_roe        = st.selectbox("Return on equity", _preset_labels("returnOnEquity"),    key="filter_returnOnEquity", help=FUNDAMENTAL_DESC.get("returnOnEquity"))
    sel_margin     = st.selectbox("Profit margin",    _preset_labels("profitMargins"),     key="filter_profitMargins", help=FUNDAMENTAL_DESC.get("profitMargins"))
    sel_de         = st.selectbox("Debt / equity",    _preset_labels("debtToEquity"),      key="filter_debtToEquity", help=FUNDAMENTAL_DESC.get("debtToEquity"))

    st.subheader("Growth & income")
    sel_revGrowth  = st.selectbox("Revenue growth",   _preset_labels("revenueGrowth"),     key="filter_revenueGrowth", help=FUNDAMENTAL_DESC.get("revenueGrowth"))
    sel_divYield   = st.selectbox("Dividend yield",   _preset_labels("dividendYield"),     key="filter_dividendYield")

    st.divider()
    st.caption("Sector filter appears after the first screen run.")

    show_descriptions = st.checkbox("Show metric descriptions", value=False)

    if st.button("Reset filters", width="stretch"):
        st.session_state[RESET_FLAG_KEY] = True
        st.rerun()


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
        key="sector_filter",
        help="Leave empty for all sectors.",
    )


# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
selection = {
    "marketCap":          sel_marketCap,
    "trailingPE":         sel_trailingPE,
    "priceToBook":        sel_priceToBook,
    "enterpriseToEbitda": sel_evEbitda,
    "pegRatio":           sel_peg,
    "dividendYield":      sel_divYield,
    "returnOnEquity":     sel_roe,
    "profitMargins":      sel_margin,
    "revenueGrowth":      sel_revGrowth,
    "debtToEquity":       sel_de,
}

mask = pd.Series(True, index=df.index)
for field, label in selection.items():
    if field not in df.columns:
        continue
    lo, hi = _preset_bounds(field, label)
    mask &= _apply_bounds(df[field], lo, hi)
if sector_filter and "sector" in df.columns:
    mask &= df["sector"].isin(sector_filter)

filtered = df[mask].copy()

# Default sort: largest market cap first.
if "marketCap" in filtered.columns:
    filtered = filtered.sort_values("marketCap", ascending=False, na_position="last")


# ---------------------------------------------------------------------------
# Summary + display
# ---------------------------------------------------------------------------
n_total = len(df)
n_pass = len(filtered)
active_filters = [field for field, label in selection.items() if label != "Any"]
if sector_filter:
    active_filters.append("sector")

scol1, scol2, scol3 = st.columns(3)
scol1.metric("Stocks in universe", n_total)
scol2.metric("Pass filters", n_pass)
scol3.metric("Active filters", len(active_filters))

st.subheader(f"Results — {n_pass} of {n_total} stocks")

if filtered.empty:
    st.warning("No stocks match the current filters. Try loosening the criteria or clicking **Reset filters**.")
    st.stop()


# Main display table
display_cols = {
    "shortName":            "Company",
    "sector":               "Sector",
    "marketCapB":           "Mkt Cap ($B)",
    "currentPrice":         "Price",
    "trailingPE":           "P/E",
    "forwardPE":            "Fwd P/E",
    "priceToBook":          "P/B",
    "enterpriseToEbitda":   "EV/EBITDA",
    "pegRatio":             "PEG",
    "dividendYieldPct":     "Div Yield %",
    "returnOnEquity":       "ROE",
    "profitMargins":        "Margin",
    "revenueGrowth":        "Rev Growth",
    "debtToEquity":         "D/E",
    "beta":                 "Beta",
    "pct_below_52w_high":   "% Below 52w High",
}
available = {k: v for k, v in display_cols.items() if k in filtered.columns}
display = filtered[list(available.keys())].rename(columns=available)

# Pretty percentages for ratio fields that yfinance reports as fractions.
for col in ["ROE", "Margin", "Rev Growth"]:
    if col in display.columns:
        display[col] = (display[col] * 100).round(2).astype(str) + "%"

st.dataframe(display, width="stretch", height=550)


# ---------------------------------------------------------------------------
# Quick actions — add top N (by market cap) to watchlist
# ---------------------------------------------------------------------------
st.divider()
st.subheader(":material/bookmark_add: Quick actions")

current_wl = set(watchlist_get())
top_n = min(10, len(filtered))

qcol1, qcol2, qcol3 = st.columns([2, 2, 3])
with qcol1:
    n_add = st.number_input(
        "Add top N by market cap", min_value=1, max_value=top_n, value=min(5, top_n), step=1
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
# Metric descriptions
# ---------------------------------------------------------------------------
if show_descriptions:
    with st.expander("What do these metrics mean?"):
        for key, desc in FUNDAMENTAL_DESC.items():
            if key in display_cols:
                st.markdown(f"**{display_cols.get(key, key)}:** {desc}")
