# -*- coding: utf-8 -*-
"""
StockLens — Market Pulse (Home)

The daily engagement hook. Shows:
  - Macro regime strip (VIX, 10Y yield, S&P 500)
  - Sector ETF heatmap (11 SPDR sectors colored by 1-day % change)
  - Watchlist snippet (live status for tickers the user is tracking)
  - Top movers (biggest S&P 100 gainers / losers on the day)
  - Navigation to the deep-dive pages

Designed to be the first thing the user opens in the morning.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from utils.data import (
    SECTOR_ETF,
    get_daily_changes,
    get_macro_snapshot,
)
from utils.watchlist import get_tickers as get_watchlist_tickers
from utils.watchlist import load_watchlist


st.set_page_config(
    page_title="StockLens — Market Pulse",
    page_icon=":material/query_stats:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Header + macro regime strip
# ---------------------------------------------------------------------------

today = dt.date.today()
weekday = today.strftime("%A")
is_weekend = today.weekday() >= 5

st.title(":material/query_stats: StockLens — Market Pulse")
st.caption(
    f"{weekday}, {today.strftime('%B %d, %Y')} "
    + ("· Markets closed (weekend)" if is_weekend else "· Live quotes from Yahoo Finance")
)

macro = get_macro_snapshot()


def _macro_metric(sym: str, fmt: str, delta_inverse: bool = False) -> None:
    """Render one macro metric. delta_inverse=True for VIX (up is bad)."""
    data = macro.get(sym, {})
    current = data.get("current")
    pct = data.get("change_pct")
    label = data.get("label", sym)
    value = fmt.format(current) if current is not None else "—"
    if pct is None:
        delta = None
    else:
        delta = f"{pct:+.2f}%"
    # For VIX, rising is "off" (risk-off). Streamlit's default red-green treats
    # positive delta as green; `delta_color='inverse'` flips that.
    st.metric(
        label,
        value,
        delta=delta,
        delta_color="inverse" if delta_inverse else "normal",
    )


mcol1, mcol2, mcol3, mcol4 = st.columns([1, 1, 1, 1])
with mcol1:
    _macro_metric("SPY", "${:,.2f}")
with mcol2:
    _macro_metric("^VIX", "{:.2f}", delta_inverse=True)
with mcol3:
    _macro_metric("^TNX", "{:.2f}%")
with mcol4:
    # Simple regime label derived from VIX level
    vix = macro.get("^VIX", {}).get("current")
    if vix is None:
        regime, tone = "—", "gray"
    elif vix < 15:
        regime, tone = "Calm", "#16a34a"
    elif vix < 20:
        regime, tone = "Normal", "#0891b2"
    elif vix < 30:
        regime, tone = "Elevated", "#d97706"
    else:
        regime, tone = "Stressed", "#dc2626"
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;
                    background:#fafafa;height:100%;">
          <div style="font-size:13px;color:#6b7280;">Regime</div>
          <div style="font-size:28px;font-weight:600;color:{tone};line-height:1.1;">
            {regime}
          </div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px;">
            Based on VIX level
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Sector heatmap
# ---------------------------------------------------------------------------

st.subheader(":material/grid_view: Sector heatmap")
st.caption("1-day move in each SPDR sector ETF. Click into Stock Analysis to drill into names.")

sector_etfs = list(SECTOR_ETF.values())  # 11 ETFs
sector_names = list(SECTOR_ETF.keys())

with st.spinner("Loading sector data..."):
    sector_changes = get_daily_changes(tuple(sector_etfs))


def _tile_color(pct: float | None) -> str:
    """Return a hex background for a sector tile based on % change."""
    if pct is None:
        return "#f3f4f6"
    # Clamp at ±3% for color saturation
    clamped = max(-3.0, min(3.0, pct))
    if clamped >= 0:
        # Green shade: stronger green as pct grows
        intensity = min(1.0, clamped / 3.0)
        # Blend between pale green (#e6f4ea) and strong green (#16a34a)
        r = int(230 - (230 - 22) * intensity)
        g = int(244 - (244 - 163) * intensity)
        b = int(234 - (234 - 74) * intensity)
    else:
        intensity = min(1.0, -clamped / 3.0)
        r = int(253 - (253 - 220) * intensity)
        g = int(226 - (226 - 38) * intensity)
        b = int(226 - (226 - 38) * intensity)
    return f"rgb({r},{g},{b})"


def _tile_text_color(pct: float | None) -> str:
    """Darker text when background is strong, lighter when pale."""
    if pct is None:
        return "#6b7280"
    return "#111827" if abs(pct) < 1.5 else "#ffffff"


# Build 4 columns x 3 rows (11 tiles; last cell empty)
n_cols = 4
tile_cols = st.columns(n_cols)
for i, (sector, etf) in enumerate(SECTOR_ETF.items()):
    col = tile_cols[i % n_cols]
    row = sector_changes.loc[etf] if etf in sector_changes.index else None
    if row is not None:
        pct = float(row["change_pct"])
        price = float(row["price"])
        pct_str = f"{pct:+.2f}%"
        price_str = f"${price:,.2f}"
    else:
        pct = None
        pct_str = "—"
        price_str = "—"
    bg = _tile_color(pct)
    fg = _tile_text_color(pct)
    with col:
        st.markdown(
            f"""
            <div style="background:{bg};border-radius:8px;padding:14px 12px;
                        margin-bottom:10px;min-height:96px;">
              <div style="font-size:11px;color:{fg};opacity:0.85;
                          text-transform:uppercase;letter-spacing:0.03em;">
                {etf}
              </div>
              <div style="font-size:13px;color:{fg};font-weight:500;
                          margin-top:2px;">
                {sector}
              </div>
              <div style="font-size:22px;color:{fg};font-weight:700;
                          margin-top:6px;">
                {pct_str}
              </div>
              <div style="font-size:11px;color:{fg};opacity:0.75;">
                {price_str}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Leaderboard
