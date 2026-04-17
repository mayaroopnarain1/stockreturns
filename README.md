# StockLens

A multi-page Streamlit app for equity research, comparison, and portfolio construction. Built for self-directed investors and MBA-level finance students who want transparent, rules-based output rather than black-box scores.

No API keys required — all market data comes live from Yahoo Finance via [`yfinance`](https://github.com/ranaroussi/yfinance).

## What's inside

**Market Pulse (home)** — the morning dashboard. Macro regime strip (VIX, 10Y yield, S&P 500 level), 11-tile SPDR sector heatmap colored by 1-day % change, watchlist snippet with live price vs. target status, top gainers and losers.

**Stock Analysis** — the research hub. For any ticker:
- Buy / Hold / Avoid verdict with a **transparent rubric** (valuation, quality, momentum, macro) calibrated to one of four investor profiles (Balanced, Value, Growth, Income)
- Expandable "How was this calculated?" panel showing every component score and its inputs
- Tabs for Overview, Fundamentals (with optional sector-percentile context), Technicals (RSI, MACD, Bollinger Bands, moving averages), Risk (Sharpe, Sortino, MaxDD, VaR, rolling vol, return distribution), and Price & Events (earnings / dividend / outlier-day overlays)

**Stock Screener** — scan the S&P 500 against your filters. Composite score is **investor-profile-aware**: the Value profile reweights toward cheap multiples, Growth leans on revenue growth, etc. Add top-N matches to the watchlist in one click.

**Compare Stocks** — pick 2–5 tickers. SPY benchmark overlay on the normalized price chart, best-in-cohort highlighting on the fundamentals table, prescription-engine verdicts up top, correlation matrix with a diversification read.

**Portfolio Risk** — enter holdings and weights (or load your watchlist). See portfolio return / vol / Sharpe / drawdown / VaR, alpha and beta vs. SPY, per-holding risk contributions, sector allocation breakdown with concentration alerts, and suggested alternative weight schemes (equal-weight, inverse-volatility).

**Watchlist** — persistent tracking (JSON file at `.watchlist.json`). Live price vs. 1d/5d moves, RSI bucket, 52-week range position, days tracked, next earnings, and alert banners when targets are hit, RSI flips extreme, or earnings land this week.

## Quickstart

```bash
# 1. Clone and enter the directory
git clone <your-repo-url>
cd Stocks

# 2. (Recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run streamlit_app.py
```

Streamlit opens the app at http://localhost:8501.

## How the verdict engine works

For a given ticker, four sub-scores (each 0–100) are computed from transparent rules:

1. **Valuation** — P/E, P/B, EV/EBITDA, PEG mapped to scores via "good" and "bad" anchor points (e.g. P/E of 15 → 100, P/E of 40 → 0). Linear between.
2. **Quality** — ROE, profit margin, operating margin, debt/equity, current ratio, free cash flow sign.
3. **Momentum** — derived from the technicals engine (trend direction × strength from MACD / RSI / moving-average crosses).
4. **Macro** — VIX level and 10Y yield mapped to a regime score.

The **composite** is a weighted sum; weights depend on the chosen investor profile:

| Profile  | Valuation | Quality | Momentum | Macro |
|----------|-----------|---------|----------|-------|
| Balanced | 30%       | 30%     | 25%      | 15%   |
| Value    | 45%       | 30%     | 10%      | 15%   |
| Growth   | 15%       | 30%     | 40%      | 15%   |
| Income   | 25%       | 40%     | 10%      | 25%   |

The composite maps to a verdict band (Buy / Hold / Avoid) plus a confidence level. The full breakdown is visible on the Stock Analysis page behind the "How was this calculated?" expander — there are no hidden inputs.

## Project structure

```
Stocks/
├── streamlit_app.py          # Market Pulse home page
├── pages/
│   ├── 1_Stock_Screener.py
│   ├── 2_Stock_Analysis.py
│   ├── 3_Compare_Stocks.py
│   ├── 4_Portfolio_Risk.py
│   ├── 5_Watchlist.py
│   └── archive/              # Legacy pages, preserved
├── utils/
│   ├── data.py               # yfinance wrappers (cached)
│   ├── metrics.py            # return / risk / technical calculations
│   ├── prescription.py       # verdict engine + investor profiles
│   └── watchlist.py          # JSON-backed persistence
├── requirements.txt
└── README.md
```

## Caching

All yfinance calls go through `utils/data.py` with TTL caches so repeat usage is fast and polite to Yahoo's servers:

| Data                              | Cache TTL |
|-----------------------------------|-----------|
| Macro snapshot (VIX, 10Y, SPY)    | 1 hour    |
| Bulk daily changes (heatmap etc.) | 30 minutes|
| Dividends                         | 6 hours   |
| Price history                     | 6 hours   |
| Earnings dates                    | 12 hours  |
| Single-ticker `.info`             | 12 hours  |
| S&P 500 bulk fundamentals         | 12 hours  |

The Screener's first run fetches fundamentals for all 500 names and takes 3–8 minutes. Subsequent runs within 12 hours are instant.

## Data caveats

Yahoo Finance is free and convenient, but it's a best-effort data source:
- Some tickers have spotty `earnings_dates` coverage — overlays silently drop missing dates.
- Fundamentals can differ from what broker dashboards show (different vendors, different fiscal-period cutoffs).
- Don't use this for real trading decisions without cross-checking against a primary source.

## Disclaimer

This app is for research and education. It is not investment advice. The verdict engine is a transparent heuristic, not a forecast. Past performance is not predictive of future returns.

## License

MIT (or whatever you prefer — update this line before publishing).
