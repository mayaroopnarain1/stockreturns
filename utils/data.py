# -*- coding: utf-8 -*-
"""Shared data-fetching helpers and constants."""

import streamlit as st
import yfinance as yf
import pandas as pd

# S&P 500 tickers (static list — avoids scraping Wikipedia on every load)
SP500_TICKERS: list[str] = [
    "AAPL","ABBV","ABT","ACN","ADBE","ADI","ADM","ADP","ADSK","AEE","AEP","AES",
    "AFL","AIG","AIZ","AJG","AKAM","ALB","ALGN","ALK","ALL","ALLE","AMAT","AMCR",
    "AMD","AME","AMGN","AMP","AMT","AMZN","ANET","ANSS","AON","AOS","APA","APD",
    "APH","APTV","ARE","ATO","ATVI","AVB","AVGO","AVY","AWK","AXP","AZO","BA",
    "BAC","BAX","BBWI","BBY","BDX","BEN","BF.B","BIO","BK","BKNG","BKR","BLK",
    "BMY","BR","BRK.B","BRO","BSX","BWA","BXP","C","CAG","CAH","CARR","CAT","CB",
    "CBOE","CBRE","CCI","CCL","CDAY","CDNS","CDW","CE","CEG","CF","CFG","CHD",
    "CHRW","CHTR","CI","CINF","CL","CLX","CMA","CMCSA","CME","CMG","CMI","CMS",
    "CNC","CNP","COF","COO","COP","COST","CPB","CPRT","CPT","CRL","CRM","CSCO",
    "CSGP","CSX","CTAS","CTLT","CTRA","CTSH","CTVA","CVS","CVX","CZR","D","DAL",
    "DD","DE","DFS","DG","DGX","DHI","DHR","DIS","DISH","DLR","DLTR","DOV","DOW",
    "DPZ","DRI","DTE","DUK","DVA","DVN","DXC","DXCM","EA","EBAY","ECL","ED","EFX",
    "EIX","EL","EMN","EMR","ENPH","EOG","EPAM","EQIX","EQR","EQT","ES","ESS","ETN",
    "ETR","ETSY","EVRG","EW","EXC","EXPD","EXPE","EXR","F","FANG","FAST","FBHS",
    "FCX","FDS","FDX","FE","FFIV","FIS","FISV","FITB","FLT","FMC","FOX","FOXA",
    "FRC","FRT","FTNT","FTV","GD","GE","GILD","GIS","GL","GLW","GM","GNRC","GOOG",
    "GOOGL","GPC","GPN","GRMN","GS","GWW","HAL","HAS","HBAN","HCA","HD","HOLX",
    "HON","HPE","HPQ","HRL","HSIC","HST","HSY","HUM","HWM","IBM","ICE","IDXX",
    "IEX","IFF","ILMN","INCY","INTC","INTU","INVH","IP","IPG","IQV","IR","IRM",
    "ISRG","IT","ITW","IVZ","J","JBHT","JCI","JKHY","JNJ","JNPR","JPM","K","KDP",
    "KEY","KEYS","KHC","KIM","KLAC","KMB","KMI","KMX","KO","KR","L","LDOS","LEN",
    "LH","LHX","LIN","LKQ","LLY","LMT","LNC","LNT","LOW","LRCX","LUMN","LUV",
    "LVS","LW","LYB","LYV","MA","MAA","MAR","MAS","MCD","MCHP","MCK","MCO","MDLZ",
    "MDT","MET","META","MGM","MHK","MKC","MKTX","MLM","MMC","MMM","MNST","MO",
    "MOH","MOS","MPC","MPWR","MRK","MRNA","MRO","MS","MSCI","MSFT","MSI","MTB",
    "MTCH","MTD","MU","NCLH","NDAQ","NDSN","NEE","NEM","NFLX","NI","NKE","NOC",
    "NOW","NRG","NSC","NTAP","NTRS","NUE","NVDA","NVR","NWL","NWS","NWSA","NXPI",
    "O","ODFL","OGN","OKE","OMC","ON","ORCL","ORLY","OTIS","OXY","PARA","PAYC",
    "PAYX","PCAR","PCG","PEAK","PEG","PEP","PFE","PFG","PG","PGR","PH","PHM",
    "PKG","PKI","PLD","PM","PNC","PNR","PNW","POOL","PPG","PPL","PRU","PSA","PSX",
    "PTC","PVH","PWR","PXD","PYPL","QCOM","QRVO","RCL","RE","REG","REGN","RF",
    "RHI","RJF","RL","RMD","ROK","ROL","ROP","ROST","RSG","RTX","SBAC","SBNY",
    "SBUX","SCHW","SEE","SHW","SIVB","SJM","SLB","SNA","SNPS","SO","SPG","SPGI",
    "SRE","STE","STT","STX","STZ","SWK","SWKS","SYF","SYK","SYY","T","TAP","TDG",
    "TDY","TECH","TEL","TER","TFC","TFX","TGT","TJX","TMO","TMUS","TPR","TRGP",
    "TRMB","TROW","TRV","TSCO","TSLA","TSN","TT","TTWO","TXN","TXT","TYL","UAL",
    "UDR","UHS","ULTA","UNH","UNP","UPS","URI","USB","V","VFC","VICI","VLO","VMC",
    "VNO","VRSK","VRSN","VRTX","VTR","VTRS","VZ","WAB","WAT","WBA","WBD","WDC",
    "WEC","WELL","WFC","WHR","WM","WMB","WMT","WRB","WRK","WST","WTW","WY","WYNN",
    "XEL","XOM","XRAY","XYL","YUM","ZBH","ZBRA","ZION","ZTS",
]


@st.cache_data(show_spinner=False, ttl="6h")
def get_price_history(symbol: str, period: str) -> pd.DataFrame:
    data = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    return data if data is not None and not data.empty else pd.DataFrame()


@st.cache_data(show_spinner=False, ttl="6h")
def get_price_history_dates(symbol: str, start: str, end: str) -> pd.DataFrame:
    data = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
    return data if data is not None and not data.empty else pd.DataFrame()


@st.cache_data(show_spinner=False, ttl="6h")
def get_ticker_info(symbol: str) -> dict:
    try:
        return dict(yf.Ticker(symbol).info)
    except Exception:
        return {}


@st.cache_data(show_spinner=False, ttl="12h")
def fetch_fundamentals_bulk(tickers: list[str]) -> pd.DataFrame:
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
        "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice",
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
    return pd.DataFrame(rows).set_index("Ticker") if rows else pd.DataFrame()