if not sector_changes.empty:
    sector_df = sector_changes.copy()
    sector_df["Sector"] = [
        next((s for s, e in SECTOR_ETF.items() if e == t), t)
        for t in sector_df.index
    ]
    leaders = sector_df.sort_values("change_pct", ascending=False)
    lcol1, lcol2 = st.columns(2)
    with lcol1:
        st.caption(":material/trending_up: Leading sectors")
        for _, r in leaders.head(3).iterrows():
            st.write(
                f"**{r['Sector']}** ({r.name}) · **{r['change_pct']:+.2f}%**  ·  ${r['price']:,.2f}"
            )
    with lcol2:
        st.caption(":material/trending_down: Lagging sectors")
        for _, r in leaders.tail(3).iloc[::-1].iterrows():
            st.write(
                f"**{r['Sector']}** ({r.name}) · **{r['change_pct']:+.2f}%**  ·  ${r['price']:,.2f}"
            )

st.markdown("---")

# ---------------------------------------------------------------------------
# Watchlist snippet
# ---------------------------------------------------------------------------

st.subheader(":material/visibility: Your watchlist")

watch_items = load_watchlist()
watch_tickers = [it["ticker"] for it in watch_items]

if not watch_tickers:
    st.info(
        "You're not tracking anything yet. Head to **Stock Analysis** to research a name "
        "and add it to your watchlist — or open the **Watchlist** page to add tickers directly.",
        icon=":material/lightbulb:",
    )
