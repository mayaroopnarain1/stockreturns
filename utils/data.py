# -*- coding: utf-8 -*-
"""
Shared data-fetching helpers and constants.

For US issuers, SEC EDGAR is the primary source for authoritative fundamentals
(statements, dividends, historical earnings dates). yfinance remains primary
for price-shaped data (quotes, macro, daily changes) and the fallback for any
ticker EDGAR does not cover (ADRs, foreign issuers). All caching stays here so
Streamlit behaviour is unchanged.
"""

from utils.cache import cache_data
import yfinance as yf
import pandas as pd

from utils.providers import ProviderError, ProviderNotCovered
from utils.providers import edgar_provider


from utils.constants import (  # noqa: F401 - re-exported for existing importers
    MACRO_TICKERS,
    SECTOR_ETF,
    SP500_TICKERS,
    UNIVERSE_OPTIONS,
    get_sector_etf,
    get_sector_peers,
)


# ---------------------------------------------------------------------------
# Data fetching — single ticker
# ---------------------------------------------------------------------------

@cache_data(ttl="6h")
def get_price_history(symbol: str, period: str) -> pd.DataFrame:
    """Fetch OHLCV history for one ticker by period string."""
    data = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if data is None or data.empty:
        return pd.DataFrame()
    return data


@cache_data(ttl="6h")
def get_price_history_dates(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV history for one ticker by start/end dates."""
    data = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
    if data is None or data.empty:
        return pd.DataFrame()
    return data


@cache_data(ttl="6h")
def get_ticker_info(symbol: str) -> dict:
    """Return the .info dict for a single ticker, enriched with EDGAR fundamentals.

    yfinance provides sector, industry, price, market cap and the 50+ other
    fields native to ``.info``. EDGAR overlays authoritative XBRL-derived
    values (margins, ROE, ROA, revenue growth, trailing EPS, book value,
    shares outstanding). When yfinance returns empty (throttled or missing
    ticker), the EDGAR overlay alone keeps the page usable.
    """
    try:
        yf_info = dict(yf.Ticker(symbol).info)
    except Exception:
        yf_info = {}

    # Best-effort EDGAR enrichment. Silently skipped when EDGAR doesn't cover
    # the ticker, the circuit breaker is open, or any other error occurs.
    try:
        edgar_extras = edgar_provider.get_ticker_extras(symbol)
    except (ProviderNotCovered, ProviderError):
        edgar_extras = {}
    except Exception:
        edgar_extras = {}

    # EDGAR wins on the overlap where both are present — its values come
    # straight from signed filings rather than Yahoo's derived view. But
    # fields yfinance uniquely provides (sector, beta, marketCap, etc.)
    # pass through unchanged.
    merged = dict(yf_info)
    for k, v in edgar_extras.items():
        if v is not None:
            merged[k] = v
    return merged


# ---------------------------------------------------------------------------
# Bulk fundamental fetch — for the screener
# ---------------------------------------------------------------------------

@cache_data(ttl="12h")
def fetch_fundamentals_bulk(tickers: list[str]) -> pd.DataFrame:
    """
    Fetch key fundamental fields for a list of tickers.
    Returns a DataFrame indexed by ticker with one row per stock.
    Slow for large lists (~1-2 sec per ticker). Cache aggressively.
    """
    fields = [
        "shortName", "sector", "industry", "marketCap",
        "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
        "priceToSalesTrailing12Months", "pegRatio",
        "dividendYield", "payoutRatio",
        "returnOnEquity", "returnOnAssets",
        "profitMargins", "operatingMargins",
        "revenueGrowth", "earningsGrowth",
        "debtToEquity", "currentRatio",
        "freeCashflow", "operatingCashflow",
        "enterpriseValue", "totalRevenue", "ebitda",
        "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        "currentPrice",
    ]

    rows = []
    for sym in tickers:
        info = get_ticker_info(sym)
        if not info:
            continue
        row = {"Ticker": sym}
        for f in fields:
            row[f] = info.get(f)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("Ticker")
    return df


# ---------------------------------------------------------------------------
# Macro snapshot — VIX, 10Y yield, SPY current level + 1-day change
# ---------------------------------------------------------------------------

@cache_data(ttl="1h")
def get_macro_snapshot() -> dict:
    """Fetch current values and 1-day % change for the macro regime panel.

    Returns a dict keyed by symbol. Each value is {"current": float|None,
    "change_pct": float|None, "label": str}. Returns None values on fetch
    failure so callers can render gracefully.
    """
    snap: dict[str, dict] = {}
    for sym, label in MACRO_TICKERS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d", auto_adjust=True)
            if hist is None or hist.empty:
                snap[sym] = {"current": None, "change_pct": None, "label": label}
                continue
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            change_pct = (current - prev) / prev * 100 if prev else 0.0
            snap[sym] = {"current": current, "change_pct": change_pct, "label": label}
        except Exception:
            snap[sym] = {"current": None, "change_pct": None, "label": label}
    return snap


# ---------------------------------------------------------------------------
# Events — earnings dates and dividends for the Price & Events overlay
# ---------------------------------------------------------------------------

def _yf_earnings_dates(symbol: str) -> pd.DataFrame:
    try:
        ed = yf.Ticker(symbol).earnings_dates
        if ed is None or len(ed) == 0:
            return pd.DataFrame()
        df = ed.copy()
        df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


@cache_data(ttl="12h")
def get_earnings_dates(symbol: str) -> pd.DataFrame:
    """Return known earnings dates for a ticker.

    EDGAR supplies historical release dates (from 10-Q / 10-K filings) with
    authoritative Reported EPS. yfinance is used to fill in any forward-dated
    entries EDGAR cannot provide (IR-calendar scheduled releases).
    """
    edgar_df = pd.DataFrame()
    try:
        edgar_df = edgar_provider.get_earnings_dates(symbol)
    except ProviderNotCovered:
        pass
    except ProviderError:
        pass
    except Exception:
        pass

    yf_df = _yf_earnings_dates(symbol)

    if edgar_df.empty:
        return yf_df
    if yf_df.empty:
        return edgar_df

    # Merge: keep EDGAR rows (authoritative past) + any yfinance rows that
    # don't have a matching period end already in EDGAR (typically future).
    cutoff = edgar_df.index.max()
    yf_future = yf_df[yf_df.index > cutoff]
    merged = pd.concat([edgar_df, yf_future]).sort_index()
    merged = merged[~merged.index.duplicated(keep="first")]
    return merged


def _yf_dividends(symbol: str, period: str) -> pd.Series:
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=False, actions=True)
        if hist is None or hist.empty or "Dividends" not in hist.columns:
            return pd.Series(dtype=float)
        divs = hist[hist["Dividends"] > 0]["Dividends"]
        divs.index = pd.to_datetime(divs.index).tz_localize(None) if divs.index.tz is not None else pd.to_datetime(divs.index)
        return divs
    except Exception:
        return pd.Series(dtype=float)


@cache_data(ttl="6h")
def get_dividends(symbol: str, period: str = "5y") -> pd.Series:
    """Return dividends per share indexed by declaration/ex-date.

    EDGAR primary (declared-DPS XBRL facts from 10-K), yfinance fallback for
    tickers EDGAR does not cover.
    """
    try:
        return edgar_provider.get_dividends(symbol, period=period)
    except ProviderNotCovered:
        return _yf_dividends(symbol, period)
    except ProviderError:
        return _yf_dividends(symbol, period)
    except Exception:
        return _yf_dividends(symbol, period)


# ---------------------------------------------------------------------------
# Bulk daily changes — for Market Pulse heatmap and movers list
# ---------------------------------------------------------------------------

@cache_data(ttl="30m")
def get_daily_changes(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Bulk-fetch current price and 1-day % change for a list of tickers.

    Uses yfinance's batch download endpoint which is dramatically faster than
    looping Ticker(...).history() one at a time. Caches 30 min — fresh enough
    for a market-hours heatmap, coarse enough to avoid hammering Yahoo.

    Returns a DataFrame indexed by ticker with columns [price, prev_close,
    change_abs, change_pct, volume]. Missing tickers are simply omitted.
    """
    if not tickers:
        return pd.DataFrame()
    # Convert to list for yfinance
    ticker_list = list(tickers)
    try:
        data = yf.download(
            ticker_list,
            period="5d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception:
        return pd.DataFrame()

    if data is None or data.empty:
        return pd.DataFrame()

    rows = []
    # Handle single-ticker case (columns are flat) vs multi (MultiIndex)
    single = len(ticker_list) == 1
    for t in ticker_list:
        try:
            if single:
                closes = data["Close"].dropna()
                vols = data["Volume"].dropna() if "Volume" in data.columns else pd.Series(dtype=float)
            else:
                if t not in data.columns.get_level_values(0):
                    continue
                sub = data[t]
                closes = sub["Close"].dropna()
                vols = sub["Volume"].dropna() if "Volume" in sub.columns else pd.Series(dtype=float)
            if len(closes) < 2:
                continue
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            change_abs = price - prev
            change_pct = (change_abs / prev * 100) if prev else 0.0
            vol = float(vols.iloc[-1]) if not vols.empty else 0.0
            rows.append({
                "Ticker": t,
                "price": price,
                "prev_close": prev,
                "change_abs": change_abs,
                "change_pct": change_pct,
                "volume": vol,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("Ticker")
    return df


# ---------------------------------------------------------------------------
# Financial statements — income / balance sheet / cash flow
# ---------------------------------------------------------------------------

def _yf_financials(symbol: str, freq: str) -> dict:
    empty = {"income": pd.DataFrame(), "balance": pd.DataFrame(), "cashflow": pd.DataFrame()}
    try:
        t = yf.Ticker(symbol)
        if freq == "quarterly":
            inc = t.quarterly_income_stmt
            bal = t.quarterly_balance_sheet
            cf = t.quarterly_cashflow
        else:
            inc = t.income_stmt
            bal = t.balance_sheet
            cf = t.cashflow
    except Exception:
        return empty

    def _prep(df):
        if df is None or (hasattr(df, "empty") and df.empty):
            return pd.DataFrame()
        df = df.copy()
        try:
            df = df.reindex(sorted(df.columns), axis=1)
        except Exception:
            pass
        return df

    return {"income": _prep(inc), "balance": _prep(bal), "cashflow": _prep(cf)}


# Rows the downstream financials analytics (utils/financials.py) actually
# consume. If EDGAR returns a statement with ANY of these rows all-NaN, we
# fetch yfinance and fill that row in — correcting EDGAR's concept-tagging
# gaps rather than swallowing them as junk output.
_CRITICAL_FINANCIAL_ROWS: dict[str, tuple[str, ...]] = {
    "income": ("Total Revenue", "Net Income", "Operating Income",
               "Gross Profit", "Pretax Income", "Tax Provision"),
    "balance": ("Total Assets", "Stockholders Equity",
                "Current Liabilities", "Current Assets"),
    "cashflow": ("Operating Cash Flow", "Capital Expenditure"),
}


def _fill_missing_rows(edgar_stmts: dict, yf_stmts: dict) -> dict:
    """Copy rows from yfinance into EDGAR result where the EDGAR row is all-NaN.

    Mutates and returns a new dict. Only the critical rows listed above are
    considered — we don't want to overwrite legitimately absent line items
    that simply weren't requested, or churn labels that already carry data.
    """
    out = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in edgar_stmts.items()}
    for statement, critical in _CRITICAL_FINANCIAL_ROWS.items():
        edf = out.get(statement)
        yf_df = yf_stmts.get(statement) if yf_stmts else None
        if edf is None or edf.empty or yf_df is None or yf_df.empty:
            continue
        yf_norm = {str(i).strip().lower(): i for i in yf_df.index}
        for row_label in critical:
            if row_label not in edf.index:
                continue
            if not edf.loc[row_label].isna().all():
                continue
            yf_key = yf_norm.get(row_label.strip().lower())
            if yf_key is None:
                continue
            yf_row = pd.to_numeric(yf_df.loc[yf_key], errors="coerce")
            # Align yfinance periods onto EDGAR columns; leave NaN where
            # no matching period exists.
            aligned = pd.Series(
                {c: yf_row.get(c, float("nan")) for c in edf.columns},
                index=edf.columns,
                dtype=float,
            )
            if aligned.notna().any():
                out[statement].loc[row_label] = aligned
    return out


@cache_data(ttl="24h")
def get_financials(symbol: str, freq: str = "annual") -> dict:
    """Fetch the three core financial statements for a single ticker.

    EDGAR primary — XBRL from 10-K (annual) or 10-Q (quarterly). yfinance
    fallback when EDGAR doesn't cover the ticker (ADRs / foreign issuers) AND
    row-level fill when EDGAR returns a statement where a critical line item
    (Revenue, Net Income, etc.) is all-NaN because the filer tagged it under
    a non-standard concept.

    freq: "annual" (default) or "quarterly". Returns a dict with keys
    ``income``, ``balance``, ``cashflow`` — each a DataFrame with line items
    on the index and period-end Timestamps on the columns, ordered oldest →
    newest. Missing statements are returned as empty DataFrames so callers
    can render gracefully.
    """
    try:
        edgar_stmts = edgar_provider.get_financials(symbol, freq=freq)
    except (ProviderNotCovered, ProviderError):
        return _yf_financials(symbol, freq)
    except Exception:
        return _yf_financials(symbol, freq)

    # Row-level fill: only bother calling yfinance if at least one critical
    # row is empty. For the common AAPL/MSFT case this costs nothing.
    needs_fill = False
    for statement, rows in _CRITICAL_FINANCIAL_ROWS.items():
        df = edgar_stmts.get(statement)
        if df is None or df.empty:
            continue
        for row in rows:
            if row in df.index and df.loc[row].isna().all():
                needs_fill = True
                break
        if needs_fill:
            break
    if not needs_fill:
        return edgar_stmts

    yf_stmts = _yf_financials(symbol, freq)
    return _fill_missing_rows(edgar_stmts, yf_stmts)
