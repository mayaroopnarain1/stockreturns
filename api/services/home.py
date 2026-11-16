# -*- coding: utf-8 -*-
"""Market Pulse (home) payload."""

from __future__ import annotations

import datetime as dt

from utils.constants import SECTOR_ETF

MOVERS_UNIVERSE = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "LLY", "AVGO",
    "V", "JPM", "UNH", "XOM", "MA", "JNJ", "WMT", "PG", "HD", "ORCL",
    "BAC", "COST", "CVX", "ABBV", "KO", "MRK", "NFLX", "CRM", "AMD", "PEP",
    "ADBE", "CSCO", "TMO", "ACN", "MCD", "INTC", "QCOM", "DIS", "BA", "CAT",
)


def vix_regime(vix: float | None) -> dict:
    """Regime label + tone from the VIX level (thresholds 15 / 20 / 30)."""
    if vix is None:
        return {"label": "—", "tone": "gray"}
    if vix < 15:
        return {"label": "Calm", "tone": "#16a34a"}
    if vix < 20:
        return {"label": "Normal", "tone": "#0891b2"}
    if vix < 30:
        return {"label": "Elevated", "tone": "#d97706"}
    return {"label": "Stressed", "tone": "#dc2626"}


def _row(ticker: str, r) -> dict:
    return {"ticker": ticker, "price": float(r["price"]), "change_pct": float(r["change_pct"])}


def top_movers(changes, n: int = 5) -> dict:
    """Top ``n`` gainers (desc) and losers (most negative first)."""
    if changes is None or changes.empty:
        return {"gainers": [], "losers": []}
    ordered = changes.sort_values("change_pct", ascending=False)
    gainers = [_row(t, r) for t, r in ordered.head(n).iterrows()]
    losers = [_row(t, r) for t, r in ordered.tail(n).iloc[::-1].iterrows()]
    return {"gainers": gainers, "losers": losers}


def sector_summary(changes) -> dict:
    """Tiles for every sector ETF plus leading/lagging three."""
    tiles = []
    for sector, etf in SECTOR_ETF.items():
        if changes is not None and not changes.empty and etf in changes.index:
            r = changes.loc[etf]
            tiles.append({"sector": sector, "etf": etf,
                          "price": float(r["price"]), "change_pct": float(r["change_pct"])})
        else:
            tiles.append({"sector": sector, "etf": etf, "price": None, "change_pct": None})
    have = sorted([t for t in tiles if t["change_pct"] is not None],
                  key=lambda t: t["change_pct"], reverse=True)
    return {"tiles": tiles, "leaders": have[:3], "laggards": have[-3:][::-1]}


def build_home(data, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    macro = data.get_macro_snapshot()
    tiles = []
    for sym in ("SPY", "^VIX", "^TNX"):
        m = macro.get(sym, {})
        tiles.append({"symbol": sym, "label": m.get("label", sym),
                      "current": m.get("current"), "change_pct": m.get("change_pct")})
    vix = macro.get("^VIX", {}).get("current")
    sectors = data.get_daily_changes(tuple(SECTOR_ETF.values()))
    movers = data.get_daily_changes(MOVERS_UNIVERSE)
    return {
        "date": today.isoformat(),
        "weekday": today.strftime("%A"),
        "is_weekend": today.weekday() >= 5,
        "macro": tiles,
        "regime": vix_regime(vix),
        "sectors": sector_summary(sectors),
        "movers": top_movers(movers),
    }