else:
    with st.spinner("Fetching watchlist quotes..."):
        watch_changes = get_daily_changes(tuple(watch_tickers))

    rows = []
    for it in watch_items:
        t = it["ticker"]
        target = it.get("target_price")
        if t not in watch_changes.index:
            rows.append({
                "Ticker": t,
                "Price": None,
                "Change %": None,
                "Target": target,
                "vs Target": None,
                "Status": "No data",
            })
            continue
        r = watch_changes.loc[t]
        price = float(r["price"])
        pct = float(r["change_pct"])
        if target is not None and target > 0:
            vs_target = (price - target) / target * 100
            if price >= target:
                status = ":material/check_circle: Target hit"
            elif vs_target >= -5:
                status = ":material/trending_up: Near target"
            else:
                status = ":material/schedule: Below target"
        else:
            vs_target = None
            status = "—"
        rows.append({
            "Ticker": t,
            "Price": price,
            "Change %": pct,
            "Target": target,
            "vs Target": vs_target,
            "Status": status,
        })

    watch_df = pd.DataFrame(rows)
    st.dataframe(
        watch_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Change %": st.column_config.NumberColumn(format="%+.2f%%"),
            "Target": st.column_config.NumberColumn(format="$%.2f"),
            "vs Target": st.column_config.NumberColumn(format="%+.1f%%"),
        },
    )

    # Quick alert summary
    hit = [r for r in rows if r["Status"] and "Target hit" in r["Status"]]
    near = [r for r in rows if r["Status"] and "Near target" in r["Status"]]
    if hit:
        st.success(
            f":material/check_circle: **Price target hit:** {', '.join(r['Ticker'] for r in hit)}",
            icon=":material/notifications_active:",
        )
    elif near:
        st.warning(
            f":material/trending_up: **Approaching target:** {', '.join(r['Ticker'] for r in near)}",
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Top movers — S&P 100 subset for speed
# ---------------------------------------------------------------------------

st.subheader(":material/bolt: Today's movers")

# Curated S&P 100 subset — good signal/weight tradeoff; ~30 mega-caps
MOVERS_UNIVERSE = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "LLY", "AVGO",
    "V", "JPM", "UNH", "XOM", "MA", "JNJ", "WMT", "PG", "HD", "ORCL",
    "BAC", "COST", "CVX", "ABBV", "KO", "MRK", "NFLX", "CRM", "AMD", "PEP",
    "ADBE", "CSCO", "TMO", "ACN", "MCD", "INTC", "QCOM", "DIS", "BA", "CAT",
)

with st.spinner("Scanning top movers..."):
    movers = get_daily_changes(MOVERS_UNIVERSE)

if movers.empty:
    st.warning("Couldn't fetch mover data right now. Try again in a minute.")
else:
    movers_sorted = movers.sort_values("change_pct", ascending=False)
    gainers = movers_sorted.head(5)
    losers = movers_sorted.tail(5).iloc[::-1]

    gcol, lcol = st.columns(2)
    with gcol:
        st.caption(":material/trending_up: Top gainers")
        for t, r in gainers.iterrows():
            st.markdown(
                f"**{t}** · ${r['price']:,.2f}  "
                f"<span style='color:#16a34a;font-weight:600;'>{r['change_pct']:+.2f}%</span>",
                unsafe_allow_html=True,
            )
    with lcol:
        st.caption(":material/trending_down: Top losers")
        for t, r in losers.iterrows():
            st.markdown(
                f"**{t}** · ${r['price']:,.2f}  "
                f"<span style='color:#dc2626;font-weight:600;'>{r['change_pct']:+.2f}%</span>",
                unsafe_allow_html=True,
            )

st.markdown("---")

# ---------------------------------------------------------------------------
# Navigation CTAs
# ---------------------------------------------------------------------------

st.subheader(":material/explore: Explore")

ncol1, ncol2, ncol3, ncol4, ncol5 = st.columns(5)
with ncol1:
    st.page_link("pages/1_Stock_Analysis.py", label="Stock Analysis", icon=":material/query_stats:")
    st.caption("Buy / Hold / Avoid verdict with transparent rubric")
with ncol2:
    st.page_link("pages/2_Stock_Screener.py", label="Screener", icon=":material/search:")
    st.caption("Find undervalued names across the S&P 500")
with ncol3:
    st.page_link("pages/3_Compare_Stocks.py", label="Compare", icon=":material/compare_arrows:")
    st.caption("Side-by-side metrics and correlation")
with ncol4:
    st.page_link("pages/4_Portfolio_Risk.py", label="Portfolio", icon=":material/account_balance_wallet:")
    st.caption("Weighted return, volatility, and risk contributions")
with ncol5:
    st.page_link("pages/5_Watchlist.py", label="Watchlist", icon=":material/visibility:")
    st.caption("Track tickers, set price targets, get alerts")

st.caption(
    "Data: Yahoo Finance via yfinance. Macro 1h cache · Sector/movers 30m cache · "
    "Fundamentals 12h cache. No API key required."
)
