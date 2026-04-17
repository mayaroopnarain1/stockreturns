# -*- coding: utf-8 -*-
"""
Shared data-fetching helpers and constants.
All yfinance calls go through this module so caching is consistent.
"""

import streamlit as st
import yfinance as yf
import pandas as pd


# ---------------------------------------------------------------------------
# Sector -> SPDR sector ETF mapping (used for peer comparison)
# ---------------------------------------------------------------------------
SECTOR_ETF: dict[str, str] = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


# Macro tickers for the regime panel
MACRO_TICKERS: dict[str, str] = {
    "^VIX": "Volatility Index",
    "^TNX": "10-Year Treasury Yield",
    "SPY": "S&P 500",
}


# ---------------------------------------------------------------------------
# S&P 500 ticker list  (updated periodically — last verified March 2026)
# Maintaining a static list avoids scraping Wikipedia on every load.
# ---------------------------------------------------------------------------

SP500_TICKERS: list[str] = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "ATVI", "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX",
    "BBWI", "BBY", "BDX", "BEN", "BF.B", "BIO", "BK", "BKNG", "BKR", "BLK",
    "BMY", "BR", "BRK.B", "BRO", "BSX", "BWA", "BXP", "C", "CAG", "CAH",
    "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDAY", "CDNS", "CDW",
    "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI", "CINF", "CL",
    "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF",
    "COO", "COP", "COST", "CPB", "CPRT", "CPT", "CRL", "CRM", "CSCO", "CSGP",
    "CSX", "CTAS", "CTLT", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR", "D",
    "DAL", "DD", "DE", "DFS", "DG", "DGX", "DHI", "DHR", "DIS", "DISH",
    "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN",
    "DXC", "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "EMN",
    "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS", "ETN",
    "ETR", "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR", "F", "FANG",
    "FAST", "FBHS", "FCX", "FDS", "FDX", "FE", "FFIV", "FIS", "FISV", "FITB",
    "FLT", "FMC", "FOX", "FOXA", "FRC", "FRT", "FTNT", "FTV", "GD", "GE",
    "GILD", "GIS", "GL", "GLW", "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN",
    "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA", "HD", "HOLX", "HON",
    "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUM", "HWM", "IBM", "ICE",
    "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU", "INVH", "IP",
    "IPG", "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ", "J", "JBHT",
    "JCI", "JKHY", "JNJ", "JNPR", "JPM", "K", "KDP", "KEY", "KEYS", "KHC",
    "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR", "L", "LDOS", "LEN",
    "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNC", "LNT", "LOW", "LRCX",
    "LUMN", "LUV", "LVS", "LW", "LYB", "LYV", "MA", "MAA", "MAR", "MAS",
    "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META", "MGM", "MHK",
    "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO", "MOH", "MOS", "MPC",
    "MPWR", "MRK", "MRNA", "MRO", "MS", "MSCI", "MSFT", "MSI", "MTB", "MTCH",
    "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE",
    "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWL",
    "NWS", "NWSA", "NXPI", "O", "ODFL", "OGN", "OKE", "OMC", "ON", "ORCL",
    "ORLY", "OTIS", "OXY", "PARA", "PAYC", "PAYX", "PCAR", "PCG", "PEAK",
    "PEG", "PEP", "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG", "PKI",
    "PLD", "PM", "PNC", "PNR", "PNW", "POOL", "PPG", "PPL", "PRU", "PSA",
    "PSX", "PTC", "PVH", "PWR", "PXD", "PYPL", "QCOM", "QRVO", "RCL", "RE",
    "REG", "REGN", "RF", "RHI", "RJF", "RL", "RMD", "ROK", "ROL", "ROP",
    "ROST", "RSG", "RTX", "SBAC", "SBNY", "SBUX", "SCHW", "SEE", "SHW",
    "SIVB", "SJM", "SLB", "SNA", "SNPS", "SO", "SPG", "SPGI", "SRE", "STE",
    "STT", "STX", "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP",
    "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT", "TJX", "TMO",
    "TMUS", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN",
    "TT", "TTWO", "TXN", "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH",
    "UNP", "UPS", "URI", "USB", "V", "VFC", "VICI", "VLO", "VMC", "VNO",
    "VRSK", "VRSN", "VRTX", "VTR", "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD",
    "WDC", "WEC", "WELL", "WFC", "WHR", "WM", "WMB", "WMT", "WRB", "WRK",
    "WST", "WTW", "WY", "WYNN", "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH",
    "ZBRA", "ZION", "ZTS",
]

