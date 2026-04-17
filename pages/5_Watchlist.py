# -*- coding: utf-8 -*-
"""
StockLens — Watchlist

Persistent list of tickers the user is tracking, with live status:
  - Price, 1-day and 5-day changes
  - Price target (editable inline) with hit / near / below flags
  - RSI (14) bucket — overbought / oversold / neutral
  - 52-week range position
  - Days since added
  - Next known earnings date (if yfinance has it)

Storage is via utils/watchlist.py (JSON file) so state survives app restarts.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from utils.data import (
    get_daily_changes,
    get_earnings_dates,
    get_price_history,
    get_ticker_info,
)
from utils.metrics import rsi
from utils.watchlist import (
    add_ticker,
    load_watchlist,
    remove_ticker,
    update_notes,
    update_target,
)


st.set_page_config(
    page_title="StockLens — Watchlist",
    page_icon=":material/visibility:",
    layout="wide",
)

st.title(":material/visibility: Watchlist")
st.caption("Track tickers you're interested in, set price targets, and get quick status at a glance.")


# ===========================================================================
# Add ticker form
# ===========================================================================
with st.container(border=True):
    st.markdown("**Add a ticker**")
    add_cols = st.columns([2, 2, 4, 1])
    with add_cols[0]:
        new_ticker = st.text_input(
            "Ticker", value="", placeholder="e.g. AAPL", key="add_ticker",
            label_visibility="collapsed",
        )
    with add_cols[1]:
        new_target = st.number_input(
            "Target price ($)", min_value=0.0, value=0.0, step=1.0, format="%.2f",
            key="add_target", label_visibility="collapsed",
            help="Optional. Leave at 0 for no target.",
        )
    with add_cols[2]:
        new_notes = st.text_input(
            "Notes", value="", placeholder="Why you're watching it (optional)",
            key="add_notes", label_visibility="collapsed",
        )
    with add_cols[3]:
        add_clicked = st.button("Add", width="stretch", type="primary")

    if add_clicked:
        t = (new_ticker or "").strip().upper()
        if not t:
            st.warning("Enter a ticker.")
        else:
            # Validate by attempting a quote fetch
            info_check = get_ticker_info(t)
            if not info_check or not info_check.get("symbol") and not info_check.get("shortName"):
                st.error(f"Couldn't find a ticker named **{t}** on Yahoo Finance. Double-check the symbol.")
            else:
                target_val = new_target if new_target > 0 else None
                added = add_ticker(t, target_price=target_val, notes=new_notes)
                if added:
                    st.success(f"Added **{t}** to your watchlist.")
                else:
                    st.info(f"**{t}** is already on your watchlist (target updated if provided).")
                st.rerun()


# ===========================================================================
# Load watchlist
# ===========================================================================
items = load_watchlist()

if not items:
    st.info(
        "Your watchlist is empty. Add a ticker above, or open **Stock Analysis** "
        "and use the _Add to Watchlist_ button.",
        icon=":material/lightbulb:",
    )
    st.page_link("pages/2_Stock_Analysis.py", label="Open Stock Analysis", icon=":material/query_stats:")
    st.stop()


# ===========================================================================
# Compute status rows
# ===========================================================================
tickers = [it["ticker"] for it in items]
with st.spinner("Fetching quotes..."):
    changes = get_daily_changes(tuple(tickers))


def _rsi_bucket(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 70:
        return f"Overbought ({value:.0f})"
    if value <= 30:
        return f"Oversold ({value:.0f})"
    return f"Neutral ({value:.0f})"


def _5d_change(symbol: str) -> float | None:
    """Pull 1mo history, compute last 5-session % change."""
    hist = get_price_history(symbol, "1mo")
    if hist.empty or len(hist) < 6:
        return None
    close = hist["Close"]
    return float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)


def _rsi_latest(symbol: str) -> float | None:
    hist = get_price_history(symbol, "3mo")
    if hist.empty or len(hist) < 30:
        return None
    series = rsi(hist["Close"])
    if series is None or series.empty or pd.isna(series.iloc[-1]):
        return None
    return float(series.iloc[-1])


def _next_earnings(symbol: str) -> dt.datetime | None:
    ed = get_earnings_dates(symbol)
    if ed is None or ed.empty:
        return None
    now = pd.Timestamp(dt.datetime.now())
    future = ed.index[ed.index >= now]
    if len(future) == 0:
        return None
    return future.min().to_pydatetime()


today = dt.date.today()
rows = []
with st.spinner("Computing status..."):
    for it in items:
        t = it["ticker"]
        target = it.get("target_price")
        added_str = it.get("added_date", "")
        try:
            added_date = dt.date.fromisoformat(added_str) if added_str else today
        except ValueError:
            added_date = today
        days_since_added = (today - added_date).days

        if t in changes.index:
            r = changes.loc[t]
            price = float(r["price"])
            pct_1d = float(r["change_pct"])
        else:
            price = None
            pct_1d = None

        pct_5d = _5d_change(t)
        rsi_val = _rsi_latest(t)
        next_er = _next_earnings(t)
        days_to_er = (next_er.date() - today).days if next_er else None

        # 52w range pos (from info)
        info = get_ticker_info(t)
        w_high = info.get("fiftyTwoWeekHigh")
        w_low = info.get("fiftyTwoWeekLow")
        range_pos = None
        if price is not None and w_high and w_low and w_high > w_low:
            range_pos = (price - w_low) / (w_high - w_low) * 100

        # Status
        if price is None:
            status = "No data"
        elif target and target > 0:
            gap_pct = (price - target) / target * 100
            if price >= target:
                status = ":material/check_circle: Target hit"
            elif gap_pct >= -5:
                status = ":material/trending_up: Near target"
            else:
                status = ":material/schedule: Below target"
        else:
            status = "—"

        rows.append({
            "Ticker": t,
            "Price": price,
            "1d %": pct_1d,
            "5d %": pct_5d,
            "Target": target,
            "vs Target %": ((price - target) / target * 100) if (price is not None and target and target > 0) else None,
            "Status": status,
            "RSI(14)": _rsi_bucket(rsi_val),
            "52w range": range_pos,
            "Days tracked": days_since_added,
            "Next earnings": (
                f"{next_er.date().isoformat()} ({days_to_er}d)"
                if next_er is not None else "—"
            ),
            "Notes": it.get("notes", ""),
        })


# ===========================================================================
# Alert banners
# ===========================================================================
alerts_hit = [r for r in rows if "Target hit" in (r["Status"] or "")]
alerts_near = [r for r in rows if "Near target" in (r["Status"] or "")]
alerts_rsi_hot = [r for r in rows if "Overbought" in (r["RSI(14)"] or "")]
alerts_rsi_cold = [r for r in rows if "Oversold" in (r["RSI(14)"] or "")]
alerts_earnings = [
    r for r in rows
    if r["Next earnings"] != "—"
    and "(" in r["Next earnings"]
    and 0 <= int(r["Next earnings"].split("(")[1].split("d")[0]) <= 7
]

if alerts_hit or alerts_near or alerts_rsi_hot or alerts_rsi_cold or alerts_earnings:
    with st.container(border=True):
        st.markdown("**:material/notifications_active: Alerts**")
        if alerts_hit:
            st.success(
                f":material/check_circle: **Target hit:** {', '.join(r['Ticker'] for r in alerts_hit)}"
            )
        if alerts_near:
            st.warning(
                f":material/trending_up: **Within 5% of target:** {', '.join(r['Ticker'] for r in alerts_near)}"
            )
        if alerts_rsi_hot:
            st.warning(
                f":material/local_fire_department: **Overbought (RSI ≥ 70):** "
                f"{', '.join(r['Ticker'] for r in alerts_rsi_hot)} — watch for pullback"
            )
        if alerts_rsi_cold:
            st.info(
                f":material/ac_unit: **Oversold (RSI ≤ 30):** "
                f"{', '.join(r['Ticker'] for r in alerts_rsi_cold)} — potential entry"
            )
        if alerts_earnings:
            st.info(
                f":material/event: **Earnings this week:** "
                + ", ".join(f"{r['Ticker']} ({r['Next earnings']})" for r in alerts_earnings)
            )


# ===========================================================================
# Main table
# ===========================================================================
st.subheader("Live status")

df = pd.DataFrame(rows)
st.dataframe(
    df,
    hide_index=True,
    width="stretch",
    column_config={
        "Price": st.column_config.NumberColumn(format="$%.2f"),
        "1d %": st.column_config.NumberColumn(format="%+.2f%%"),
        "5d %": st.column_config.NumberColumn(format="%+.2f%%"),
        "Target": st.column_config.NumberColumn(format="$%.2f"),
        "vs Target %": st.column_config.NumberColumn(format="%+.1f%%"),
        "52w range": st.column_config.ProgressColumn(
            "52w range",
            min_value=0,
            max_value=100,
            format="%.0f%%",
            help="0% = 52-week low, 100% = 52-week high",
        ),
        "Days tracked": st.column_config.NumberColumn(format="%d"),
    },
)


# ===========================================================================
# Per-ticker actions
# ===========================================================================
st.subheader("Manage")
st.caption("Edit price targets, update notes, remove tickers, or jump into analysis.")

for it in items:
    t = it["ticker"]
    current_target = it.get("target_price")
    current_notes = it.get("notes", "")

    with st.expander(f"**{t}**"):
        e_cols = st.columns([2, 4, 1, 1])

        with e_cols[0]:
            new_target_val = st.number_input(
                "Target price ($)",
                min_value=0.0,
                value=float(current_target) if current_target else 0.0,
                step=1.0,
                format="%.2f",
                key=f"target_{t}",
            )
        with e_cols[1]:
            new_notes_val = st.text_input(
                "Notes",
                value=current_notes,
                key=f"notes_{t}",
            )
        with e_cols[2]:
            if st.button("Save", key=f"save_{t}", width="stretch"):
                tp = new_target_val if new_target_val > 0 else None
                update_target(t, tp)
                update_notes(t, new_notes_val)
                st.success(f"Saved changes for {t}.")
                st.rerun()
        with e_cols[3]:
            if st.button(":material/delete: Remove", key=f"remove_{t}", width="stretch"):
                remove_ticker(t)
                st.success(f"Removed {t} from watchlist.")
                st.rerun()

        # Link to Stock Analysis — preserve ticker via session state
        if st.button(
            f":material/query_stats: Analyze {t}",
            key=f"analyze_{t}",
            width="stretch",
        ):
            st.session_state["analysis_ticker"] = t
            st.switch_page("pages/2_Stock_Analysis.py")


# ===========================================================================
# Export
# ===========================================================================
with st.expander(":material/download: Export watchlist"):
    export_df = pd.DataFrame(items)
    st.download_button(
        "Download as CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=f"watchlist_{today.isoformat()}.csv",
        mime="text/csv",
    )
    st.caption(f"{len(items)} ticker(s) tracked · Stored in `.watchlist.json` next to the app.")
