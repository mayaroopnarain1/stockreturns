# -*- coding: utf-8 -*-
"""Live status for a client-held watchlist (the server stores nothing)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from api.services.common import rsi_bucket, target_status
from utils.metrics import rsi


def _trailing_stats(hist: pd.DataFrame) -> dict:
    """5-day % change and latest RSI from one 3-month history."""
    out = {"change_5d": None, "rsi": None}
    if hist is None or hist.empty:
        return out
    close = hist["Close"]
    if len(close) >= 6:
        out["change_5d"] = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)
    if len(close) >= 30:
        series = rsi(close)
        if series is not None and not series.empty and not pd.isna(series.iloc[-1]):
            out["rsi"] = float(series.iloc[-1])
    return out


def _next_earnings(ed: pd.DataFrame, now: pd.Timestamp) -> pd.Timestamp | None:
    if ed is None or ed.empty:
        return None
    future = ed.index[ed.index >= now]
    return future.min() if len(future) else None


def item_status(item: dict, changes: pd.DataFrame, data, today: dt.date, now: pd.Timestamp) -> dict:
    t = item["ticker"]
    target = item.get("target_price")
    target = float(target) if target not in (None, "") and float(target) > 0 else None

    try:
        added = dt.date.fromisoformat(item.get("added_date") or "")
    except ValueError:
        added = today
    days_tracked = (today - added).days

    price = pct_1d = None
    if changes is not None and not changes.empty and t in changes.index:
        r = changes.loc[t]
        price, pct_1d = float(r["price"]), float(r["change_pct"])

    trailing = _trailing_stats(data.get_price_history(t, "3mo"))
    nxt = _next_earnings(data.get_earnings_dates(t), now)
    days_to_er = (nxt.date() - today).days if nxt is not None else None

    info = data.get_ticker_info(t) or {}
    hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
    range_pos = None
    if price is not None and hi and lo and hi > lo:
        range_pos = (price - lo) / (hi - lo) * 100

    vs_target, status = target_status(price, target)
    return {
        "ticker": t,
        "price": price,
        "change_1d": pct_1d,
        "change_5d": trailing["change_5d"],
        "target": target,
        "vs_target": vs_target,
        "status": status,
        "rsi": rsi_bucket(trailing["rsi"]),
        "range_52w": range_pos,
        "days_tracked": days_tracked,
        "next_earnings": nxt.date().isoformat() if nxt is not None else None,
        "days_to_earnings": days_to_er,
        "notes": item.get("notes", ""),
    }


def build_alerts(rows: list[dict]) -> dict:
    """Group rows into the alert categories the Watchlist page shows."""
    def names(pred) -> list[str]:
        return [r["ticker"] for r in rows if pred(r)]

    earnings = [
        {"ticker": r["ticker"], "date": r["next_earnings"], "days": r["days_to_earnings"]}
        for r in rows
        if r["days_to_earnings"] is not None and 0 <= r["days_to_earnings"] <= 7
    ]
    return {
        "target_hit": names(lambda r: r["status"] == "hit"),
        "near_target": names(lambda r: r["status"] == "near"),
        "overbought": names(lambda r: r["rsi"]["label"] == "Overbought"),
        "oversold": names(lambda r: r["rsi"]["label"] == "Oversold"),
        "earnings_soon": earnings,
    }


def build_status(items: list[dict], data, today: dt.date | None = None,
                 now: pd.Timestamp | None = None) -> dict:
    today = today or dt.date.today()
    now = now or pd.Timestamp(dt.datetime.now())
    tickers = [i["ticker"] for i in items]
    changes = data.get_daily_changes(tuple(tickers)) if tickers else pd.DataFrame()
    rows = [item_status(i, changes, data, today, now) for i in items]
    return {"rows": rows, "alerts": build_alerts(rows)}