# Common preset universes
UNIVERSE_OPTIONS: dict[str, list[str]] = {
    "S&P 500": SP500_TICKERS,
}


# ---------------------------------------------------------------------------
# Data fetching — single ticker
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl="6h")
def get_price_history(symbol: str, period: str) -> pd.DataFrame:
    """Fetch OHLCV history for one ticker by period string."""
    data = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if data is None or data.empty:
        return pd.DataFrame()
    return data


@st.cache_data(show_spinner=False, ttl="6h")
def get_price_history_dates(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV history for one ticker by start/end dates."""
    data = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
    if data is None or data.empty:
        return pd.DataFrame()
    return data


@st.cache_data(show_spinner=False, ttl="6h")
def get_ticker_info(symbol: str) -> dict:
    """Return the .info dict for a single ticker. Returns {} on failure."""
    try:
        return dict(yf.Ticker(symbol).info)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Bulk fundamental fetch — for the screener
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl="12h")
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

@st.cache_data(show_spinner=False, ttl="1h")
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

@st.cache_data(show_spinner=False, ttl="12h")
def get_earnings_dates(symbol: str) -> pd.DataFrame:
    """Return known past & future earnings dates for a ticker.

    yfinance coverage is spotty — some tickers return None or empty. Callers
    should handle an empty DataFrame without erroring.
    """
    try:
        ed = yf.Ticker(symbol).earnings_dates
        if ed is None or len(ed) == 0:
            return pd.DataFrame()
        df = ed.copy()
        # Normalise index to timezone-naive timestamps for easy joining
        df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl="6h")
def get_dividends(symbol: str, period: str = "5y") -> pd.Series:
    """Return a Series of dividend payments (indexed by ex-date, values = $ / share).

    Uses auto_adjust=False to preserve the Dividends column; returns an empty
    Series on failure.
    """
    try:
        hist = yf.Ticker(symbol).history(period=period, auto_adjust=False, actions=True)
        if hist is None or hist.empty or "Dividends" not in hist.columns:
            return pd.Series(dtype=float)
        divs = hist[hist["Dividends"] > 0]["Dividends"]
        divs.index = pd.to_datetime(divs.index).tz_localize(None) if divs.index.tz is not None else pd.to_datetime(divs.index)
        return divs
    except Exception:
        return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Sector helpers
# ---------------------------------------------------------------------------

def get_sector_etf(sector: str | None) -> str | None:
    """Return the SPDR sector ETF symbol for a given sector name, or None if not mapped."""
    if not sector:
        return None
    return SECTOR_ETF.get(sector)


# ---------------------------------------------------------------------------
# Bulk daily changes — for Market Pulse heatmap and movers list
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl="30m")
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

@st.cache_data(show_spinner=False, ttl="24h")
def get_financials(symbol: str, freq: str = "annual") -> dict:
    """Fetch the three core financial statements for a single ticker.

    freq: "annual" (default) or "quarterly". Returns a dict with keys
    ``income``, ``balance``, ``cashflow`` — each a DataFrame with line items
    on the index and periods on the columns, ordered oldest → newest.
    Missing statements are returned as empty DataFrames so callers can
    render gracefully.
    """
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
        # yfinance returns columns as period-end Timestamps, newest first.
        # Sort oldest → newest for natural left-to-right trend rendering.
        df = df.copy()
        try:
            df = df.reindex(sorted(df.columns), axis=1)
        except Exception:
            pass
        return df

    return {"income": _prep(inc), "balance": _prep(bal), "cashflow": _prep(cf)}


def get_sector_peers(
    ticker: str,
    sector: str | None,
    universe_df: pd.DataFrame | None = None,
    n: int = 4,
) -> list[str]:
    """Pick up to n S&P 500 peers in the same sector by market cap.

    Requires a pre-fetched fundamentals DataFrame (as produced by
    fetch_fundamentals_bulk) to avoid triggering a 5-minute bulk fetch.
    Returns an empty list if the universe isn't available or sector is missing.
    """
    if universe_df is None or universe_df.empty or not sector:
        return []
    if "sector" not in universe_df.columns or "marketCap" not in universe_df.columns:
        return []
    same_sector = universe_df[universe_df["sector"] == sector]
    same_sector = same_sector.drop(ticker, errors="ignore")
    same_sector = same_sector.sort_values("marketCap", ascending=False)
    return same_sector.head(n).index.tolist()
